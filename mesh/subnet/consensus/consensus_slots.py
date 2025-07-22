import asyncio
import threading
from dataclasses import asdict
from typing import List

from mesh import DHT
from mesh.dht.validation import RecordValidatorBase
from mesh.subnet.utils.consensus import (
    ConsensusScores,
)
from mesh.substrate.chain_functions import Hypertensor
from mesh.substrate.config import BLOCK_SECS
from mesh.utils import get_logger

logger = get_logger(__name__)

class Consensus(threading.Thread):
    def __init__(
        self,
        dht: DHT,
        subnet_id: int,
        subnet_node_id: int,
        record_validator: RecordValidatorBase,
        hypertensor: Hypertensor,
        skip_activate_subnet: bool = False,
        start: bool = True
    ):
        super().__init__(daemon=True)
        self.dht = dht
        self.peer_id = self.dht.peer_id
        self.subnet_id = subnet_id
        self.subnet_node_id = subnet_node_id
        self.hypertensor = hypertensor
        self.record_validator = record_validator
        self.validator_scores = None
        self.previous_epoch_data = None
        self.is_subnet_active = False
        self.skip_activate_subnet = skip_activate_subnet
        self.slot = None # subnet epoch slot

        self.stop = threading.Event()

        if start:
            self.run()

    def get_validator(self, epoch: int):
        validator = self.hypertensor.get_rewards_validator(self.subnet_id, epoch)
        return validator

    def get_scores(self) -> List[ConsensusScores]:
        """
        Fill in a way to get scores on each node

        These scores must be deterministic
        """
        if self.validator_scores is None:
            return []

        # Step 2: Convert to List[ConsensusScores], rounding or casting score to int
        consensus_score_list = [
            ConsensusScores(peer_id=peer_id, score=int(score * 1e18))
            for peer_id, score in self.validator_scores.items()
        ]

        # Reset scores for node roles
        self.validator_scores = None

        return consensus_score_list

    def compare_consensus_data(self, my_data, validator_data, epoch: int) -> bool:
        """
        Compare the current epochs elected validator consensus submission to our own

        Must have 100% accuracy to return True
        """
        # if validator submitted no data, and we have also found the subnet is broken
        if len(validator_data) == 0 and len(my_data) == 0:
            self.previous_epoch_data = []
            return True

        # otherwise, check the data matches
        # at this point, the

        # use ``asdict`` because data is decoded from blockchain as dataclass
        # we assume the lists are consistent across all elements
        # Convert validator_data to a set
        validator_data_set = set(frozenset(asdict(d).items()) for d in validator_data)

        # Convert my_data to a set
        my_data_set = set(frozenset(d.items()) for d in my_data)

        success = validator_data_set == my_data_set

        if not success:
            """
            # Cases

            Case 1: Node leaves DHT before validator submit consensus and returns before attestation.
                    - Validator data does not include node, Attestors data will include node, creating a mismatch.
            Case 2: Node leaves DHT after validator submits consensus.
                    - Validator data does include node, Attestors data does not include node, creating a mismatch.

            # Solution

            We check our previous epochs data, if successfully attested, to find symmetry with the validators data.

            * If none of these solutions work, we assume the validator is being dishonest or is faulty
            """
            if not success and self.previous_epoch_data is not None:
                dif = validator_data_set.symmetric_difference(my_data_set)
                success = dif.issubset(self.previous_epoch_data)
            elif not success and self.previous_epoch_data is None:
                """
                If this is the nodes first epoch after a restart of the node, check last epochs consensus data
                """
                previous_epoch_validator_data = self._get_validator_consensus_submission(epoch - 1)
                # This is a backup so we ensure the data was super majority attested to use it
                if previous_epoch_validator_data is not None:
                    _, attestation_percentage = self._get_reward_result(epoch)
                    if attestation_percentage / 1e18 < 0.66:
                        # TODO: Check
                        success = False
                    else:
                        previous_epoch_data_onchain = set(
                            frozenset(asdict(d).items()) for d in previous_epoch_validator_data
                        )
                        dif = validator_data_set.symmetric_difference(my_data_set)
                        success = dif.issubset(previous_epoch_data_onchain)

        self.previous_epoch_data = my_data_set

        return success

    def _get_reward_result(self, epoch: int):
        try:
            event = self.hypertensor.get_reward_result_event(self.self.subnet_id, epoch)
            subnet_id, attestation_percentage = event["event"]["attributes"]
            return subnet_id, attestation_percentage
        except Exception as e:
            logger.warning("Reward Result Error: %s" % e, exc_info=True)
            return None

    def run(self):
        self.is_subnet_active = asyncio.run(self.run_activate_subnet())
        if not self.is_subnet_active:
            return

        self.is_node_validator = asyncio.run(self.run_is_node_validator())
        if not self.is_node_validator:
            return

        asyncio.run(self.run_forever())

    async def run_activate_subnet(self):
        """
        Verify subnet is active on-chain before starting consensus

        For initial coldkeys this will sleep until the enactment period, then proceed
        to check once per epoch after enactment starts if the owner activated the subnet
        """
        # Useful if subnet is already active and for testing
        if self.skip_activate_subnet:
            return True

        last_epoch = None
        subnet_registration_epochs = self.hypertensor.get_subnet_registration_epochs()
        subnet_active = False
        errors_count = 0
        while not self.stop.is_set():
            epoch_data = self.hypertensor.get_epoch_data()
            current_epoch = epoch_data.epoch

            if current_epoch != last_epoch:
                seconds_per_epoch = epoch_data.seconds_per_epoch
                offset_sleep = 0
                subnet_info = self.hypertensor.get_formatted_subnet_info(
                    self.subnet_id
                )
                if subnet_info is None:
                    if errors_count > 3:
                        logger.warning("Cannot find subnet ID: %s, shutting down", self.subnet_id)
                        self.shutdown()
                        subnet_active = False
                        break
                    else:
                        errors_count = errors_count + 1
                else:
                    if subnet_info.state == "Active":
                        subnet_active = True
                        self.slot = self.hypertensor.get_subnet_slot(self.subnet_id)
                        break

                    # Still in registration period
                    max_registration_epoch = subnet_registration_epochs + subnet_info.registration_epoch
                    registration_epochs_remaining = max_registration_epoch - current_epoch
                    offset_sleep = seconds_per_epoch * registration_epochs_remaining - epoch_data.seconds_elapsed
                    # Wait until enactment period
                    await asyncio.sleep(
                        max(0.0, offset_sleep)
                    )

                last_epoch = current_epoch
            else:
                await asyncio.sleep(epoch_data.seconds_remaining)
                continue

            await asyncio.sleep(
                max(0.0, seconds_per_epoch - epoch_data.seconds_elapsed - offset_sleep)
            )

        return subnet_active

    def _is_subnet_node_activated(self, node_class) -> bool:
        if (
            node_class == "Idle" or
            node_class == "Included" or
            node_class == "Validator"
        ):
            return True

        return False

    async def run_is_node_validator(self):
        """
        Verify node is active on-chain before starting consensus

        Node must be classed as Included on-chain to to start consensus

        Included nodes cannot be the elected validator or attest but must take part in consensus
        and be included in the consensus data to graduate to a Validator classed node
        """
        last_epoch = None
        while not self.stop.is_set():
            epoch_data = self.hypertensor.get_epoch_data()
            current_epoch = epoch_data.epoch

            if current_epoch != last_epoch:
                nodes = self.hypertensor.get_subnet_validator_nodes(self.subnet_id)
                node_found = False
                for node in nodes:
                    if node.id == self.subnet_node_id:
                        node_found = True
                        break

                if not node_found:
                    logger.info(
                        "Subnet Node ID %s is not Validator class on epoch %s. Trying again in one epoch", self.subnet_node_id, current_epoch
                    )

                last_epoch = current_epoch
            else:
                await asyncio.sleep(epoch_data.seconds_remaining)
                continue

            await asyncio.sleep(epoch_data.seconds_remaining)

        return True

    async def run_forever(self):
        """
        Loop until a new epoch to found, then run consensus logic
        """

        self._async_stop_event = asyncio.Event()
        last_epoch = None

        while not self.stop.is_set() and not self._async_stop_event.is_set():
            # epoch_data = self.hypertensor.get_epoch_data()
            epoch_data = self.hypertensor.get_subnet_epoch_progress(self.slot)
            current_epoch = epoch_data.epoch

            if current_epoch != last_epoch:
                """
                Add validation logic before and/or after `await run_consensus(current_epoch)`
                """

                # Attest/Validate
                await self.run_consensus(current_epoch)

                last_epoch = current_epoch
            else:
                # Sync blockchain and DHT clock
                await asyncio.sleep(epoch_data.seconds_remaining)
                continue

            # Keep sleep interval accurate to blockchain clock
            # epoch_data = self.hypertensor.get_epoch_data()
            epoch_data = self.hypertensor.get_subnet_epoch_progress(self.slot)
            epoch_data.seconds_remaining

            try:
                await asyncio.wait_for(self._async_stop_event.wait(), timeout=epoch_data.seconds_remaining)
            except asyncio.TimeoutError:
                pass

    async def run_consensus(self, current_epoch: int):
        """
        At the start of each epoch, we check if we are validator

        We start by:
            - Getting scores
                - Can generate scores in real-time or get from the DHT database

        If elected on-chain validator:
            - Submit scores to Hypertensor

        If attestor (non-elected on-chain validator):
            - Retrieve validators score submission from Hypertensor
            - Compare to our own
            - Attest if 100% accuracy, else do nothing
        """
        scores = self.get_scores()

        validator = None
        # Wait until validator is chosen
        while not self.stop.is_set():
            validator = self.get_validator(current_epoch)

            if validator is None:
                # Wait until next block to try again
                await asyncio.sleep(BLOCK_SECS)
                continue

        if validator == self.subnet_node_id:
            print(f"Acting as validator for epoch {current_epoch}")

            if len(scores) == 0:
                """
                Add any logic here for when no scores a present.

                No scores are generated, likely subnet in broken state and all other nodes 
                should be too, so we submit consensus with no scores.

                This will increase subnet penalties, but avoid validator penalties.

                Any successful epoch following will remove these penalties on the subnet
                """
                self.hypertensor.validate(self.subnet_id, data=scores)
            else:
                self.hypertensor.validate(self.subnet_id, data=scores)

        elif validator is not None:
            print(f"Acting as attestor for epoch {current_epoch}")
            while not self.stop.is_set():
                validator_data = self.hypertensor.get_consensus_data(self.subnet_id, current_epoch)

                if validator_data is None:
                    await asyncio.sleep(BLOCK_SECS)
                    continue

                """
                Get all of the hosters inference outputs they stored to the DHT
                """
                if self.compare_consensus_data(scores, validator_data, current_epoch):
                    print(f"Validator data matches for epoch {current_epoch}, attesting")
                    self.hypertensor.attest(self.subnet_id)
                else:
                    print(f"Data doesn't match validator for epoch {current_epoch}, moving forward with no attetation")

    def shutdown(self):
        self.stop.set()
