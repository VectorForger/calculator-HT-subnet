from dataclasses import dataclass
from typing import Any, List, Optional

from substrateinterface import ExtrinsicReceipt, Keypair, SubstrateInterface
from substrateinterface.exceptions import SubstrateRequestException
from tenacity import retry, stop_after_attempt, wait_fixed

from mesh.substrate.chain_data import SubnetData, SubnetInfo, SubnetNode
from mesh.substrate.config import BLOCK_SECS


@dataclass
class EpochData:
  block: int
  epoch: int
  block_per_epoch: int
  seconds_per_epoch: int
  percent_complete: float
  blocks_elapsed: int
  blocks_remaining: int
  seconds_elapsed: int
  seconds_remaining: int

  @staticmethod
  def zero(current_block: int, epoch_length: int) -> "EpochData":
    return EpochData(
      block=current_block,
      epoch=0,
      block_per_epoch=epoch_length,
      seconds_per_epoch=epoch_length * BLOCK_SECS,
      percent_complete=0.0,
      blocks_elapsed=0,
      blocks_remaining=epoch_length,
      seconds_elapsed=0,
      seconds_remaining=epoch_length * BLOCK_SECS
    )


class Hypertensor:
  def __init__(self, url: str, phrase: str):
    self.url = url
    self.interface: SubstrateInterface = SubstrateInterface(url=url)
    self.keypair = Keypair.create_from_uri(phrase)
    self.hotkey = Keypair.create_from_uri(phrase).ss58_address

  def get_block_number(self):
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          block_hash = _interface.get_block_hash()
          block_number = _interface.get_block_number(block_hash)
          return block_number
      except SubstrateRequestException as e:
        print("Failed to get query request: {}".format(e))

    return make_query()

  def get_epoch(self):
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          block_hash = _interface.get_block_hash()
          current_block = _interface.get_block_number(block_hash)
          epoch_length = _interface.get_constant('Network', 'EpochLength')
          epoch = current_block // epoch_length
          return epoch
      except SubstrateRequestException as e:
        print("Failed to get query request: {}".format(e))

    return make_query()

  def validate(
    self,
    subnet_id: int,
    data,
    args: Optional[Any] = None,
  ):
    """
    Submit consensus data on each epoch with no conditionals

    It is up to prior functions to decide whether to call this function

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param data: an array of data containing all AccountIds, PeerIds, and scores per subnet hoster
    :param args: arbitrary data the validator can send in with consensus data

    Note: It's important before calling this to ensure the entrinsic will be successful.
          If the function reverts, the extrinsic is Pays::Yes
    """
    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='validate',
      call_params={
        'subnet_id': subnet_id,
        'data': data,
        'args': args,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          if receipt.is_success:
            print('✅ Success, triggered events:')
            for event in receipt.triggered_events:
                print(f'* {event.value}')
          else:
              print('⚠️ Extrinsic Failed: ', receipt.error_message)

          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def attest(
    self,
    subnet_id: int
  ):
    """
    Attest validator submission on current epoch

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: Subnet ID

    Note: It's important before calling this to ensure the entrinsic will be successful.
          If the function reverts, the extrinsic is Pays::Yes
    """
    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='attest',
      call_params={
        'subnet_id': subnet_id,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)

          if receipt.is_success:
            print('✅ Success, triggered events:')
            for event in receipt.triggered_events:
                print(f'* {event.value}')
          else:
              print('⚠️ Extrinsic Failed: ', receipt.error_message)

          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def register_subnet(
    self,
    path: str,
    memory_mb: int,
    registration_blocks: int,
    entry_interval: int,
  ) -> ExtrinsicReceipt:
    """
    Register subnet node and stake

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param path: path to download the model
    :param memory_mb: memory requirements to host entire model one time
    :param registration_blocks: blocks to keep subnet in registration period
    :param entry_interval: blocks required between each subnet node entry
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='register_subnet',
      call_params={
        'subnet_data': {
          'path': path,
          'memory_mb': memory_mb,
          'registration_blocks': registration_blocks,
          'entry_interval': entry_interval,
        }
      }
    )

    # create signed extrinsic
    extrinsic = self.interface.create_signed_extrinsic(call=call, keypair=self.keypair)

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def activate_subnet(
    self,
    subnet_id: str,
  ) -> ExtrinsicReceipt:
    """
    Activate a registered subnet node

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='activate_subnet',
      call_params={
        'subnet_id': subnet_id,
      }
    )

    # @retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(4))
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def remove_subnet(
    self,
    subnet_id: str,
  ) -> ExtrinsicReceipt:
    """
    Remove a subnet

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='remove_subnet',
      call_params={
        'subnet_id': subnet_id,
      }
    )

    # create signed extrinsic
    extrinsic = self.interface.create_signed_extrinsic(call=call, keypair=self.keypair)

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def get_subnet_nodes(
    self,
    subnet_id: int,
  ):
    """
    Function to return all account_ids and subnet_node_ids from the substrate Hypertensor Blockchain

    :param subnet_id: subnet ID
    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getSubnetNodes',
            params=[
              subnet_id
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_subnet_nodes_included(
    self,
    subnet_id: int,
  ):
    """
    Function to return Included classified account_ids and subnet_node_ids from the substrate Hypertensor Blockchain

    :param subnet_id: subnet ID
    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getSubnetNodesIncluded',
            params=[subnet_id]
          )
        return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_subnet_nodes_validator(
    self,
    subnet_id: int,
  ):
    """
    Function to return Validator classified account_ids and subnet_node_ids from the substrate Hypertensor Blockchain

    :param subnet_id: subnet ID
    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getSubnetNodesValidator',
            params=[
              subnet_id
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  async def get_consensus_data(
    self,
    subnet_id: int,
    epoch: int
  ):
    """
    Query an epochs consesnus submission

    :param subnet_id: subnet I
    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getConsensusData',
            params=[
              subnet_id,
              epoch
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def is_subnet_node_by_peer_id(
    self,
    subnet_id: int,
    peer_id: str
  ):
    """
    Function to return all account_ids and subnet_node_ids from the substrate Hypertensor Blockchain by peer ID

    :param subnet_id: subnet ID
    :param peer_id: peer ID
    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          is_subnet_node = _interface.rpc_request(
            method='network_isSubnetNodeByPeerId',
            params=[
              subnet_id,
              peer_id
            ]
          )
          return is_subnet_node
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_minimum_delegate_stake(
    self,
    subnet_id: int,
  ):
    """
    Query required minimum stake balance based on memory

=    :param subnet_id: Subnet ID

    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getMinimumDelegateStake',
            params=[
              subnet_id
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_subnet_node_info(
    self,
    subnet_id: int,
    subnet_node_id: int
  ):
    """
    Function to return all subnet nodes in the SubnetNodeInfo struct format

    :param subnet_id: subnet ID

    :returns: subnet_nodes_data
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getSubnetNodeInfo',
            params=[
              subnet_id,
              subnet_node_id
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def add_subnet_node(
    self,
    subnet_id: int,
    hotkey: str,
    peer_id: str,
    delegate_reward_rate: int,
    stake_to_be_added: int,
    a: Optional[str] = None,
    b: Optional[str] = None,
    c: Optional[str] = None,
  ) -> ExtrinsicReceipt:
    """
    Add subnet validator as subnet subnet_node and stake

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param hotkey: Hotkey of subnet node
    :param peer_id: peer Id of subnet node
    :param delegate_reward_rate: reward rate to delegate stakers (1e18)
    :param stake_to_be_added: amount to stake
    :param a: unique optional parameter
    :param b: optional parametr
    :param c: optional parametr
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='add_subnet_node',
      call_params={
        'subnet_id': subnet_id,
        'hotkey': hotkey,
        'peer_id': peer_id,
        'delegate_reward_rate': delegate_reward_rate,
        'stake_to_be_added': stake_to_be_added,
        'a': a,
        'b': b,
        'c': c,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def register_subnet_node(
    self,
    subnet_id: int,
    hotkey: str,
    peer_id: str,
    delegate_reward_rate: int,
    stake_to_be_added: int,
    a: Optional[str] = None,
    b: Optional[str] = None,
    c: Optional[str] = None,
  ) -> ExtrinsicReceipt:
    """
    Register subnet node and stake

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param hotkey: Hotkey of subnet node
    :param peer_id: peer Id of subnet node
    :param delegate_reward_rate: reward rate to delegate stakers (1e18)
    :param stake_to_be_added: amount to stake
    :param a: unique optional parameter
    :param b: optional parametr
    :param c: optional parametr
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='register_subnet_node',
      call_params={
        'subnet_id': subnet_id,
        'hotkey': hotkey,
        'peer_id': peer_id,
        'delegate_reward_rate': delegate_reward_rate,
        'stake_to_be_added': stake_to_be_added,
        'a': a,
        'b': b,
        'c': c,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def activate_subnet_node(
    self,
    subnet_id: int,
    subnet_node_id: int,
  ) -> ExtrinsicReceipt:
    """
    Activate registered subnet node

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param subnet_node_id: subnet node ID
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='activate_subnet_node',
      call_params={
        'subnet_id': subnet_id,
        'subnet_node_id': subnet_node_id,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def deactivate_subnet_node(
    self,
    subnet_id: int,
    subnet_node_id: int,
  ) -> ExtrinsicReceipt:
    """
    Temporarily deactivate subnet node

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param subnet_node_id: subnet node ID
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='deactivate_subnet_node',
      call_params={
        'subnet_id': subnet_id,
        'subnet_node_id': subnet_node_id,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def remove_subnet_node(
    self,
    subnet_id: int,
    subnet_node_id: int,
  ):
    """
    Remove subnet node

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param subnet_node_id: subnet node ID
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='remove_subnet_node',
      call_params={
        'subnet_id': subnet_id,
        'subnet_node_id': subnet_node_id,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def add_to_stake(
    self,
    subnet_id: int,
    subnet_node_id: int,
    stake_to_be_added: int,
  ):
    """
    Increase stake balance of a subnet node

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param subnet_node_id: subnet node ID
    :param stake_to_be_added: stake to be added towards subnet
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='add_to_stake',
      call_params={
        'subnet_id': subnet_id,
        'subnet_node_id': subnet_node_id,
        'hotkey': self.keypair.ss58_address,
        'stake_to_be_added': stake_to_be_added,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def remove_stake(
    self,
    subnet_id: int,
    stake_to_be_removed: int,
  ):
    """
    Remove stake balance towards specified subnet.

    Amount must be less than minimum required balance if an activate subnet node.

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param stake_to_be_removed: stake to be removed from subnet
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='remove_stake',
      call_params={
        'subnet_id': subnet_id,
        'hotkey': self.keypair.ss58_address,
        'stake_to_be_removed': stake_to_be_removed,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def claim_stake_unbondings(self):
    """
    Remove balance from unbondings ledger

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: Subnet ID
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='claim_unbondings',
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def add_to_delegate_stake(
    self,
    subnet_id: int,
    stake_to_be_added: int,
  ):
    """
    Add delegate stake balance to subnet

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: subnet ID
    :param stake_to_be_added: stake to be added towards subnet
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='add_to_delegate_stake',
      call_params={
        'subnet_id': subnet_id,
        'stake_to_be_added': stake_to_be_added,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def transfer_delegate_stake(
    self,
    from_subnet_id: int,
    to_subnet_id: int,
    delegate_stake_shares_to_be_switched: int,
  ):
    """
    Transfer delegate stake from one subnet to another subnet

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param from_subnet_id: from subnet ID 
    :param to_subnet_id: to subnet ID
    :param stake_to_be_added: stake to be added towards subnet
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='transfer_delegate_stake',
      call_params={
        'from_subnet_id': from_subnet_id,
        'to_subnet_id': to_subnet_id,
        'delegate_stake_shares_to_be_switched': delegate_stake_shares_to_be_switched
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def remove_delegate_stake(
    self,
    subnet_id: int,
    shares_to_be_removed: int,
  ):
    """
    Remove delegate stake balance from subnet by shares

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: to subnet ID
    :param shares_to_be_removed: sahares to be removed
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='add_to_delegate_stake',
      call_params={
        'subnet_id': subnet_id,
        'shares_to_be_removed': shares_to_be_removed,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def increase_delegate_stake(
    self,
    subnet_id: int,
    amount: int,
  ):
    """
    Increase delegate stake pool balance to subnet ID

    Note: This does ''NOT'' increase the balance of a user

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: to subnet ID
    :param amount: TENSOR to be added
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='increase_delegate_stake',
      call_params={
        'subnet_id': subnet_id,
        'amount': amount,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def update_coldkey(
    self,
    hotkey: str,
    new_coldkey: str,
  ):
    """
    Update coldkey using current coldkey as self.keypair

    :param self.keypair: coldkey self.keypair
    :param hotkey: Hotkey
    :param new_coldkey: New coldkey
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='update_coldkey',
      call_params={
        'hotkey': hotkey,
        'new_coldkey': new_coldkey,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def update_hotkey(
    self,
    old_hotkey: str,
    new_hotkey: str,
  ):
    """
    Updates hotkey using coldkey

    :param self.keypair: coldkey self.keypair
    :param old_hotkey: Old hotkey
    :param new_hotkey: New hotkey
    """

    # compose call
    call = self.interface.compose_call(
      call_module='Network',
      call_function='update_hotkey',
      call_params={
        'old_hotkey': old_hotkey,
        'new_hotkey': new_hotkey,
      }
    )

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def submit_extrinsic():
      try:
        with self.interface as _interface:
          # get none on retries
          nonce = _interface.get_account_nonce(self.keypair.ss58_address)

          # create signed extrinsic
          extrinsic = _interface.create_signed_extrinsic(call=call, keypair=self.keypair, nonce=nonce)

          receipt = _interface.submit_extrinsic(extrinsic, wait_for_inclusion=True)
          return receipt
      except SubstrateRequestException as e:
        print("Failed to send: {}".format(e))

    return submit_extrinsic()

  def get_subnet_node_data(
    self,
    subnet_id: int,
    subnet_node_id: int,
  ) -> ExtrinsicReceipt:
    """
    Query a subnet node ID by its hotkey

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: to subnet ID
    :param hotkey: Hotkey of subnet node
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetNodesData', [subnet_id, subnet_node_id])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_hotkey_subnet_node_id(
    self,
    subnet_id: int,
    hotkey: str,
  ) -> ExtrinsicReceipt:
    """
    Query a subnet node ID by its hotkey

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param subnet_id: to subnet ID
    :param hotkey: Hotkey of subnet node
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'HotkeySubnetNodeId', [subnet_id, hotkey])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_hotkey_owner(
    self,
    hotkey: str,
  ) -> ExtrinsicReceipt:
    """
    Get coldkey of hotkey

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'HotkeyOwner', [hotkey])
          return result.value['data']['free']
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_node_id_hotkey(
    self,
    subnet_id: int,
    hotkey: str,
  ) -> ExtrinsicReceipt:
    """
    Query hotkey by subnet node ID

    :param self.keypair: self.keypair of extrinsic caller. Must be a subnet_node in the subnet
    :param hotkey: Hotkey of subnet node
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetNodeIdHotkey', [subnet_id, hotkey])
          return result.value['data']['free']
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_activation_grace_epochs(
    self,
    subnet_id: int,
  ) -> ExtrinsicReceipt:
    """
    Query subnet grace epochs

    The grace epochs the are epochs allowable following the start_epoch for activating
    a subnet node

    :param subnet_id: Subnet ID
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'ActivationGraceEpochs', [subnet_id])
          return result.value['data']['free']
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_balance(
    self,
    address: str
  ):
    """
    Function to return account balance

    :param address: address of account_id
    :returns: account balance
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('System', 'Account', [address])
          return result.value['data']['free']
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_stake_balance(
    self,
    subnet_id: int,
    address: str
  ):
    """
    Function to return a subnet node stake balance

    :param subnet_id: Subnet ID
    :param address: address of account_id
    :returns: account stake balance towards subnet
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'AccountSubnetStake', [address, subnet_id])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_id_by_path(
    self,
    path: str
  ):
    """
    Query subnet ID by path

    :param path: path of subnet
    :returns: subnet_id
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetPaths', [path])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_data(
    self,
    id: int
  ):
    """
    Function to get data struct of the subnet

    :param id: id of subnet
    :returns: subnet_id
    """
    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetsData', [id])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_info(
    self,
    subnet_id: int,
  ):
    """
    Query an epochs chosen subnet validator and return SubnetNode

    :param subnet_id: subnet ID
    :returns: Struct of subnet info
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getSubnetInfo',
            params=[
              subnet_id,
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_max_subnets(self):
    """
    Function to get the maximum number of subnets allowed on the blockchain

    :returns: max_subnets
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MaxSubnets')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_min_subnet_nodes(self):
    """
    Function to get the minimum number of subnet_nodes required to host a subnet

    :returns: min_subnet_nodes
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MinSubnetNodes')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_min_stake_balance(self):
    """
    Function to get the minimum stake balance required to host a subnet

    :returns: min_stake_balance
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MinStakeBalance')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_max_subnet_nodes(self):
    """
    Function to get the maximum number of subnet_nodes allowed to host a subnet

    :returns: max_subnet_nodes
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MaxSubnetNodes')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_tx_rate_limit(self):
    """
    Function to get the transaction rate limit

    :returns: tx_rate_limit
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'TxRateLimit')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_epoch_length(self):
    """
    Function to get the epoch length as blocks per epoch

    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.get_constant('Network', 'EpochLength')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_rewards_validator(
    self,
    subnet_id: int,
    epoch: int
  ):
    """
    Query an epochs chosen subnet validator

    :param subnet_id: subnet ID
    :param epoch: epoch to query SubnetRewardsValidator
    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetRewardsValidator', [subnet_id, epoch])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()


  def get_rewards_validator_info(
    self,
    subnet_id: int,
    epoch: int
  ):
    """
    Query an epochs chosen subnet validator and return SubnetNodeInfo

    :param subnet_id: subnet ID
    :param epoch: epoch to query SubnetRewardsValidator
    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getRewardsValidatorInfo',
            params=[
              subnet_id,
              epoch
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_elected_validator_node(
    self,
    subnet_id: int,
    epoch: int
  ):
    """
    Query an epochs chosen subnet validator and return SubnetNode

    :param subnet_id: subnet ID
    :param epoch: epoch to query SubnetRewardsValidator
    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_rpc_request():
      try:
        with self.interface as _interface:
          subnet_nodes_data = _interface.rpc_request(
            method='network_getElectedValidatorNode',
            params=[
              subnet_id,
              epoch
            ]
          )
          return subnet_nodes_data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_rpc_request()

  def get_rewards_submission(
    self,
    subnet_id: int,
    epoch: int
  ):
    """
    Query epochs validator rewards submission

    :param subnet_id: subnet ID
    :param epoch: epoch to query SubnetRewardsSubmission 

    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetRewardsSubmission', [subnet_id, epoch])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_min_subnet_registration_blocks(self):
    """
    Query minimum subnet registration blocks

    :returns: epoch_length
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MinSubnetRegistrationBlocks')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_max_subnet_registration_blocks(self):
    """
    Query maximum subnet registration blocks

    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MaxSubnetRegistrationBlocks')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_max_subnet_entry_interval(self):
    """
    Query maximum subnet entry interval blocks
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'MaxSubnetEntryInterval')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_registration_epochs(self):
    """
    Query maximum subnet entry interval blocks
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetRegistrationEpochs')
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  def get_subnet_slot(self, subnet_id: int):
    """
    Query maximum subnet entry interval blocks
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_query():
      try:
        with self.interface as _interface:
          result = _interface.query('Network', 'SubnetSlot', [subnet_id])
          return result
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_query()

  # EVENTS

  def get_reward_result_event(
    self,
    target_subnet_id: int,
    epoch: int
  ):
    """
    Query the event of an epochs rewards submission

    :param target_subnet_id: subnet ID

    :returns: subnet_nodes_data
    """

    @retry(wait=wait_fixed(BLOCK_SECS+1), stop=stop_after_attempt(4))
    def make_event_query():
      try:
        epoch_length = self.get_epoch_length()
        epoch_length = int(str(epoch_length))
        block_number = epoch_length * epoch
        block_hash = self.interface.get_block_hash(block_number=block_number)
        with self.interface as _interface:
          data = None
          events = _interface.get_events(block_hash=block_hash)
          for event in events:
            if event['event']['module_id'] == "Network" and event['event']['event_id'] == "RewardResult":
              subnet_id, attestation_percentage = event['event']['attributes']
              if subnet_id == target_subnet_id:
                data = subnet_id, attestation_percentage
                break
          return data
      except SubstrateRequestException as e:
        print("Failed to get rpc request: {}".format(e))

    return make_event_query()

  """
  Helpers
  """
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

  def get_subnet_epoch_progress(self, slot: int) -> EpochData:
    current_block = self.get_block_number()
    epoch_length = self.get_epoch_length()

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

  def get_formatted_elected_validator_node(self, subnet_id: int, epoch: int) -> Optional["SubnetNode"]:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_elected_validator_node(
        subnet_id,
        epoch
      )

      subnet_node = SubnetNode.from_vec_u8(result["result"])

      return subnet_node
    except Exception:
      return None

  def get_formatted_subnet_data(self, subnet_id: int) -> Optional["SubnetData"]:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_subnet_data(
        subnet_id,
      )

      subnet = SubnetData.from_vec_u8(result["result"])

      return subnet
    except Exception:
      return None

  def get_formatted_subnet_info(self, subnet_id: int) -> Optional["SubnetInfo"]:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_subnet_info(subnet_id)

      subnet = SubnetInfo.from_vec_u8(result["result"])

      return subnet
    except Exception:
      return None

  def get_formatted_subnet_node_data(self, subnet_id: int, subnet_node_id: int) -> Optional["SubnetNode"]:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_subnet_node_data(subnet_id, subnet_node_id)

      subnet = SubnetNode.from_vec_u8(result["result"])

      return subnet
    except Exception:
      return None

  def get_subnet_validator_nodes(self, subnet_id: int) -> List:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_subnet_nodes_validator(
        subnet_id,
      )

      subnet_nodes = SubnetNode.list_from_vec_u8(result["result"])

      return subnet_nodes
    except Exception:
      return []

  def get_subnet_included_nodes(self, subnet_id: int) -> List:
    """
    Get formatted list of subnet nodes classified as Validator

    :param subnet_id: subnet ID

    :returns: List of subnet node IDs
    """
    try:
      result = self.get_subnet_nodes_included(
        subnet_id,
      )

      subnet_nodes = SubnetNode.list_from_vec_u8(result["result"])

      return subnet_nodes
    except Exception:
      return []
