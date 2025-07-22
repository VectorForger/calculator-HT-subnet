import os
from typing import List

import pytest

from mesh.dht.crypto import RSASignatureValidator
from mesh.subnet.utils.key import generate_rsa_private_key_file, get_rsa_private_key

from test_utils.dht_swarms import (
    launch_dht_with_clients,
)

# pytest tests/test_dht_client.py::test_dht_same_clients -rP

@pytest.mark.forked
def test_dht_same_clients(n_peers=10):
    peers_len = 5

    test_paths = []
    record_validators: List[RSASignatureValidator] = []
    for i in range(peers_len):
        test_path = f"rsa_test_path_{i}.key"
        root_path = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(root_path, test_path)

        if not os.path.exists(full_path):
            private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(test_path)

        test_paths.append(test_path)
        loaded_key = get_rsa_private_key(test_path)
        record_validator = RSASignatureValidator(loaded_key)
        record_validators.append(record_validator)

        if i > 0:
            test_paths.append(test_path)
            record_validators.append(record_validator)


    dhts = launch_dht_with_clients(
        record_validators=record_validators,
        identity_paths=test_paths,
    )

    for path in test_paths:
        try:
            os.remove(path)
        except:  # noqa: E722
            pass

    for dht in dhts:
        dht.shutdown()
