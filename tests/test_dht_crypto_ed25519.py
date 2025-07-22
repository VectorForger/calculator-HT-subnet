import dataclasses
import multiprocessing as mp
import pickle

import pytest

import mesh
from mesh.dht.crypto import Ed25519SignatureValidator
from mesh.dht.node import DHTNode
from mesh.dht.validation import DHTRecord, DHTRecordRequestType
from mesh.utils.crypto import Ed25519PrivateKey
from mesh.utils.timed_storage import get_dht_time

# pytest tests/test_dht_crypto_ed25519.py::test_ed25519_signature_validator -rP

def test_ed25519_signature_validator():
    receiver_validator = Ed25519SignatureValidator()
    sender_validator = Ed25519SignatureValidator(Ed25519PrivateKey())
    mallory_validator = Ed25519SignatureValidator(Ed25519PrivateKey())

    plain_record = DHTRecord(key=b"key", subkey=b"subkey", value=b"value", expiration_time=get_dht_time() + 10)
    protected_records = [
        dataclasses.replace(plain_record, key=plain_record.key + sender_validator.local_public_key),
        dataclasses.replace(plain_record, subkey=plain_record.subkey + sender_validator.local_public_key),
    ]

    # test 1: Non-protected record (no signature added)
    assert sender_validator.sign_value(plain_record) == plain_record.value
    assert receiver_validator.validate(plain_record, DHTRecordRequestType.POST)

    # test 2: Correct signatures
    signed_records = [
        dataclasses.replace(record, value=sender_validator.sign_value(record)) for record in protected_records
    ]
    for record in signed_records:
        assert receiver_validator.validate(record, DHTRecordRequestType.POST)
        assert receiver_validator.strip_value(record) == b"value"

    # test 3: Invalid signatures
    signed_records = protected_records  # Without signature
    signed_records += [
        dataclasses.replace(record, value=record.value + b"[signature:INVALID_BYTES]") for record in protected_records
    ]  # With invalid signature
    signed_records += [
        dataclasses.replace(record, value=mallory_validator.sign_value(record)) for record in protected_records
    ]  # With someone else's signature
    for record in signed_records:
        assert not receiver_validator.validate(record, DHTRecordRequestType.POST)

# pytest tests/test_dht_crypto_ed25519.py::test_cached_key -rP

def test_cached_key():
    first_validator = Ed25519SignatureValidator()
    second_validator = Ed25519SignatureValidator()
    assert first_validator.local_public_key == second_validator.local_public_key

    third_validator = Ed25519SignatureValidator(Ed25519PrivateKey())
    assert first_validator.local_public_key != third_validator.local_public_key

# pytest tests/test_dht_crypto_ed25519.py::test_validator_instance_is_picklable -rP

def test_validator_instance_is_picklable():
    # Needs to be picklable because the validator instance may be sent between processes

    original_validator = Ed25519SignatureValidator()
    unpickled_validator = pickle.loads(pickle.dumps(original_validator))

    # To check that the private key was pickled and unpickled correctly, we sign a record
    # with the original public key using the unpickled validator and then validate the signature

    record = DHTRecord(
        key=b"key",
        subkey=b"subkey" + original_validator.local_public_key,
        value=b"value",
        expiration_time=get_dht_time() + 10,
    )
    signed_record = dataclasses.replace(record, value=unpickled_validator.sign_value(record))

    assert b"[signature:" in signed_record.value
    assert original_validator.validate(signed_record, DHTRecordRequestType.POST)
    assert unpickled_validator.validate(signed_record, DHTRecordRequestType.POST)


def get_signed_record(conn: mp.connection.Connection) -> DHTRecord:
    validator = conn.recv()
    record = conn.recv()

    record = dataclasses.replace(record, value=validator.sign_value(record))

    conn.send(record)
    return record

# pytest tests/test_dht_crypto_ed25519.py::test_dhtnode_signatures -rP

@pytest.mark.forked
@pytest.mark.asyncio
async def test_dhtnode_signatures():
    alice = await DHTNode.create(record_validator=Ed25519SignatureValidator())
    initial_peers = await alice.get_visible_maddrs()
    bob = await DHTNode.create(record_validator=Ed25519SignatureValidator(Ed25519PrivateKey()), initial_peers=initial_peers)
    mallory = await DHTNode.create(
        record_validator=Ed25519SignatureValidator(Ed25519PrivateKey()), initial_peers=initial_peers
    )

    key = b"key"
    subkey = b"protected_subkey" + bob.protocol.record_validator.local_public_key

    assert await bob.store(key, b"true_value", mesh.get_dht_time() + 10, subkey=subkey)
    assert (await alice.get(key, latest=True)).value[subkey].value == b"true_value"

    store_ok = await mallory.store(key, b"fake_value", mesh.get_dht_time() + 10, subkey=subkey)
    assert not store_ok
    assert (await alice.get(key, latest=True)).value[subkey].value == b"true_value"

    assert await bob.store(key, b"updated_true_value", mesh.get_dht_time() + 10, subkey=subkey)
    assert (await alice.get(key, latest=True)).value[subkey].value == b"updated_true_value"

    await bob.shutdown()  # Bob has shut down, now Mallory is the single peer of Alice

    store_ok = await mallory.store(key, b"updated_fake_value", mesh.get_dht_time() + 10, subkey=subkey)
    assert not store_ok
    assert (await alice.get(key, latest=True)).value[subkey].value == b"updated_true_value"

# pytest tests/test_dht_crypto_ed25519.py::test_signing_in_different_process -rP

def test_signing_in_different_process():
    parent_conn, child_conn = mp.Pipe()
    process = mp.Process(target=get_signed_record, args=[child_conn])
    process.start()

    validator = Ed25519SignatureValidator()
    parent_conn.send(validator)

    record = DHTRecord(
        key=b"key", subkey=b"subkey" + validator.local_public_key, value=b"value", expiration_time=get_dht_time() + 10
    )
    parent_conn.send(record)

    signed_record = parent_conn.recv()
    assert b"[signature:" in signed_record.value
    assert validator.validate(signed_record, DHTRecordRequestType.POST)
