import glob
import json
from typing import Any, List, Optional

from mesh import PeerID
from mesh.substrate.chain_data import SubnetNode, SubnetNodeInfo
from mesh.substrate.chain_functions import EpochData
from mesh.substrate.config import BLOCK_SECS

epoch_data_location = "tests/test_utils/epoch_json.json"
def write_epoch_json(data: dict):
    with open(epoch_data_location, "w") as f:
        json.dump(data, f)

def increase_progress_and_write(percentage: float):
    if not (0.0 <= percentage <= 1.0):
        raise ValueError("target_percent must be between 0.0 and 1.0")

    with open(epoch_data_location, "r") as f:
        data = json.load(f)

    block_per_epoch = data.get("block_per_epoch", 100)
    epoch_length = block_per_epoch
    current_block = data["block"]

    # Calculate the block offset from the start of the current epoch
    blocks_elapsed = int(percentage * epoch_length)
    current_block = (data["epoch"] * epoch_length) + blocks_elapsed
    epoch = current_block // epoch_length
    percent_complete = blocks_elapsed / epoch_length
    blocks_remaining = epoch_length - blocks_elapsed
    seconds_elapsed = blocks_elapsed * BLOCK_SECS
    seconds_remaining = blocks_remaining * BLOCK_SECS
    seconds_per_epoch = epoch_length * BLOCK_SECS

    updated_data = {
        "block": current_block,
        "epoch": epoch,
        "block_per_epoch": epoch_length,
        "seconds_per_epoch": seconds_per_epoch,
        "percent_complete": percent_complete,
        "blocks_elapsed": blocks_elapsed,
        "blocks_remaining": blocks_remaining,
        "seconds_elapsed": seconds_elapsed,
        "seconds_remaining": seconds_remaining
    }

    with open(epoch_data_location, "w") as f:
        json.dump(updated_data, f, indent=2)

def increase_progress_and_write_with_slot(percentage: float, slot: int):
    if not (0.0 <= percentage <= 1.0):
        raise ValueError("percentage must be between 0.0 and 1.0")

    with open(epoch_data_location, "r") as f:
        data = json.load(f)

    block_per_epoch = data.get("block_per_epoch", 100)
    epoch_length = block_per_epoch
    current_block = data["block"]

    # Calculate the block offset from the start of the current epoch
    blocks_elapsed = int(percentage * epoch_length)
    current_block = (data["epoch"] * epoch_length) + blocks_elapsed + slot
    epoch = current_block // epoch_length
    percent_complete = blocks_elapsed / epoch_length
    blocks_remaining = epoch_length - blocks_elapsed
    seconds_elapsed = blocks_elapsed * BLOCK_SECS
    seconds_remaining = blocks_remaining * BLOCK_SECS
    seconds_per_epoch = epoch_length * BLOCK_SECS

    updated_data = {
        "block": current_block,
        "epoch": epoch,
        "block_per_epoch": epoch_length,
        "seconds_per_epoch": seconds_per_epoch,
        "percent_complete": percent_complete,
        "blocks_elapsed": blocks_elapsed,
        "blocks_remaining": blocks_remaining,
        "seconds_elapsed": seconds_elapsed,
        "seconds_remaining": seconds_remaining
    }

    with open(epoch_data_location, "w") as f:
        json.dump(updated_data, f, indent=2)

class MockHypertensor:
    url = None
    interface = None
    keypair = None
    hotkey = None

    def get_epoch_length(self):
        return 10

    def get_block_number(self):
        return 10

    def get_subnet_slot(self, subnet_id: int):
        return 2

    def get_epoch(self):
        with open(epoch_data_location, "r") as f:
            data = json.load(f)

        current_block = data["block"]
        epoch_length = data["block_per_epoch"]
        epoch = current_block // epoch_length

        return epoch

    def get_epoch_data(self) -> EpochData:
        with open(epoch_data_location, "r") as f:
            data = json.load(f)

        return EpochData(**data)

    def get_subnet_epoch(self, subnet_id: int):
        subnet_slot = self.get_subnet_slot(subnet_id)
        with open(epoch_data_location, "r") as f:
            data = json.load(f)

        current_block = data["block"]
        epoch_length = data["block_per_epoch"]
        offset_block = current_block - subnet_slot

        return int(offset_block / epoch_length)

    def get_subnet_epoch_data(self, slot: int) -> EpochData:
        with open(epoch_data_location, "r") as f:
            data = json.load(f)

            current_block = data['block']
            epoch_length = data['block_per_epoch']

            if current_block < slot:
                return EpochData.zero(current_block=current_block, epoch_length=epoch_length)

            blocks_since_start = current_block - slot
            epoch = blocks_since_start // epoch_length
            blocks_elapsed = blocks_since_start % epoch_length
            percent_complete = blocks_elapsed / epoch_length
            blocks_remaining = epoch_length - blocks_elapsed
            seconds_elapsed = blocks_elapsed * BLOCK_SECS
            seconds_remaining = blocks_remaining * BLOCK_SECS

        return EpochData(
            block=current_block,
            epoch=epoch,
            block_per_epoch=epoch_length,
            seconds_per_epoch=epoch_length * BLOCK_SECS,
            percent_complete=percent_complete,
            blocks_elapsed=blocks_elapsed,
            blocks_remaining=blocks_remaining,
            seconds_elapsed=seconds_elapsed,
            seconds_remaining=seconds_remaining
        )

    def get_rewards_validator(self, subnet_id: int, epoch: int):
        1

    def validate(
        self,
        subnet_id: int,
        data,
        args: Optional[Any] = None,
    ):
        return

    def attest(
        self,
        subnet_id: int
    ):
        return

    def get_formatted_elected_validator_node(self, subnet_id: int, epoch: int) -> Optional["SubnetNode"]:
        return SubnetNode(
            id=1,
            hotkey="0x1234567890abcdef1234567890abcdef12345678",
            peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            bootstrap_peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            client_peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            classification="Validator",
            delegate_reward_rate=0,
            last_delegate_reward_rate_update=0,
            a=None,
            b=None,
            c=None,
        )

    def get_formatted_rewards_validator_info(self, subnet_id, epoch: int) -> Optional["SubnetNodeInfo"]:
        return SubnetNodeInfo(
            subnet_node_id=1,
            coldkey="0x1234567890abcdef1234567890abcdef12345678",
            hotkey="0x1234567890abcdef1234567890abcdef12345678",
            peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            bootstrap_peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            client_peer_id="QmNV5G3hq2UmAck2htEgsqrmPFBff5goFZAdmKDcZLBZLX",
            classification="Validator",
            delegate_reward_rate=0,
            last_delegate_reward_rate_update=0,
            a=None,
            b=None,
            c=None,
            stake_balance=10000000000000
        )

    def get_consensus_data(self, subnet_id: int, epoch: int):
        consensus_data = []
        for identity_path in glob.glob("rsa_test_path*.key"):
            with open(identity_path, "rb") as f:
                peer_id = PeerID.from_identity_rsa(f.read())
                node = {
                    'peer_id': peer_id,
                    'score': 1e18
                }
                consensus_data.append(node)

        return consensus_data

    def get_subnet_included_nodes(self, subnet_id: int) -> List:
        subnet_nodes = []
        id = 1
        for identity_path in glob.glob("rsa_test_path*.key"):
            with open(identity_path, "rb") as f:
                peer_id = PeerID.from_identity_rsa(f.read())
                subnet_nodes.append(SubnetNode(
                    id=id,
                    hotkey=f"0x1234567890abcdef1234567890abcdef1234567{id}",
                    peer_id=peer_id,
                    bootstrap_peer_id=peer_id,
                    client_peer_id=peer_id,
                    classification="Validator",
                    delegate_reward_rate=0,
                    last_delegate_reward_rate_update=0,
                    a=None,
                    b=None,
                    c=None,
                ))
                id += 1

        return subnet_nodes

    def get_subnet_registration_epochs(self):
        return 1
