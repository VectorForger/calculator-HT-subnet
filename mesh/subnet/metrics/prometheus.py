import datetime
import time
from functools import partial
from multiprocessing import Process
from threading import Thread
from typing import Dict, List

from prometheus_client import Gauge, start_http_server

from mesh import DHT, PeerID
from mesh.subnet.data_structures import RemoteModuleInfo, ServerState
from mesh.subnet.metrics.config import INITIAL_PEERS, UPDATE_PERIOD
from mesh.subnet.utils.consensus import ConsensusScores
from mesh.subnet.utils.dht import get_node_infos
from mesh.substrate.chain_functions import Hypertensor
from mesh.utils.multiaddr import Multiaddr
from mesh.utils.p2p_utils import check_reachability_parallel, extract_peer_ip_info, get_peers_ips


class MetricsServer:
    def __init__(
        self,
        hypertensor: Hypertensor,
        dht: DHT,
        port: int = 8000
    ):
        self.hypertensor = hypertensor
        self.dht = dht
        self.port = port
        self.process = None

        self.heartbeat = Gauge('heartbeat', 'Heartbeat')
        self.subnet_consensus_data = Gauge('subnet_consensus_data', 'Subnet Consensus')
        self.onchain_consensus_data = Gauge('onchain_consensus_data', 'Onchain Consensus')

    def start(self):
        self.process = Process(target=self._run)
        self.process.start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.join()

    def _run(self):
        start_http_server(self.port)
        print(f"[Metrics] Prometheus exporter started on port {self.port}")

        # Start separate threads for each interval-specific updater
        Thread(target=self._heartbeat_metrics, daemon=True).start()
        Thread(target=self._onchain_consensus, daemon=True).start()
        Thread(target=self._subnet_consensus, daemon=True).start()

        # Keep the process alive
        while self.running:
            time.sleep(1)

    def _heartbeat_metrics(self):
        while self.running:
            self.heartbeat.set(self.get_heartbeat_metrics())
            time.sleep(60)

    def _onchain_consensus(self):
        while self.running:
            self.inference_latency_gauge.set(self.get_onchain_consensus())
            time.sleep(100)

    def _subnet_consensus(self):
        while self.running:
            self.cache_hit_ratio.set(self.get_subnet_consensus())
            time.sleep(600)

    def get_heartbeat_metrics(self) -> int:
        start_time = time.perf_counter()
        bootstrap_peer_ids = []
        for addr in INITIAL_PEERS:
            peer_id = PeerID.from_base58(Multiaddr(addr)["p2p"])
            if peer_id not in bootstrap_peer_ids:
                bootstrap_peer_ids.append(peer_id)

        reach_infos = self.dht.run_coroutine(partial(check_reachability_parallel, bootstrap_peer_ids))
        bootstrap_states = ["online" if reach_infos[peer_id]["ok"] else "unreachable" for peer_id in bootstrap_peer_ids]

        all_servers: List[RemoteModuleInfo] = []
        hoster_module_infos = get_node_infos(self.dht, "hoster", latest=True)
        all_servers.append(hoster_module_infos)
        validator_module_infos = get_node_infos(self.dht, "validator", latest=True)
        all_servers.append(validator_module_infos)
        online_servers = [peer_id for peer_id, span in all_servers.items() if span.state == ServerState.ONLINE]

        reach_infos.update(self.dht.run_coroutine(partial(check_reachability_parallel, online_servers, fetch_info=True)))
        peers_info = {str(peer.peer_id): {"location": extract_peer_ip_info(str(peer.addrs[0])), "multiaddrs": [str(multiaddr) for multiaddr in peer.addrs]} for peer in self.dht.run_coroutine(get_peers_ips)}

        metrics = []
        for server in all_servers:
            peer_id = server.peer_id
            reachable = reach_infos[peer_id]["ok"] if peer_id in reach_infos else True
            state = server.server.state.name.lower() if reachable else "unreachable"
            server_info = server.server
            role = server_info.role
            public_name = server_info.public_name
            location = peers_info.get(str(peer_id), None)
            latitude = location['lat'] if location is not None else None
            longitude = location['lon'] if location is not None else None
            country = location['country'] if location is not None else None
            region = location['region'] if location is not None else None

            data = {
                "peer_id": peer_id,
                "state": state,
                "role": role.name,
                "public_name": public_name,
                "latitude": latitude,
                "longitude": longitude,
                "country": country,
                "region": region,
            }
            metrics.append(data)

        reachability_issues = [
            dict(peer_id=peer_id, err=info["error"]) for peer_id, info in sorted(reach_infos.items()) if not info["ok"]
        ]

        return dict(
            bootstrap_states=bootstrap_states,
            metrics=metrics,
            reachability_issues=reachability_issues,
            last_updated=datetime.datetime.now(datetime.timezone.utc),
            next_update=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=UPDATE_PERIOD),
            update_period=UPDATE_PERIOD,
            update_duration=time.perf_counter() - start_time
        )

    def get_onchain_consensus(self):
        ...

    def get_subnet_consensus(self):
        ...

    def score_hosters(self, current_epoch: int) -> Dict[str, float]:
        ...

    def score_validators(self, current_epoch: int) -> Dict[str, float]:
        ...

    def normalize_scores(self, scores: Dict[str, float], target_total: float) -> Dict[str, float]:
        total = sum(scores.values())
        if total == 0:
            return {peer_id: 0.0 for peer_id in scores}
        return {
            peer_id: (score / total) * target_total
            for peer_id, score in scores.items()
        }

    def filter_merged_scores(self, scores: Dict[str, float]) -> List[ConsensusScores]:
        """
        Filter scores against the blockchain activated subnet nodes
        """
        return scores
