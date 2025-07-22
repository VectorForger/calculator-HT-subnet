from __future__ import annotations
import asyncio
import multiprocessing as mp
from typing import Optional
from .calculator_model import SimpleCalculator
import time
import mesh
from mesh import DHT, get_dht_time
from mesh.p2p import P2P, P2PContext, PeerID, ServicerBase
from mesh.proto import dht_pb2, calculator_protocol_pb2
from mesh.utils import get_logger
from mesh.utils.asyncio import switch_to_uvloop
from mesh.utils.auth import AuthorizerBase, AuthRole, AuthRPCWrapperStreamer
from mesh.utils.mpfuture import MPFuture

logger = get_logger(__name__)

class SimpleCalculatorProtocol(mp.context.ForkProcess, ServicerBase):
    """Super simple calculator protocol with custom messages"""
    
    def __init__(
        self,
        dht: DHT,
        subnet_id: int,
        authorizer: Optional[AuthorizerBase] = None,
        client: bool = False,
        start: bool = False,
    ):
        super().__init__()
        self.dht = dht
        self.subnet_id = subnet_id
        self.peer_id = dht.peer_id
        self.node_id = dht.node_id
        self.node_info = dht_pb2.NodeInfo(node_id=self.node_id.to_bytes())
        self.authorizer = authorizer
        self.client = client
        self._p2p = None
        self.ready = MPFuture()
        self._inner_pipe, self._outer_pipe = mp.Pipe(duplex=True)
        self.daemon = True
        
        # Calculator (only for server nodes)
        self.calculator = None
        
        if start:
            self.run_in_background(await_ready=True)
    
    def run(self):
        """Run in separate process"""
        loop = switch_to_uvloop()
        stop = asyncio.Event()
        loop.add_reader(self._inner_pipe.fileno(), stop.set)
        
        async def _run():
            try:
                # Set up P2P connection
                self._p2p = await self.dht.replicate_p2p()
                
                # Add RPC handlers
                if self.authorizer is not None:
                    await self.add_p2p_handlers(
                        self._p2p,
                        AuthRPCWrapperStreamer(self, AuthRole.SERVICER, self.authorizer),
                    )
                else:
                    await self.add_p2p_handlers(self._p2p)
                
                # Initialize calculator for server nodes only
                if not self.client:
                    
                    self.calculator = SimpleCalculator()
                    logger.info("Calculator ready")
                
                self.ready.set_result(None)
                
            except Exception as e:
                logger.error(f"Protocol startup failed: {e}")
                self.ready.set_exception(e)
            
            try:
                await stop.wait()
            finally:
                await self.remove_p2p_handlers(self._p2p)
        
        try:
            loop.run_until_complete(_run())
        except KeyboardInterrupt:
            logger.info("Calculator shutting down...")
    
    def run_in_background(self, await_ready: bool = True, timeout: Optional[float] = None):
        """Start in background process"""
        self.start()
        if await_ready:
            self.ready.result(timeout)
    
    def get_stub(self, p2p: P2P, peer: PeerID) -> AuthRPCWrapperStreamer:
        """Get authenticated stub for peer communication"""
        stub = super().get_stub(p2p, peer)
        return AuthRPCWrapperStreamer(
            stub, AuthRole.CLIENT, self.authorizer, service_public_key=None
        )
    
    # THE MAIN RPC METHOD - This is what other nodes call
    async def rpc_calculate(
        self, request: calculator_protocol_pb2.CalculationRequest, context: P2PContext
    ) -> calculator_protocol_pb2.CalculationResponse:
        """
        Handle calculation requests from other nodes
        This is the core of our subnet!
        """
        expression = request.expression
        request_id = request.request_id
        
        logger.info(f"📝 Received calculation: {expression}")
        
        # Make sure we have a calculator (server mode)
        if self.calculator is None:
            return calculator_protocol_pb2.CalculationResponse(
                peer=self.node_info,
                dht_time=get_dht_time(),
                expression=expression,
                result=0.0,
                success=False,
                error="Node is in client mode - cannot perform calculations",
                request_id=request_id
            )
        
        # Do the actual calculation
        result_dict = self.calculator.calculate(expression)
        
        # Build response
        if result_dict["success"]:
            logger.info(f"✅ {expression} = {result_dict['result']}")
            return calculator_protocol_pb2.CalculationResponse(
                peer=self.node_info,
                dht_time=get_dht_time(),
                expression=expression,
                result=result_dict["result"],
                success=True,
                error="",
                request_id=request_id
            )
        else:
            logger.error(f"❌ {expression} failed: {result_dict['error']}")
            return calculator_protocol_pb2.CalculationResponse(
                peer=self.node_info,
                dht_time=get_dht_time(),
                expression=expression,
                result=0.0,
                success=False,
                error=result_dict["error"],
                request_id=request_id
            )
    
    # METHOD TO CALL OTHER NODES
    async def call_peer_calculate(
        self, peer: PeerID, expression: str
    ) -> calculator_protocol_pb2.CalculationResponse:
        """
        Call another calculator node to do math for us
        """
        request_id = f"calc_{int(time.time() * 1000)}"
        
        request = calculator_protocol_pb2.CalculationRequest(
            peer=self.node_info,
            expression=expression,
            request_id=request_id
        )
        
        try:
            logger.info(f"🔗 Asking peer {peer} to calculate: {expression}")
            p2p = await self.dht.replicate_p2p()
            response = await self.get_stub(p2p, peer).rpc_calculate(request)
            
            if response.success:
                logger.info(f"📨 Peer response: {expression} = {response.result}")
            else:
                logger.error(f"📨 Peer error: {response.error}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to call peer {peer}: {e}")
            return calculator_protocol_pb2.CalculationResponse(
                peer=self.node_info,
                dht_time=get_dht_time(),
                expression=expression,
                result=0.0,
                success=False,
                error=f"Network error: {str(e)}",
                request_id=request_id
            )