"""
Substrate config file for storing blockchain configuration and parameters in a pickle
to avoid remote blockchain calls
"""
from substrateinterface import Keypair, SubstrateInterface

BLOCK_SECS = 6
EPOCH_LENGTH = 100 # blocks per epoch

class SubstrateConfigCustom:
  def __init__(self, phrase, url):
    self.url = url
    self.interface: SubstrateInterface = SubstrateInterface(url=url)
    self.keypair = Keypair.create_from_uri(phrase)
    self.hotkey = Keypair.create_from_uri(phrase).ss58_address
