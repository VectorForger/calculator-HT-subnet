import asyncio
import multiprocessing as mp
import os
import random
import signal
from typing import List, Sequence, Tuple

import pytest

import mesh
from mesh import P2P, PeerID, get_dht_time, get_logger
from mesh.dht import DHTID
from mesh.dht.crypto import RSASignatureValidator
from mesh.dht.protocol import DHTProtocol
from mesh.dht.validation import DHTRecord, RecordValidatorBase
from mesh.subnet.utils.key import generate_rsa_private_key_file, get_rsa_private_key
from mesh.utils.multiaddr import Multiaddr

logger = get_logger(__name__)

# pytest tests/test_dht_protocol_v2.py -rP

def maddrs_to_peer_ids(maddrs: List[Multiaddr]) -> List[PeerID]:
    return list({PeerID.from_base58(maddr["p2p"]) for maddr in maddrs})

test_identity_paths = []

def run_protocol_listener(
    dhtid: DHTID,
    maddr_conn: mp.connection.Connection,
    initial_peers: Sequence[Multiaddr],
    record_validator: RecordValidatorBase,
    identity_path: str,
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    p2p = loop.run_until_complete(P2P.create(initial_peers=initial_peers, identity_path=identity_path))
    visible_maddrs = loop.run_until_complete(p2p.get_visible_maddrs())

    protocol = loop.run_until_complete(
        DHTProtocol.create(
            p2p,
            dhtid,
            bucket_size=20,
            depth_modulo=5,
            num_replicas=3,
            wait_timeout=5,
            record_validator=record_validator
        )
    )

    logger.info(f"Started peer id={protocol.node_id} visible_maddrs={visible_maddrs}")

    for peer_id in maddrs_to_peer_ids(initial_peers):
        loop.run_until_complete(protocol.call_ping(peer_id))

    maddr_conn.send((p2p.peer_id, visible_maddrs))

    async def shutdown():
        await p2p.shutdown()
        logger.info(f"Finished peer id={protocol.node_id} maddrs={visible_maddrs}")
        loop.stop()

    loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(shutdown()))
    loop.run_forever()


def launch_protocol_listener(
    index: int, initial_peers: Sequence[Multiaddr] = ()
) -> Tuple[DHTID, mp.Process, PeerID, List[Multiaddr]]:
    remote_conn, local_conn = mp.Pipe()
    dht_id = DHTID.generate()
    identity_path = f"rsa_test_path_{index}.key"
    test_identity_paths.append(identity_path)
    private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(identity_path)
    loaded_key = get_rsa_private_key(identity_path)
    record_validator = RSASignatureValidator(loaded_key)

    process = mp.Process(
        target=run_protocol_listener,
        args=(dht_id, remote_conn, initial_peers, record_validator, identity_path),
        daemon=True
    )
    process.start()
    peer_id, visible_maddrs = local_conn.recv()

    return dht_id, process, peer_id, visible_maddrs

# def run_protocol_listener_v2(
#     dhtid: DHTID,
#     maddr_conn: mp.connection.Connection,
#     initial_peers: Sequence[Multiaddr],
#     record_validator: AuthorizerBase,
#     identity_path: str,
# ) -> None:
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)

#     p2p = loop.run_until_complete(P2P.create(initial_peers=initial_peers, identity_path=identity_path))
#     visible_maddrs = loop.run_until_complete(p2p.get_visible_maddrs())

#     protocol = loop.run_until_complete(
#         DHTProtocol.create(
#             p2p,
#             dhtid,
#             bucket_size=20,
#             depth_modulo=5,
#             num_replicas=3,
#             wait_timeout=5,
#             record_validator=[record_validator]
#         )
#     )

#     logger.info(f"Started peer id={protocol.node_id} visible_maddrs={visible_maddrs}")

#     for peer_id in maddrs_to_peer_ids(initial_peers):
#         loop.run_until_complete(protocol.call_ping(peer_id))

#     maddr_conn.send((p2p.peer_id, visible_maddrs))

#     async def shutdown():
#         await p2p.shutdown()
#         logger.info(f"Finished peer id={protocol.node_id} maddrs={visible_maddrs}")
#         loop.stop()

#     loop.add_signal_handler(signal.SIGTERM, lambda: loop.create_task(shutdown()))
#     loop.run_forever()


# def launch_protocol_listener_v2(
#     index: int, initial_peers: Sequence[Multiaddr] = ()
# ) -> Tuple[DHTID, mp.Process, PeerID, List[Multiaddr]]:
#     remote_conn, local_conn = mp.Pipe()
#     dht_id = DHTID.generate()
#     identity_path = f"rsa_test_path_{index}.key"
#     private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(identity_path)
#     loaded_key = get_rsa_private_key(identity_path)
#     record_validator = RSASignatureValidator(loaded_key)

#     process = mp.Process(
#         target=run_protocol_listener_v2,
#         args=(dht_id, remote_conn, initial_peers, record_validator, identity_path),
#         daemon=True
#     )
#     process.start()
#     peer_id, visible_maddrs = local_conn.recv()

#     return dht_id, process, peer_id, visible_maddrs

# pytest tests/test_dht_protocol_v2.py::test_dht_protocol -rP

@pytest.mark.forked
@pytest.mark.asyncio
async def test_dht_protocol():
    peer1_node_id, peer1_proc, peer1_id, peer1_maddrs = launch_protocol_listener(1)
    peer2_node_id, peer2_proc, peer2_id, peer2_maddrs = launch_protocol_listener(2, initial_peers=peer1_maddrs)

    peer_3_identity_path = f"rsa_test_path_{3}.key"
    test_identity_paths.append(peer_3_identity_path)
    private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(peer_3_identity_path)
    peer_3_loaded_key = get_rsa_private_key(peer_3_identity_path)
    peer_3_record_validator = RSASignatureValidator(peer_3_loaded_key)

    peer_id = DHTID.generate()
    p2p = await P2P.create(initial_peers=peer1_maddrs)
    protocol = await DHTProtocol.create(
        p2p,
        peer_id,
        bucket_size=20,
        depth_modulo=5,
        wait_timeout=5,
        num_replicas=3,
        client_mode=False,
        record_validator=peer_3_record_validator
    )
    logger.info(f"Self id={protocol.node_id}")

    assert peer1_node_id == await protocol.call_ping(peer1_id)

    key, value, expiration, subkey = DHTID.generate(), [random.random(), {"ololo": "pyshpysh"}], get_dht_time() + 1e3, peer_3_record_validator.local_public_key
    # record = DHTRecord(
    #     key=DHTID.generate(source="field_b").to_bytes(),
    #     subkey=subkey,
    #     value=value,
    #     expiration_time=expiration,
    # )
    record = DHTRecord(
        key=key.to_bytes(),
        subkey=DHTProtocol.serializer.dumps(peer_3_record_validator.local_public_key),
        value=DHTProtocol.serializer.dumps(777),
        expiration_time=mesh.get_dht_time() + 10,
    )
    # mimic sign_value
    signed_value = peer_3_record_validator.sign_value(record)
    assert peer_3_record_validator.validate(signed_value)
    store_ok = await protocol.call_store(
        peer1_id,
        keys=[key],
        values=[signed_value],
        expiration_time=expiration,
        subkeys=[subkey]
    )
    assert all(store_ok), "DHT rejected a trivial store"


    # for client_mode in [True, False]:  # note: order matters, this test assumes that first run uses client mode
    #     peer_id = DHTID.generate()
    #     p2p = await P2P.create(initial_peers=peer1_maddrs)
    #     protocol = await DHTProtocol.create(
    #         p2p, peer_id, bucket_size=20, depth_modulo=5, wait_timeout=5, num_replicas=3, client_mode=client_mode
    #     )
    #     logger.info(f"Self id={protocol.node_id}")

    #     assert peer1_node_id == await protocol.call_ping(peer1_id)

    #     key, value, expiration = DHTID.generate(), [random.random(), {"ololo": "pyshpysh"}], get_dht_time() + 1e3
    #     store_ok = await protocol.call_store(peer1_id, [key], [mesh.MSGPackSerializer.dumps(value)], expiration)
    #     assert all(store_ok), "DHT rejected a trivial store"

    #     # peer 1 must know about peer 2
    #     (recv_value_bytes, recv_expiration), nodes_found = (await protocol.call_find(peer1_id, [key]))[key]
    #     recv_value = mesh.MSGPackSerializer.loads(recv_value_bytes)
    #     (recv_id, recv_peer_id) = next(iter(nodes_found.items()))
    #     assert recv_id == peer2_node_id and recv_peer_id == peer2_id, (
    #         f"expected id={peer2_node_id}, peer={peer2_id} but got {recv_id}, {recv_peer_id}"
    #     )

    #     assert recv_value == value and recv_expiration == expiration, (
    #         f"call_find_value expected {value} (expires by {expiration}) "
    #         f"but got {recv_value} (expires by {recv_expiration})"
    #     )

    #     # peer 2 must know about peer 1, but not have a *random* nonexistent value
    #     dummy_key = DHTID.generate()
    #     empty_item, nodes_found_2 = (await protocol.call_find(peer2_id, [dummy_key]))[dummy_key]
    #     assert empty_item is None, "Non-existent keys shouldn't have values"
    #     (recv_id, recv_peer_id) = next(iter(nodes_found_2.items()))
    #     assert recv_id == peer1_node_id and recv_peer_id == peer1_id, (
    #         f"expected id={peer1_node_id}, peer={peer1_id} but got {recv_id}, {recv_peer_id}"
    #     )

    #     # cause a non-response by querying a nonexistent peer
    #     assert not await protocol.call_find(PeerID.from_base58("fakeid"), [key])

    #     # store/get a dictionary with sub-keys
    #     nested_key, subkey1, subkey2 = DHTID.generate(), "foo", "bar"
    #     value1, value2 = [random.random(), {"ololo": "pyshpysh"}], "abacaba"
    #     assert await protocol.call_store(
    #         peer1_id,
    #         keys=[nested_key],
    #         values=[mesh.MSGPackSerializer.dumps(value1)],
    #         expiration_time=[expiration],
    #         subkeys=[subkey1],
    #     )
    #     assert await protocol.call_store(
    #         peer1_id,
    #         keys=[nested_key],
    #         values=[mesh.MSGPackSerializer.dumps(value2)],
    #         expiration_time=[expiration + 5],
    #         subkeys=[subkey2],
    #     )
    #     (recv_dict, recv_expiration), nodes_found = (await protocol.call_find(peer1_id, [nested_key]))[nested_key]
    #     assert isinstance(recv_dict, DictionaryDHTValue)
    #     assert len(recv_dict.data) == 2 and recv_expiration == expiration + 5
    #     assert recv_dict.data[subkey1] == (protocol.serializer.dumps(value1), expiration)
    #     assert recv_dict.data[subkey2] == (protocol.serializer.dumps(value2), expiration + 5)

    #     if not client_mode:
    #         await p2p.shutdown()

    peer1_proc.terminate()
    peer2_proc.terminate()

    for identiy_paths in test_identity_paths:
        os.remove(identiy_paths)
