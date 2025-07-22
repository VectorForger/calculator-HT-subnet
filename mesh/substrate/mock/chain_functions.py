import glob
from typing import Any, Optional

from mesh.subnet.utils.key import generate_rsa_private_key_file
from mesh.substrate.chain_data import SubnetNode, SubnetNodeInfo
from mesh.substrate.chain_functions import EpochData
from mesh.substrate.config import BLOCK_SECS


class MockHypertensor:
    url = None
    interface = None
    keypair = None
    hotkey = None

    def get_epoch_length(self):
        return 100

    def get_block_number(self):
        return 100

    def get_epoch(self):
        current_block = self.get_block_number()
        epoch_length = self.get_epoch_length()
        return current_block // epoch_length

    def get_epoch_data(self) -> EpochData:
        current_block = self.get_block_number()
        epoch_length = self.get_epoch_length()
        epoch = current_block // epoch_length
        blocks_elapsed = current_block % epoch_length
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
        for filepath in glob.glob("server*.id"):
            _, _, public_bytes, _, _, peer_id = generate_rsa_private_key_file(filepath)
            node = {
                'peer_id': peer_id,
                'score': 1e18
            }
            consensus_data.append(node)


    def get_subnet_registration_epochs(self, subnet_id: int):
        return 10
