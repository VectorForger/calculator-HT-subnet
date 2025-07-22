import asyncio
import multiprocessing as mp
import random
import signal
import threading
from typing import Dict, List, Optional, Tuple

from mesh.dht import DHT
from mesh.dht.node import DHTID, DHTNode
from mesh.dht.validation import RecordValidatorBase
from mesh.p2p import PeerID
from mesh.utils.multiaddr import Multiaddr


def run_node(initial_peers: List[Multiaddr], info_queue: mp.Queue, **kwargs):
    if asyncio.get_event_loop().is_running():
        asyncio.get_event_loop().stop()  # if we're in jupyter, get rid of its built-in event loop
        asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    node = loop.run_until_complete(DHTNode.create(initial_peers=initial_peers, **kwargs))
    maddrs = loop.run_until_complete(node.get_visible_maddrs())

    info_queue.put((node.node_id, node.peer_id, maddrs))

    async def shutdown():
        await node.shutdown()
        loop.stop()

    loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(shutdown()))
    loop.run_forever()


def launch_swarm_in_separate_processes(
    n_peers: int, n_sequential_peers: int, **kwargs
) -> Tuple[List[mp.Process], Dict[PeerID, DHTID], List[List[Multiaddr]]]:
    assert n_sequential_peers < n_peers, (
        "Parameters imply that first n_sequential_peers of n_peers will be run sequentially"
    )

    processes = []
    dht = {}
    swarm_maddrs = []

    info_queue = mp.Queue()
    info_lock = mp.RLock()

    for _ in range(n_sequential_peers):
        initial_peers = random.choice(swarm_maddrs) if swarm_maddrs else []

        proc = mp.Process(target=run_node, args=(initial_peers, info_queue), kwargs=kwargs, daemon=True)
        proc.start()
        processes.append(proc)

        node_id, peer_id, peer_maddrs = info_queue.get()
        dht[peer_id] = node_id
        swarm_maddrs.append(peer_maddrs)

    def collect_info():
        while True:
            node_id, peer_id, peer_maddrs = info_queue.get()
            with info_lock:
                dht[peer_id] = node_id
                swarm_maddrs.append(peer_maddrs)

                if len(dht) == n_peers:
                    break

    collect_thread = threading.Thread(target=collect_info)
    collect_thread.start()

    for _ in range(n_peers - n_sequential_peers):
        with info_lock:
            initial_peers = random.choice(swarm_maddrs)

        proc = mp.Process(target=run_node, args=(initial_peers, info_queue), kwargs=kwargs, daemon=True)
        proc.start()
        processes.append(proc)

    collect_thread.join()

    return processes, dht, swarm_maddrs

def launch_swarm_in_separate_processes_with_validators(
    n_peers: int,
    n_sequential_peers: int,
    record_validators: List[RecordValidatorBase],
    identity_paths: List[str],
    **kwargs
) -> Tuple[List[mp.Process], Dict[PeerID, DHTID], List[List[Multiaddr]]]:
    assert n_sequential_peers < n_peers, (
        "Parameters imply that first n_sequential_peers of n_peers will be run sequentially"
    )

    assert len(record_validators) == len(identity_paths), (
        "Validators and identity paths must be equal in length"
    )

    processes = []
    dht = {}
    swarm_maddrs = []

    info_queue = mp.Queue()
    info_lock = mp.RLock()

    for _ in range(n_sequential_peers):
        initial_peers = random.choice(swarm_maddrs) if swarm_maddrs else []

        proc = mp.Process(target=run_node, args=(initial_peers, info_queue), kwargs=kwargs, daemon=True)
        proc.start()
        processes.append(proc)

        node_id, peer_id, peer_maddrs = info_queue.get()
        dht[peer_id] = node_id
        swarm_maddrs.append(peer_maddrs)

    def collect_info():
        while True:
            node_id, peer_id, peer_maddrs = info_queue.get()
            with info_lock:
                dht[peer_id] = node_id
                swarm_maddrs.append(peer_maddrs)

                if len(dht) == n_peers:
                    break

    collect_thread = threading.Thread(target=collect_info)
    collect_thread.start()

    for _ in range(n_peers - n_sequential_peers):
        with info_lock:
            initial_peers = random.choice(swarm_maddrs)

        proc = mp.Process(target=run_node, args=(initial_peers, info_queue), kwargs=kwargs, daemon=True)
        proc.start()
        processes.append(proc)

    collect_thread.join()

    return processes, dht, swarm_maddrs

async def launch_star_shaped_swarm(n_peers: int, **kwargs) -> List[DHTNode]:
    nodes = [await DHTNode.create(**kwargs)]
    initial_peers = await nodes[0].get_visible_maddrs()
    nodes += await asyncio.gather(*[DHTNode.create(initial_peers=initial_peers, **kwargs) for _ in range(n_peers - 1)])
    return nodes

async def launch_star_shaped_swarms_with_record_validators(record_validators: List[RecordValidatorBase], **kwargs) -> List[DHTNode]:
    nodes = [await DHTNode.create(**kwargs)]
    initial_peers = await nodes[0].get_visible_maddrs()
    nodes += await asyncio.gather(*[DHTNode.create(initial_peers=initial_peers, **kwargs) for _ in range(len(record_validators) - 1)])
    return nodes

def launch_dht_instances(n_peers: int, **kwargs) -> List[DHT]:
    dhts = [DHT(start=True, **kwargs)]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(DHT(initial_peers=initial_peers, start=True, await_ready=False, **kwargs) for _ in range(n_peers - 1))
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_instances_with_record_validators(
    record_validators: List[RecordValidatorBase],
    identity_paths: List[str],
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs, with one RecordValidatorBase per peer
    """
    dhts = [DHT(start=True, record_validators=[record_validators[0]], identity_path=identity_paths[0], **kwargs)]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=[record_validators[i]],
            identity_path=identity_paths[i],
            start=True,
            await_ready=False,
            **kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_instances_with_record_validators2(
    record_validators: List[List[RecordValidatorBase]],
    identity_paths: List[str],
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs, with one RecordValidatorBase per peer
    """
    dhts = [DHT(start=True, record_validators=record_validators[0], identity_path=identity_paths[0], **kwargs)]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=record_validators[i],
            identity_path=identity_paths[i],
            start=True,
            await_ready=False,
            **kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_instances_with_record_validators_bootstrap_no_kwargs(
    record_validators: List[RecordValidatorBase],
    identity_paths: List[str],
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs, with one RecordValidatorBase per peer
    """
    dhts = [DHT(start=True, record_validators=[record_validators[0]], identity_path=identity_paths[0])]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=[record_validators[i]],
            identity_path=identity_paths[i],
            start=True,
            await_ready=False,
            **kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_with_clients(
    record_validators: List[RecordValidatorBase],
    identity_paths: List[str],
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs, with one RecordValidatorBase per peer
    """
    dhts = [DHT(start=True, record_validators=[record_validators[0]], identity_path=identity_paths[0])]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=[record_validators[i]],
            identity_path=identity_paths[i],
            start=True,
            await_ready=False,
            client_mode=True,
            **kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_instances_with_record_validators_and_authorizers(
    record_validators: List[RecordValidatorBase],
    authorizers: List[RecordValidatorBase],
    identity_paths: List[str],
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs, with one RecordValidatorBase per peer
    """
    dhts = [DHT(start=True, record_validators=[record_validators[0]], authorizer=authorizers[0], identity_path=identity_paths[0], **kwargs)]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=[record_validators[i]],
            identity_path=identity_paths[i],
            authorizer=authorizers[i],
            start=True,
            await_ready=False,
            **kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts

def launch_dht_instances_with_record_validators_kwargs(
    record_validators: List[RecordValidatorBase],
    identity_paths: List[str],
    bootstrap_kwargs: Optional[dict] = None,
    peer_kwargs: Optional[dict] = None,
    **kwargs
) -> List[DHT]:
    """
    Launch DHTs with one RecordValidatorBase per peer.
    The first DHT is a bootstrap node with optional extra kwargs.
    The rest are peer nodes with their own optional extra kwargs.
    All nodes share common **kwargs unless overridden.
    """
    bootstrap_kwargs = {**kwargs, **(bootstrap_kwargs or {})}
    peer_kwargs = {**kwargs, **(peer_kwargs or {})}

    dhts = [DHT(start=True, record_validators=[record_validators[0]], identity_path=identity_paths[0], **bootstrap_kwargs)]
    initial_peers = dhts[0].get_visible_maddrs()

    dhts.extend(
        DHT(
            initial_peers=initial_peers,
            record_validators=[record_validators[i]],
            identity_path=identity_paths[i],
            start=True,
            await_ready=False,
            **peer_kwargs
        ) for i in range(1, len(record_validators))
    )
    for process in dhts[1:]:
        process.wait_until_ready()

    return dhts
