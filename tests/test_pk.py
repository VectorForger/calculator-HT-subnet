import os

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from mesh import PeerID
from mesh.subnet.utils.key import (
    extract_ed25519_peer_id_from_ssh,
    extract_rsa_peer_id_from_ssh,
    generate_ed25519_private_key_file,
    generate_rsa_private_key_file,
    get_ed25519_peer_id,
    get_ed25519_private_key,
    get_rsa_peer_id,
    get_rsa_private_key,
)
from mesh.utils.crypto import Ed25519PrivateKey, Ed25519PublicKey, RSAPrivateKey

# pytest tests/test_pk.py -rP


# pytest tests/test_pk.py::test_get_ed25519_private_key -rP
# pytest tests/test_pk.py::test_get_ed25519_private_key --log-cli-level=DEBUG

def test_get_ed25519_private_key():
    test_path = "ed25519_test_path.key"
    private_key, public_key, raw_private_key, public_key_bytes, combined_key_bytes, peer_id = generate_ed25519_private_key_file(test_path)

    # Load using our function
    loaded_key = get_ed25519_private_key(test_path)

    assert isinstance(loaded_key, Ed25519PrivateKey)
    assert loaded_key.get_public_key().to_raw_bytes() == public_key_bytes
    assert loaded_key.to_bytes() == raw_private_key

    # Sign/verify to check it works
    message = b"hello"
    signature = loaded_key.sign(message)
    loaded_key.get_public_key().verify(signature, message)

    pubkey = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
    pubkey = Ed25519PublicKey(pubkey)
    ed25519_peer_id_from_bytes = get_ed25519_peer_id(pubkey)
    assert ed25519_peer_id_from_bytes == peer_id

    with open(test_path, "rb") as f:
        gen_peer_id = PeerID.from_identity_ed25519(f.read())
        assert gen_peer_id == peer_id

    extracted_rsa_peer_id = extract_ed25519_peer_id_from_ssh(pubkey.to_bytes())
    assert extracted_rsa_peer_id == peer_id

    os.remove(test_path)

# pytest tests/test_pk.py::test_get_rsa_private_key -rP

def test_get_rsa_private_key():
    test_path = "rsa_test_path.key"
    private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(test_path)

    loaded_key = get_rsa_private_key(test_path)

    assert isinstance(loaded_key, RSAPrivateKey)
    assert loaded_key.get_public_key().to_bytes() == public_key.to_bytes()
    assert loaded_key.to_bytes() == private_key

    # Sign/verify to check it works
    message = b"hello"
    signature = loaded_key.sign(message)
    loaded_key.get_public_key().verify(signature, message)

    rsa_peer_id_from_bytes = get_rsa_peer_id(public_bytes)
    assert rsa_peer_id_from_bytes == peer_id

    extracted_rsa_peer_id = extract_rsa_peer_id_from_ssh(public_key.to_bytes())
    assert extracted_rsa_peer_id == peer_id

    with open(test_path, "rb") as f:
        gen_peer_id = PeerID.from_identity_rsa(f.read())
        assert gen_peer_id == peer_id

    os.remove(test_path)
