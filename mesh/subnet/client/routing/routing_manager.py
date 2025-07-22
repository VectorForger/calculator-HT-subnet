from __future__ import annotations

import dataclasses
import threading
from typing import Any, Dict, Optional, Sequence, Set, Union
from weakref import WeakMethod

from mesh import DHT, P2P, PeerID
from mesh.dht.node import Blacklist
from mesh.subnet.client.config import ClientConfig
from mesh.subnet.client.routing.remote_server_info import RemoteServerInfo
from mesh.subnet.data_structures import RemoteInfo
from mesh.subnet.utils.dht import get_node_infos
from mesh.subnet.utils.ping import PingAggregator
from mesh.utils.logging import get_logger
from mesh.utils.remote_worker import RemoteWorker

logger = get_logger(__name__)



@dataclasses.dataclass
class SequenceManagerState:
    p2p: P2P = None
    remote_servers_infos: Optional[RemoteServerInfo] = None
    rpc_info: Optional[dict] = None
    banned_peers: Optional[Blacklist] = None


class RemoteManager:
    """
    Sequence manager is a thread that keeps track of remote servers that can run inference.
    TL;DR it tells you, which peers you should ask to get inference. It is used in RemoteSequential.
    When created, RemoteManager looks up which servers serve necessary layers by reading from DHT.
    Using this information, sequence manager can form sequences of servers that collectively have the full sequence.
    To form such a sequence, call .make_sequence with the appropriate optimization policy (see make_sequence docstr).

    :note: RemoteManager takes up some CPU and network I/O to operate in background. It is recommended to avoid
      running redundant sequence managers for the same set of layers.
    """

    def __init__(
        self,
        config: ClientConfig,
        *,
        dht: Optional[DHT] = None,
        state: Optional[SequenceManagerState] = None,
    ):
        assert config.initial_peers or dht is not None, "Please specify `config.initial_peers` or `dht`"
        assert config.dht_prefix, "Could not find dht_prefix in config, please create model with dht_prefix=..."

        self.config = config
        if state is None:
            state = SequenceManagerState()
        self.state = state

        if dht is None:
            dht = DHT(
                initial_peers=config.initial_peers,
                client_mode=True,
                num_workers=32,
                startup_timeout=config.daemon_startup_timeout,
                start=True,
            )
        assert isinstance(dht, DHT) and dht.is_alive(), "`dht` must be a running mesh.DHT instance"
        self.dht = dht

        if state.p2p is None:
            state.p2p = RemoteWorker.run_coroutine(dht.replicate_p2p())

        self.lock_changes = threading.Lock()
        self._thread = _SequenceManagerUpdateThread(config.update_period, WeakMethod(self._update))
        self._thread_start_lock = threading.Lock()

        self.allowed_servers = self._peer_ids_to_set(config.allowed_servers)
        self.blocked_servers = self._peer_ids_to_set(config.blocked_servers)

        self.ping_aggregator = PingAggregator(dht)

        if state.banned_peers is None:
            state.banned_peers = Blacklist(base_time=config.ban_timeout, backoff_rate=2.0)
        if state.remote_servers_infos is None:
            state.remote_servers_infos = RemoteServerInfo.make_empty()

        if state.remote_servers_infos.last_updated_time is not None:
            self._thread.ready.set()  # no need to await the first dht fetch

    @staticmethod
    def _peer_ids_to_set(peer_ids: Optional[Sequence[Union[PeerID, str]]]) -> Optional[Set[PeerID]]:
        if peer_ids is None:
            return None

        result = set()
        for peer_id in peer_ids:
            if isinstance(peer_id, PeerID):
                result.add(peer_id)
            elif isinstance(peer_id, str):
                result.add(PeerID.from_base58(peer_id))
            else:
                raise TypeError(
                    f"`allowed_servers` and `blocked_servers` have to contain only PeerIDs or strings, but got {type(peer_id)}"
                )
        return result

    def make_sequence(
        self,
        *,
        cache_tokens_needed: Optional[int] = None,
    ) -> RemoteInfo:
        """
        Form a sequence of remote servers that collectively serve all consecutive layers

        :param mode: one of ["max_throughput", "min_latency"]
        """
        with self._thread_start_lock:
            if not self.is_alive():
                self._thread.start()
        if not self.ready.is_set():
            self.update(wait=True)  # this will await an existing update or trigger a new one (if not updating)

        server = self._get_peer_with_max_throughput()

        return server

    @staticmethod
    def _rtt_to_delay(
        rtt: float,
        *,
        default_delay: float = 0.15,  # If network delay unknown
        max_delay: float = 5,  # If unreachable, we don't want to discard the edge completely
    ) -> float:
        if rtt is None:
            return default_delay
        return min(rtt / 2, max_delay)

    def _get_peer_with_max_throughput(self) -> RemoteInfo:
        client_server_rtts = self.ping_aggregator.to_dict()

        # Get node with the lowest throughput
        max_throughput_server = min(client_server_rtts, key=client_server_rtts.get)

        remote_info = next(
            (info for info in self.state.remote_servers_infos.server_infos if info.peer_id == max_throughput_server),
            None
        )

        if remote_info is None:
            raise RuntimeError("No nodes available")

        return remote_info

    def _get_peer_with_random(self) -> RemoteInfo:
        client_server_rtts = self.ping_aggregator.to_dict()
        raise RuntimeError("No nodes available")

    def __getitem__(self, ix: Union[int, slice]) -> RemoteManager:
        """Get a RemoteManager for a sub-sequence of blocks"""
        assert isinstance(ix, (int, slice))
        if not isinstance(ix, slice):
            ix = slice(int(ix), int(ix) + 1, 1)
        return type(self)(self.config, dht=self.dht, state=self.state)

    def update(self, *, wait: bool):
        """Run an asynchronous update in background as soon as possible"""
        self.ready.clear()
        self._thread.trigger.set()
        if wait:
            self.ready.wait()

    def _update(self):
        """
        Perform an immediate and synchronous refresh, may take time
        """
        hoster_infos = get_node_infos(
          self.dht,
          uid="hoster",
          latest=True
        )

        with self.lock_changes:
            self.state.remote_servers_infos.update_(hoster_infos)
            all_servers = [server.peer_id for server in hoster_infos]

        self.ping_aggregator.ping(list(all_servers), wait_timeout=self.config.ping_timeout)

        self.ready.set()

    def on_request_failure(self, peer_id: Optional[PeerID]):
        """remove a given peer from the routing table. If the routing is no longer possible, trigger an update"""
        if peer_id is not None:
            logger.debug(f"Peer {peer_id} did not respond, banning it temporarily")
            self.state.banned_peers.register_failure(peer_id)
        with self.lock_changes:
            should_update = False
            if not self.state.remote_servers_infos.server_infos:
                should_update = True
            if should_update:
                self.ready.clear()
                self.update(wait=False)

    def on_request_success(self, peer_id: PeerID):
        """if peer has a failure streak, clear that streak"""
        self.state.banned_peers.register_success(peer_id)

    @property
    def is_alive(self):
        return self._thread.is_alive

    @property
    def ready(self) -> threading.Event:
        return self._thread.ready

    def get_retry_delay(self, attempt_no: int) -> float:
        if attempt_no == 0:
            return 0
        return min(self.config.min_backoff * 2 ** (attempt_no - 1), self.config.max_backoff)

    def get_request_metadata(
        self, protocol: str, args_structure: Any = None, *args, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        :param protocol: one of "rpc_forward", "rpc_backward" or "rpc_inference"
        :param args_structure: the structure of flattened tensors from pack_args_kwargs in subnet.utils.packaging
        :param args: request-specific inputs, typically block uids and input tensors
        :param kwargs: additional request context, such as remote peer ID
        :returns: msgpack-serialized metadata dict that will be passed alongside a given request
        """
        return dict(
            active_adapter=self.config.active_adapter,
            args_structure=args_structure,
        )

    def shutdown(self):
        self._thread.shutdown()


class _SequenceManagerUpdateThread(threading.Thread):
    def __init__(self, update_period: float, ref_update_manager: WeakMethod):
        super().__init__(daemon=True)
        self.ref_update_manager = ref_update_manager
        self.ready = threading.Event()
        self.trigger = threading.Event()
        self.update_period = update_period
        self.should_shutdown = False

    def run(self) -> None:
        while not self.should_shutdown:
            update_manager = self.ref_update_manager()
            if update_manager is None:
                logger.debug(f"{self.__class__.__name__} exited because the sequence manager no longer exists")
                break

            try:
                self.trigger.clear()
                update_manager()
            except Exception as e:
                logger.exception(e, exc_info=True)
            finally:
                del update_manager

            self.trigger.wait(self.update_period)

        logger.debug(f"{self.__class__.__name__} thread exited")

    def shutdown(self, timeout: Optional[float] = None):
        self.should_shutdown = True
        self.trigger.set()
        if self.is_alive():
            self.join(timeout)

    def __del__(self):
        self.shutdown()

class MissingServersError(RuntimeError):
    def __init__(self):
        super().__init__("No servers hosting the model are online. ")
