from __future__ import annotations

import asyncio
import multiprocessing as mp
from typing import AsyncIterator, Optional

import torch

import mesh
from mesh import DHT, get_dht_time
from mesh.compression.serialization import deserialize_torch_tensor, serialize_torch_tensor
from mesh.p2p import P2P, P2PContext, PeerID, ServicerBase
from mesh.proto import dht_pb2, inference_protocol_pb2, runtime_pb2
from mesh.subnet.utils.key import extract_rsa_peer_id_from_ssh
from mesh.substrate.chain_functions import Hypertensor
from mesh.utils import get_logger
from mesh.utils.asyncio import switch_to_uvloop
from mesh.utils.auth import AuthorizerBase, AuthRole, AuthRPCWrapperStreamer
from mesh.utils.mpfuture import MPFuture
from mesh.utils.serializer import MSGPackSerializer

logger = get_logger(__name__)


class MockProtocol(mp.context.ForkProcess, ServicerBase):

    """
    Add child process variables here

    _async_model: AsyncInferenceServer
    """
    
    def __init__(
        self,
        dht: DHT,
        subnet_id: int,
        balanced: bool = True,
        shutdown_timeout: float = 3,
        hypertensor: Optional[Hypertensor] = None,
        authorizer: Optional[AuthorizerBase] = None,
        parallel_rpc: Optional[int] = None,
        client: bool = False,
        start: bool = False,
    ):
        super().__init__()
        self.dht = dht
        self.subnet_id = subnet_id
        self.peer_id = dht.peer_id
        self.node_id = dht.node_id
        self.node_info = dht_pb2.NodeInfo(node_id=self.node_id.to_bytes()) # used in key authorizer
        self.balanced, self.shutdown_timeout = balanced, shutdown_timeout
        self._p2p = None
        self.authorizer = authorizer
        self.ready = MPFuture()
        self.rpc_semaphore = asyncio.Semaphore(parallel_rpc if parallel_rpc is not None else float("inf"))
        self._inner_pipe, self._outer_pipe = mp.Pipe(duplex=True)
        self.daemon = True
        self.hypertensor = hypertensor
        self.client = client

        if start:
            self.run_in_background(await_ready=True)

    def run(self):
        torch.set_num_threads(1)
        loop = switch_to_uvloop()
        stop = asyncio.Event()
        loop.add_reader(self._inner_pipe.fileno(), stop.set)

        async def _run():
            try:
                self._p2p = await self.dht.replicate_p2p()
                """Add rpc_* methods from this class to the P2P servicer"""
                if self.authorizer is not None:
                    logger.info("Adding P2P handlers with authorizer")
                    await self.add_p2p_handlers(
                        self._p2p,
                        AuthRPCWrapperStreamer(self, AuthRole.SERVICER, self.authorizer),
                    )
                else:
                    await self.add_p2p_handlers(self._p2p, balanced=self.balanced)

                """
                Run pytorch functions and classes in the child process
                Read more:
                    - https://stackoverflow.com/questions/22950047/cuda-initialization-error-after-fork/22950549#22950549
                    - https://github.com/pytorch/pytorch/issues/17199
                """

                if not self.client:
                    """
                    Start all functionality required for RPC methods here, in the child process.

                    Example:
                        If the RPC method requires running inference, the model class(es) should be 
                        loaded here.

                    See mesh example
                    """
                self.ready.set_result(None)
            except Exception as e:
                logger.debug(e, exc_info=True)
                self.ready.set_exception(e)

            try:
                await stop.wait()
            finally:
                await self.remove_p2p_handlers(self._p2p)

        try:
            loop.run_until_complete(_run())
        except KeyboardInterrupt:
            logger.debug("Caught KeyboardInterrupt, shutting down")

    def run_in_background(self, await_ready: bool = True, timeout: Optional[float] = None) -> None:
        """
        Starts MockProtocol in a background process. If :await_ready:, this method will wait until
        it is ready to process incoming requests or for :timeout: seconds max.
        """
        self.start()

    def shutdown(self):
        if self.is_alive():
            self.join(self.shutdown_timeout)
            if self.is_alive():
                logger.warning(
                    "MockProtocol did not shut down within the grace period; terminating it the hard way"
                )
                self.terminate()
        else:
            logger.warning("MockProtocol shutdown had no effect, the process is already dead")

    def get_stub(self, p2p: P2P, peer: PeerID) -> AuthRPCWrapperStreamer:
        """
        Get a stub that sends requests to a given peer.

        It's important here to wrap the stub with an authentication wrapper, see AuthRPCWrapper
        """
        stub = super().get_stub(p2p, peer)
        return AuthRPCWrapperStreamer(stub, AuthRole.CLIENT, self.authorizer, service_public_key=None)

    @classmethod
    def get_server_stub(
        cls,
        p2p: P2P,
        peer: PeerID,
        authorizer: Optional[AuthorizerBase] = None
    ) -> "InferenceProtocolStub":  # type: ignore # noqa: F821
        """
        Get a stub that sends requests to a given peer.

        This function can be used to get the RPC methods from this protocol outside of this class.

        This is useful for client-side requests.
        """

        stub = super().get_stub(p2p, peer)
        return AuthRPCWrapperStreamer(stub, AuthRole.CLIENT, authorizer, service_public_key=None)

    async def rpc_info(self, request: runtime_pb2.Empty, context: P2PContext) -> runtime_pb2.NodeData:
        """Return node metadata"""

        """
        Add any data you may want to quickly get from a node, such as their roles, etc.
        """
        result = {
            "version": mesh.__version__,
            "dht_client_mode": self.dht.client_mode,
            "role": "server" if not self.client else "client"
        }

        return runtime_pb2.NodeData(serialized_info=MSGPackSerializer.dumps(result))

    async def call_inference_stream(
        self, peer: PeerID, prompt: str, tensor: torch.Tensor
    ) -> AsyncIterator[torch.Tensor]:
        """
        Call another peer to perform an inference stream on the `tensor`

        The inference will be returned as a streamed
        """
        input_stream = inference_protocol_pb2.InferenceRequestAuth(
            input=prompt,
            max_new_tokens=5,
            tensor=serialize_torch_tensor(tensor),
        )

        try:
            async with self.rpc_semaphore:
                p2p = await self.dht.replicate_p2p()
                response_stream = await self.get_stub(p2p, peer).rpc_inference_stream(input_stream)
                async for response in response_stream:
                    for tensor_bytes in response.tensors:
                        tensor = deserialize_torch_tensor(tensor_bytes)
                        yield tensor
        except Exception as e:
            logger.error(f"MockProtocol failed to stream from {peer}: {e}", exc_info=True)
            return

    def should_process_inference(self, tensor: torch.Tensor) -> bool:
        """
        Ensures inference request doesn't match the current epochs random prompt

        This ensure peers/hosters cannot call inference on other hosters to use
        to copy.
        """
        return True
    
    async def rpc_inference_stream(
        self, requests: inference_protocol_pb2.InferenceRequestAuth, context: P2PContext
    ) -> AsyncIterator[inference_protocol_pb2.InferenceResponseAuth]:
        """
        A peer wants us to perform an inference stream
        """
        tensor = deserialize_torch_tensor(requests.tensor)
        
        caller_peer_id = extract_rsa_peer_id_from_ssh(requests.auth.client_access_token.public_key)
        """
        Don't allow other hosters to call inference on me if it matches
        the current epochs random consensus tensors
        """
        if self.authorizer is not None and not caller_peer_id.__eq__(self.peer_id):
            # Don't bother pinging the decentralized storage unless we have to
            run_inference = self.should_process_inference(tensor)
            if run_inference is False:
                raise ValueError("Tensor must not match the current validation tensor.")

        async for token_tensor in await self._async_model.submit(tensor):
            yield inference_protocol_pb2.InferenceResponseAuth(
                peer=self.node_info,
                dht_time=get_dht_time(),
                output=str(token_tensor.item()),
                tensors=[serialize_torch_tensor(token_tensor)]
            )
