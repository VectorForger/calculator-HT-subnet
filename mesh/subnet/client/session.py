from __future__ import annotations

import asyncio
import itertools
import time
from typing import AsyncIterator, Optional

import torch

from mesh import deserialize_torch_tensor, get_logger, serialize_torch_tensor
from mesh.proto import inference_protocol_pb2
from mesh.subnet.client.routing.routing_manager import RemoteManager
from mesh.subnet.protocols.mock_protocol import MockProtocol
from mesh.utils.auth import AuthorizerBase

logger = get_logger(__name__)


class Session:
    """
    An interface to call inference on a peer hoster
    """

    def __init__(
        self,
        remote_manager: RemoteManager,
        authorizer: Optional[AuthorizerBase] = None,
    ):
        self._remote_manager = remote_manager
        self._server_session = None
        self.server = None
        self._closed = False
        self.authorizer = authorizer

    async def run_protocol_task(
        self,
        prompt: str,
        tensor: torch.Tensor,
        max_retries: Optional[int] = 4,
    ) -> AsyncIterator[torch.Tensor]:
        for attempt_no in itertools.count():
            try:
                server_session = None
                # Fetch new server if they don't exist
                if not self._server_session or attempt_no >= 1:
                    # Get new server if None of fails
                    self._update_server(attempt_no)

                # Update session to the current server
                server_session = self._server_session

                # Fetch server stub to call inference on
                stub = MockProtocol.get_server_stub(
                    self._remote_manager.state.p2p,
                    server_session.peer_id,
                    self.authorizer
                )

                input_stream = inference_protocol_pb2.InferenceRequestAuth(
                    input=prompt,
                    max_new_tokens=5,
                    tensor=serialize_torch_tensor(tensor),
                )

                async with asyncio.Semaphore(float("inf")):
                    response_stream = await stub.rpc_inference_stream(input_stream)
                    async for response in response_stream:
                        for tensor_bytes in response.tensors:
                            tensor = deserialize_torch_tensor(tensor_bytes)
                            yield tensor
                return
            except Exception as e:
                self._remote_manager.on_request_failure(
                    server_session.peer_id if server_session is not None else None
                )
                if attempt_no + 1 == self._remote_manager.config.max_retries or attempt_no + 1 >= max_retries:
                    raise
                delay = self._remote_manager.get_retry_delay(attempt_no)
                logger.warning(
                    f"Caught exception when running inference via {server_session.peer_id if server_session is not None else None} "
                    f"(retry in {delay:.0f} sec): {repr(e)}"
                )
                time.sleep(delay)

    def _update_server(self, attempt_no: int):
        if attempt_no >= 1:
            logger.debug("Server failure")

        new_server_session = self._remote_manager.make_sequence()
        self._server_session = new_server_session

    async def close(self):
        if self._closed:
            return
        self._closed = True
