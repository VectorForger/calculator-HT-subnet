from dataclasses import dataclass

from mesh import get_logger
from mesh.dht.crypto import Ed25519SignatureValidator, RSASignatureValidator

logger = get_logger(__name__)

"""
Consensus scores
"""
@dataclass# RSA subkey for records (protected records requiring signing/validating)

class ConsensusScores:
  peer_id: str
  score: int

"""
Mock Role Scores

Fill in roles if needed here along with any required parameters, such as tensor outputs
"""
@dataclass
class MockValidatorScores:
  peer_id: str
  score: int

# RSA subkey for records (protected records requiring signing/validating)
def get_consensus_subkey_rsa(record_validator: RSASignatureValidator) -> bytes:
  return record_validator.local_public_key

# Ed25519 subkey for records (protected records requiring signing/validating)
def get_consensus_subkey_ed25519(record_validator: Ed25519SignatureValidator) -> bytes:
  return record_validator.local_public_key
