from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

import mesh
from mesh import DHT, get_dht_time
from mesh.dht.crypto import RSASignatureValidator
from mesh.dht.validation import RecordValidatorBase
from mesh.subnet.consensus.consensus import Consensus
from mesh.subnet.data_structures import ServerClass, ServerInfo, ServerState
from mesh.subnet.protocols.mock_protocol import MockProtocol
from mesh.subnet.reachability import ReachabilityProtocol, check_direct_reachability
from mesh.subnet.utils.dht import declare_node, get_node_infos
from mesh.subnet.utils.key import get_rsa_private_key
from mesh.subnet.utils.ping import PingAggregator
from mesh.subnet.utils.random import sample_up_to
from mesh.substrate.chain_functions import Hypertensor
from mesh.utils.logging import get_logger
from mesh.utils.timed_storage import MAX_DHT_TIME_DISCREPANCY_SECONDS

logger = get_logger(__name__)

DEFAULT_NUM_WORKERS = 8

class Server:
    def __init__(
        self,
        *,
        initial_peers: List[str],
        public_name: Optional[str] = None,
        role: ServerClass,
        update_period: float = 60,
        expiration: Optional[float] = None,
        reachable_via_relay: Optional[bool] = None,
        use_relay: bool = True,
        use_auto_relay: bool = True,
        subnet_id: Optional[int] = None,
        subnet_node_id: Optional[int] = None,
        hypertensor: Optional[Hypertensor] = None,
        **kwargs,
    ):
        """
        Create a server
        """
        self.update_period = update_period
        if expiration is None:
            expiration = max(2 * update_period, MAX_DHT_TIME_DISCREPANCY_SECONDS)
        self.expiration = expiration

        self.initial_peers = initial_peers
        self.announce_maddrs = kwargs.get('announce_maddrs')  # Returns None if 'my_key' not present

        self.subnet_id = subnet_id
        self.subnet_node_id = subnet_node_id
        self.hypertensor = hypertensor

        # Connect to DHT
        if reachable_via_relay is None:
            is_reachable = check_direct_reachability(initial_peers=initial_peers, use_relay=False, **kwargs)
            reachable_via_relay = is_reachable is False  # if can't check reachability (returns None), run a full peer
            logger.info(f"This server is accessible {'via relays' if reachable_via_relay else 'directly'}")

        identity_path = kwargs.get('identity_path', None)
        pk = get_rsa_private_key(identity_path)

        self.rsa_signature_validator = RSASignatureValidator(pk)
        self.record_validators=[self.rsa_signature_validator]

        self.dht = DHT(
            initial_peers=initial_peers,
            start=True,
            num_workers=DEFAULT_NUM_WORKERS,
            use_relay=use_relay,
            use_auto_relay=use_auto_relay,
            client_mode=reachable_via_relay,
            record_validators=self.record_validators,
            **kwargs,
            # **dict(kwargs, authorizer=authorizer)
        )
        self.reachability_protocol = ReachabilityProtocol.attach_to_dht(self.dht) if not reachable_via_relay else None

        visible_maddrs_str = [str(a) for a in self.dht.get_visible_maddrs()]

        logger.info(f"Running a server on {visible_maddrs_str}")

        throughput_info = {"throughput": 1.0}
        self.server_info = ServerInfo(
            state=ServerState.JOINING,
            role=role,
            public_name=public_name,
            version="1.0.0",
            using_relay=reachable_via_relay,
            **throughput_info,
        )

        self.mock_protocol = None
        self.module_container = None
        self.consensus = None
        self.stop = threading.Event()

    def run(self):
        """
        Start protocols here

        self.protocol = MockProtocol(dht=self.dht)
        """
        self.mock_protocol = MockProtocol(
            dht=self.dht,
            subnet_id=self.subnet_id,
            hypertensor=self.hypertensor,
            authorizer=None,
            start=True
        )

        self.module_container = ModuleAnnouncerThread(
            dht=self.dht,
            server_info=self.server_info,
            update_period=self.update_period,
            expiration=self.expiration,
            start=True
        )

        # self.consensus = ConsensusThread(
        #     dht=self.dht,
        #     server_info=self.server_info,
        #     subnet_id=self.subnet_id,
        #     subnet_node_id=self.subnet_node_id,
        #     record_validator=self.rsa_signature_validator,
        #     hypertensor=self.hypertensor,
        #     start=True
        # )

        """
        Keep server running forever
        """
        self.stop.wait()

    def shutdown(self, timeout: Optional[float] = 5):
        logger.info("Shutting down Server, wait to shutdown properly")
        self.stop.set()

        if self.mock_protocol is not None:
            self.mock_protocol.shutdown()

        if self.reachability_protocol is not None:
            self.reachability_protocol.shutdown()

        if self.consensus is not None:
            self.consensus.shutdown()

        self.dht.shutdown()
        self.dht.join()

class ModuleAnnouncerThread(threading.Thread):
    def __init__(
        self,
        dht: DHT,
        server_info: ServerInfo,
        update_period: float,
        expiration: Optional[float] = None,
        start: bool = True,
    ):
        super().__init__()
        self.dht = dht

        server_info.state = ServerState.JOINING
        self.dht_announcer = ModuleHeartbeatThread(
            dht,
            server_info,
            update_period=update_period,
            expiration=expiration,
            daemon=True,
        )
        self.role = server_info.role
        self.dht_announcer.start()
        logger.info("Announced to the DHT that we are joining")

        if start:
            self.run()

    def run(self):
        logger.info("Announcing node is online")
        self.dht_announcer.announce(ServerState.ONLINE)

    def shutdown(self):
        """
        Gracefully terminate the container, process-safe.
        """
        self.dht_announcer.announce(ServerState.OFFLINE)
        logger.info("Announced to the DHT that we are exiting")

        self.join()
        logger.info("Module shut down successfully")

class ConsensusThread(threading.Thread):
    def __init__(
        self,
        dht: DHT,
        server_info: ServerInfo,
        subnet_id: int,
        subnet_node_id: int,
        record_validator: RecordValidatorBase,
        hypertensor: Hypertensor,
        start: bool = True,
    ):
        super().__init__()
        self.dht = dht
        self.server_info = server_info
        self.subnet_id = subnet_id
        self.subnet_node_id = subnet_node_id
        self.rsa_signature_validator = record_validator
        self.hypertensor = hypertensor
        self.consensus = None
        self.validator = None

        if start:
            self.run()

    def run(self) -> None:
        """
        Add any other logic the Consensus class requires to run,
        such as differ node role classes, etc.

        self.validator = Validator(
            role=self.server_info.role,
            dht=self.dht,
            record_validator=self.rsa_signature_validator,
            hypertensor=self.hypertensor,
        )

        See template implementation
        """

        self.consensus = Consensus(
            dht=self.dht,
            subnet_id=self.subnet_id,
            subnet_node_id=self.subnet_node_id,
            role=self.server_info.role,
            record_validator=self.rsa_signature_validator,
            hypertensor=self.hypertensor,
            start=True,
        )

    def shutdown(self):
        if self.consensus is not None:
            self.consensus.shutdown()

        if self.validator is not None:
            self.validator.shutdown()

        self.join()

class ModuleHeartbeatThread(threading.Thread):
    """Periodically announces server is live before expiration of storage, visible to all DHT peers"""

    def __init__(
        self,
        dht: DHT,
        server_info: ServerInfo,
        *,
        update_period: float,
        expiration: float,
        max_pinged: int = 5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dht = dht
        self.server_info = server_info

        self.update_period = update_period
        self.expiration = expiration
        self.trigger = threading.Event()

        self.max_pinged = max_pinged
        self.ping_aggregator = PingAggregator(self.dht)

    def run(self) -> None:
        """
        Start heartbeat

        - Tell the network you're still hear
        - Ping other nodes
        """
        while True:
            start_time = time.perf_counter()

            if self.server_info.state != ServerState.OFFLINE:
                self._ping_next_servers()
                self.server_info.next_pings = {
                    peer_id.to_base58(): rtt for peer_id, rtt in self.ping_aggregator.to_dict().items()
                }
            else:
                self.server_info.next_pings = None  # No need to ping if we're disconnecting

            declare_node(
                dht=self.dht,
                key="validator",
                server_info=self.server_info,
                expiration_time=get_dht_time() + self.expiration,
            )

            if self.server_info.state == ServerState.OFFLINE:
                break

            """
            If you want to host multiple applications in one DHT or run a bootstrap node that acts as an entry 
            point to multiple subnets, you can do so in the DHTStorage mechanism.

            Without a clear understanding of how DHTs or DHTStorage, we suggest isolating subnets and not using this.

            if not self.dht_prefix.startswith("_"):
                self.dht.store(
                    key="_team_name_here.subnets",
                    subkey=self.dht_prefix,
                    value=self.model_info.to_dict(),
                    expiration_time=get_dht_time() + self.expiration,
                )
            """

            delay = self.update_period - (time.perf_counter() - start_time)
            if delay < 0:
                logger.warning(
                    f"Declaring node to DHT takes more than --update_period, consider increasing it (currently {self.update_period})"
                )
            self.trigger.wait(max(delay, 0))
            self.trigger.clear()

    def announce(self, state: ServerState) -> None:
        self.server_info.state = state
        self.trigger.set()
        if state == ServerState.OFFLINE:
            self.join()

    def _ping_next_servers(self) -> Dict[mesh.PeerID, float]:
        module_infos = get_node_infos(
            self.dht,
            uid="hoster",
            latest=True
        )
        if len(module_infos) == 0:
            return
        middle_servers = {info.peer_id for info in module_infos}
        pinged_servers = set(sample_up_to(middle_servers, self.max_pinged))
        # discard self
        pinged_servers.discard(self.dht.peer_id)
        self.ping_aggregator.ping(list(pinged_servers))
