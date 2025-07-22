from typing import Dict, List

from mesh import DHT
from mesh.dht.validation import RecordValidatorBase
from mesh.subnet.data_structures import ServerClass
from mesh.subnet.utils.consensus import (
    ConsensusScores,
)
from mesh.substrate.chain_functions import Hypertensor
from mesh.utils.logging import get_logger

logger = get_logger(__name__)

class MockValidator:
    def __init__(
        self,
        role: ServerClass,
        dht: DHT,
        record_validator: RecordValidatorBase,
        hypertensor: Hypertensor,
    ):
        self.role = role
        self.dht = dht
        self.record_validator = record_validator
        self.latest_commit = None
        self.hypertensor = hypertensor

    async def score_nodes(self, current_epoch: int) -> List[ConsensusScores]:
        """
        Score nodes

        Have a way to score nodes:

        Can happen in real time, or by querying the DHT Records if a commit-reveal scheme
        """

        scores = self.dht.get(f"scores_{current_epoch}") or {}

        consensus_score_list = [
            ConsensusScores(peer_id=peer_id, score=int(score * 1e18))
            for peer_id, score in scores.items()
        ]

        return consensus_score_list

    def normalize_scores(self, scores: Dict[str, float], target_total: float) -> Dict[str, float]:
        """
        Normalize scores for the blockchain
        """
        total = sum(scores.values())
        if total == 0:
            return {peer_id: 0.0 for peer_id in scores}
        return {
            peer_id: (score / total) * target_total
            for peer_id, score in scores.items()
        }

    def filter_merged_scores(self, scores: Dict[str, float]) -> List[ConsensusScores]:
        """
        Filter scores against the blockchain activated subnet nodes
        """
        return scores
