from typing import Callable

from mesh import get_dht_time, get_logger
from mesh.dht.routing import DHTID
from mesh.dht.validation import DHTRecord, DHTRecordRequestType
from mesh.substrate.chain_functions import EpochData
from mesh.substrate.config import BLOCK_SECS, EPOCH_LENGTH

logger = get_logger(__name__)

"""
Commit-Reveal Schema using the PredicateValidator
"""

"""
Hypertensor predicate validator

Verified allowable keys, schemas, epoch relationships, and commit-reveal schemes.
"""

def get_mock_commit_key(epoch: int) -> str:
    return f"commit_epoch_{epoch}"

def get_mock_reveal_key(epoch: int) -> str:
    return f"reveal_epoch_{epoch}"

def get_mock_consensus_key(epoch: int) -> str:
    return f"consensus_epoch_{epoch}"

# Created At validations
# 0-15%
CONSENSUS_STORE_DEADLINE = 0.15

# hoster commit-reveal epoch percentage elapsed deadlines
COMMIT_DEADLINE = 0.5
REVEAL_DEADLINE = 0.6

# Expiration validations
MAX_HEART_BEAT_TIME = BLOCK_SECS * EPOCH_LENGTH * 1.1
MAX_CONSENSUS_TIME = BLOCK_SECS * EPOCH_LENGTH * 1.1
MAX_COMMIT_TIME = BLOCK_SECS * EPOCH_LENGTH
MAX_REVEAL_TIME = BLOCK_SECS * EPOCH_LENGTH

"""
This is a mock predicate validator (see dht/validator.py) for the HypertensorPredicateValidator

You can add pydantic validation on the values, tie keys to epochs, and more.
"""
def mock_hypertensor_consensus_predicate() -> Callable[[DHTRecord, DHTRecordRequestType], bool]:
    def predicate(record: DHTRecord, type: DHTRecordRequestType, epoch_data: EpochData) -> bool:
        try:
            # Enable GET data at any time
            if type is DHTRecordRequestType.GET:
                return True

            current_epoch = epoch_data.epoch
            percent_complete = epoch_data.percent_complete

            # Ensure the keys are valid for the current allowable keys or epoch allowable keys
            valid_keys = {
                # Heartbeat
                DHTID.generate(source="role_name").to_bytes(): "role_name",
                # ⸺ 0-15%
                DHTID.generate(source=f"consensus_epoch_{current_epoch}").to_bytes(): "consensus",
                # ⸺ 15-50%
                DHTID.generate(source=f"commit_epoch_{current_epoch}").to_bytes(): "commit",
                # ⸺ 50-60%
                DHTID.generate(source=f"reveal_epoch_{current_epoch}").to_bytes(): "reveal",
            }

            key_type = valid_keys.get(record.key, None)

            if key_type is None:
                return False

            dht_time = get_dht_time()

            # ⸺ 0-100% (any time)
            if key_type == "role_name":
                max_expiration = dht_time + MAX_HEART_BEAT_TIME
                if record.expiration_time > max_expiration:
                    return False
                # TODO: validate proof-of-stake on each heartbeat (redundant)
                return True

            # ⸺ 0-15%
            elif key_type == "consensus":
                # Must be submitted before deadline
                if percent_complete > CONSENSUS_STORE_DEADLINE:
                    return False

                max_expiration = dht_time + MAX_CONSENSUS_TIME
                if record.expiration_time > max_expiration:
                    return False

                return True

            # ⸺ 15-50%
            elif key_type == "commit":
                max_expiration = dht_time + MAX_COMMIT_TIME
                if record.expiration_time > max_expiration:
                    return False
                if percent_complete <= CONSENSUS_STORE_DEADLINE or percent_complete > COMMIT_DEADLINE:
                    return False

                return True

            # ⸺ 50-60%
            elif key_type == "reveal":
                max_expiration = dht_time + MAX_REVEAL_TIME
                if record.expiration_time > max_expiration:
                    return False
                if percent_complete <= COMMIT_DEADLINE or percent_complete > REVEAL_DEADLINE:
                    return False
                return True

            return False  # Key doesn't match any known schema
        except Exception as e:
            print(f"Predicate Err: {e}")
            return False

    return predicate
