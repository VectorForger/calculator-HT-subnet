import dataclasses
import time
from typing import List, Optional

from mesh import get_logger
from mesh.subnet.data_structures import RemoteInfo, RemoteModuleInfo, ServerState
from mesh.subnet.utils.dht import compute_spans

logger = get_logger(__name__)


@dataclasses.dataclass
class RemoteServerInfo:
    """
    A dataclass that stores general information about which servers hold any given layer;
    - updated by RemoteSequenceManager in a background thread
    - accessed by routing strategies in .on_update
    :note: this class should *not* be modified by RoutingStrategy.on_update to avoid interference between strategies;
     Any metadata specific to one routing strategy, it should be stored inside that strategy. Any information that
     is used by most routing strategies should be moved from said strategies to this class.
    """

    server_infos: List[RemoteModuleInfo]
    servers_by_priority: List[RemoteInfo]
    last_updated_time: Optional[float]

    @classmethod
    def make_empty(cls) -> "RemoteServerInfo":
        return cls([], [], last_updated_time=None)

    def __getitem__(self, ix: slice):
        assert isinstance(ix, slice)
        server_infos = self.server_infos[ix]
        servers_by_priority = self._sort_spans(server_infos)
        return RemoteServerInfo(
            server_infos, servers_by_priority, self.last_updated_time
        )

    def update_(self, new_server_infos: List[RemoteModuleInfo]):
        all_infos = self.server_infos + new_server_infos

        # Deduplicate by peer_id (most recent wins)
        deduped_by_peer = {}
        for info in all_infos:
            deduped_by_peer[info.peer_id] = info  # overwrites earlier ones

        self.server_infos = list(deduped_by_peer.values())
        self.servers_by_priority = self._sort_spans(self.server_infos)
        self.last_updated_time = time.perf_counter()

    @staticmethod
    def _sort_spans(server_infos: List[RemoteModuleInfo]):
        servers_by_priority = list(compute_spans(server_infos, min_state=ServerState.ONLINE).values())
        servers_by_priority.sort(key=lambda span: span.length, reverse=True)

        return servers_by_priority
