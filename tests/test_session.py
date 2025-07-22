import os
from typing import List

import pytest
from transformers import AutoTokenizer

from mesh import get_dht_time
from mesh.dht.crypto import RSASignatureValidator
from mesh.subnet.client.config import ClientConfig
from mesh.subnet.client.inference_session_v2 import Session
from mesh.subnet.client.routing.routing_manager import RemoteManager
from mesh.subnet.data_structures import QuantType, ServerClass, ServerInfo, ServerState
from mesh.subnet.protocols.mock_protocol import MockProtocol
from mesh.subnet.utils.dht import declare_node
from mesh.subnet.utils.key import (
    generate_rsa_private_key_file,
    get_rsa_peer_id,
    get_rsa_private_key,
)
from mesh.utils.logging import get_logger

from test_utils.dht_swarms import (
    launch_dht_instances_with_record_validators,
)

logger = get_logger(__name__)

"""
NOT COMPLETE
"""

# pytest tests/test_session.py -rP

# pytest tests/test_session.py::test_mock_session -rP
# pytest tests/test_session.py::test_mock_session --log-cli-level=DEBUG

@pytest.mark.forked
@pytest.mark.asyncio
async def test_mock_session():
    peers_len = 2

    test_paths = []
    record_validators: List[RSASignatureValidator] = []
    for i in range(peers_len):
        test_path = f"rsa_test_path_{i}.key"
        test_paths.append(test_path)
        private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id = generate_rsa_private_key_file(test_path)
        loaded_key = get_rsa_private_key(test_path)
        record_validator = RSASignatureValidator(loaded_key)
        record_validators.append(record_validator)
        peer_id = get_rsa_peer_id(public_bytes)

    dhts = launch_dht_instances_with_record_validators(
        record_validators=record_validators,
        identity_paths=test_paths,
    )

    hoster_dht = dhts[0]
    validator_dht = dhts[1]

    converted_model_name_or_path = "bigscience/bloom-560m"

    throughput_info = {"throughput": 1.0}
    server_info = ServerInfo(
        state=ServerState.ONLINE,
        role=ServerClass.HOSTER,
        public_name="",
        version="1.0.0",
        adapters=tuple(()),
        torch_dtype=str("auto").replace("torch.", ""),
        quant_type=QuantType.NF4.name.lower(),
        using_relay=False,
        **throughput_info,
    )

    declare_node(
        dht=hoster_dht,
        key="hoster",
        server_info=server_info,
        expiration_time=get_dht_time() + 999,
    )

    hoster_inference_protocol = MockProtocol(
        dht=hoster_dht,
        model_name=converted_model_name_or_path,
        start=True
    )

    config = ClientConfig()
    config.initial_peers = hoster_dht.get_visible_maddrs()
    config.dht_prefix = "subnet"
    config.update_period = 15

    remote_manager = RemoteManager(
        config=config,
        dht=validator_dht,
    )

    for dht in dhts:
        dht.shutdown()

    hoster_inference_protocol.shutdown()

    for path in test_paths:
        os.remove(path)
