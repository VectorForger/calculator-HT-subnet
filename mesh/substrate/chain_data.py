import ast
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import scalecodec
from scalecodec.base import RuntimeConfiguration, ScaleBytes
from scalecodec.type_registry import load_type_registry_preset
from scalecodec.utils.ss58 import ss58_encode

custom_rpc_type_registry = {
  "types": {
    "SubnetData": {
      "type": "struct",
      "type_mapping": [
        ["id", "u32"],
        ["name", "Vec<u8>"],
        ["repo", "Vec<u8>"],
        ["description", "Vec<u8>"],
        ["misc", "Vec<u8>"],
        ["state", "SubnetState"],
        ["start_epoch", "u32"],
      ],
    },
    "SubnetInfo": {
      "type": "struct",
      "type_mapping": [
        ["id", "u32"],
        ["name", "Vec<u8>"],
        ["repo", "Vec<u8>"],
        ["description", "Vec<u8>"],
        ["misc", "Vec<u8>"],
        ["churn_limit", "u32"],
        ["min_stake", "u128"],
        ["max_stake", "u128"],
        ["delegate_stake_percentage", "u128"],
        ["registration_queue_epochs", "u32"],
        ["activation_grace_epochs", "u32"],
        ["queue_classification_epochs", "u32"],
        ["included_classification_epochs", "u32"],
        ["max_node_penalties", "u32"],
        ["initial_coldkeys", "BTreeSet"],
        ["owner", "AccountId"],
        ["registration_epoch", "u32"],
        ["node_removal_system", "NodeRemovalSystem"],
        ["key_type", "KeyType"],
      ],
    },
    "SubnetState": {
      "type": "enum",
      "value_list": [
        "Registered",
        "Active",
      ],
    },
    "NodeRemovalSystem": {
      "type": "enum",
      "value_list": [
        "Consensus",
        "Stake",
        "Reputation",
      ],
    },
    "KeyType": {
      "type": "enum",
      "value_list": [
        "Rsa",
        "Ed25519",
        "Secp256k1",
        "Ecdsa",
      ],
    },
    "SubnetNode": {
      "type": "struct",
      "type_mapping": [
        ["id", "u32"],
        ["hotkey", "AccountId"],
        ["peer_id", "Vec<u8>"],
        ["bootstrap_peer_id", "Vec<u8>"],
        ["client_peer_id", "Vec<u8>"],
        ["classification", "SubnetNodeClassification"],
        ["delegate_reward_rate", "u128"],
        ["last_delegate_reward_rate_update", "u32"],
        ["a", "Option<BoundedVec<u8>>"],
        ["b", "Option<BoundedVec<u8>>"],
        ["c", "Option<BoundedVec<u8>>"],
      ],
    },
    "SubnetNodeClassification": {
      "type": "struct",
      "type_mapping": [
        ["node_class", "SubnetNodeClass"],
        ["start_epoch", "u32"],
      ],
    },
    "SubnetNodeClass": {
      "type": "enum",
      "value_list": [
        "Deactivated",
        "Registered",
        "Idle",
        "Included",
        "Validator"
      ],
    },
    "RewardsData": {
      "type": "struct",
      "type_mapping": [
        ["peer_id", "Vec<u8>"],
        ["score", "u128"],
      ],
    },
    "SubnetNodeInfo": {
      "type": "struct",
      "type_mapping": [
        ["subnet_node_id", "u32"],
        ["coldkey", "AccountId"],
        ["hotkey", "AccountId"],
        ["peer_id", "Vec<u8>"],
        ["bootstrap_peer_id", "Vec<u8>"],
        ["client_peer_id", "Vec<u8>"],
        ["classification", "SubnetNodeClassification"],
        ["delegate_reward_rate", "u128"],
        ["last_delegate_reward_rate_update", "u32"],
        ["a", "Vec<u8>"],
        ["b", "Vec<u8>"],
        ["c", "Vec<u8>"],
        ["stake_balance", "u128"],
      ],
    },
  }
}

class ChainDataType(Enum):
  """
  Enum for chain data types.
  """
  SubnetData = 1
  SubnetInfo = 2
  SubnetNode = 3
  RewardsData = 4
  SubnetNodeInfo = 5

def from_scale_encoding(
    input: Union[List[int], bytes, ScaleBytes],
    type_name: ChainDataType,
    is_vec: bool = False,
    is_option: bool = False,
) -> Optional[Dict]:
    """
    Returns the decoded data from the SCALE encoded input.

    Args:
      input (Union[List[int], bytes, ScaleBytes]): The SCALE encoded input.
      type_name (ChainDataType): The ChainDataType enum.
      is_vec (bool): Whether the input is a Vec.
      is_option (bool): Whether the input is an Option.

    Returns:
      Optional[Dict]: The decoded data
    """

    type_string = type_name.name
    if is_option:
      type_string = f"Option<{type_string}>"
    if is_vec:
      type_string = f"Vec<{type_string}>"

    return from_scale_encoding_using_type_string(input, type_string)

def from_scale_encoding_using_type_string(
  input: Union[List[int], bytes, ScaleBytes], type_string: str
) -> Optional[Dict]:
  """
  Returns the decoded data from the SCALE encoded input using the type string.

  Args:
    input (Union[List[int], bytes, ScaleBytes]): The SCALE encoded input.
    type_string (str): The type string.

  Returns:
    Optional[Dict]: The decoded data
  """
  if isinstance(input, ScaleBytes):
    as_scale_bytes = input
  else:
    if isinstance(input, list) and all([isinstance(i, int) for i in input]):
      vec_u8 = input
      as_bytes = bytes(vec_u8)
    elif isinstance(input, bytes):
      as_bytes = input
    else:
      raise TypeError("input must be a List[int], bytes, or ScaleBytes")

    as_scale_bytes = scalecodec.ScaleBytes(as_bytes)

  rpc_runtime_config = RuntimeConfiguration()
  rpc_runtime_config.update_type_registry(load_type_registry_preset("legacy"))
  rpc_runtime_config.update_type_registry(custom_rpc_type_registry)

  obj = rpc_runtime_config.create_scale_object(type_string, data=as_scale_bytes)

  return obj.decode()

@dataclass
class SubnetData:
  """
  Dataclass for subnet node info.
  """
  id: int
  name: str
  repo: str
  description: str
  misc: str
  state: str
  start_epoch: int

  @classmethod
  def fix_decoded_values(cls, data_decoded: Any) -> "SubnetData":
    """Fixes the values of the RewardsData object."""
    data_decoded["id"] = data_decoded["id"]
    data_decoded["name"] = data_decoded["name"]
    data_decoded["repo"] = data_decoded["repo"]
    data_decoded["description"] = data_decoded["description"]
    data_decoded["misc"] = data_decoded["misc"]
    data_decoded["state"] = data_decoded["state"]
    data_decoded["start_epoch"] = data_decoded["start_epoch"]

    return cls(**data_decoded)

  @classmethod
  def from_vec_u8(cls, vec_u8: List[int]) -> "SubnetData":
    """Returns a SubnetData object from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return SubnetData._get_null()

    decoded = from_scale_encoding(vec_u8, ChainDataType.SubnetData)

    if decoded is None:
      return SubnetData._get_null()

    decoded = SubnetData.fix_decoded_values(decoded)

    return decoded

  @classmethod
  def list_from_vec_u8(cls, vec_u8: List[int]) -> List["SubnetData"]:
    """Returns a list of SubnetData objects from a ``vec_u8``."""

    decoded_list = from_scale_encoding(
      vec_u8, ChainDataType.SubnetData, is_vec=True
    )
    if decoded_list is None:
      return []

    decoded_list = [
      SubnetData.fix_decoded_values(decoded) for decoded in decoded_list
    ]
    return decoded_list

  @staticmethod
  def _subnet_data_to_namespace(data) -> "SubnetData":
    """
    Converts a SubnetData object to a namespace.

    Args:
      rewards_data (SubnetData): The SubnetData object.

    Returns:
      SubnetData: The SubnetData object.
    """
    data = SubnetData(**data)

    return data

@dataclass
class SubnetInfo:
  """
  Dataclass for subnet node info.
  """
  id: int
  name: str
  repo: str
  description: str
  misc: str
  churn_limit: int
  min_stake: int
  max_stake: int
  delegate_stake_percentage: int
  registration_queue_epochs: int
  activation_grace_epochs: int
  queue_classification_epochs: int
  included_classification_epochs: int
  max_node_penalties: int
  initial_coldkeys: str
  owner: str
  registration_epoch: int

  @classmethod
  def fix_decoded_values(cls, data_decoded: Any) -> "SubnetInfo":
    """Fixes the values of the RewardsData object."""
    data_decoded["id"] = data_decoded["id"]
    data_decoded["name"] = data_decoded["name"]
    data_decoded["repo"] = data_decoded["repo"]
    data_decoded["description"] = data_decoded["description"]
    data_decoded["misc"] = data_decoded["misc"]
    data_decoded["churn_limit"] = data_decoded["churn_limit"]
    data_decoded["min_stake"] = data_decoded["min_stake"]
    data_decoded["max_stake"] = data_decoded["max_stake"]
    data_decoded["delegate_stake_percentage"] = data_decoded["delegate_stake_percentage"]
    data_decoded["registration_queue_epochs"] = data_decoded["registration_queue_epochs"]
    data_decoded["activation_grace_epochs"] = data_decoded["activation_grace_epochs"]
    data_decoded["queue_classification_epochs"] = data_decoded["queue_classification_epochs"]
    data_decoded["included_classification_epochs"] = data_decoded["included_classification_epochs"]
    data_decoded["max_node_penalties"] = data_decoded["max_node_penalties"]
    data_decoded["initial_coldkeys"] = data_decoded["initial_coldkeys"]
    data_decoded["owner"] = ss58_encode(
      data_decoded["owner"], 42
    )
    data_decoded["registration_epoch"] = data_decoded["registration_epoch"]

    return cls(**data_decoded)

  @classmethod
  def from_vec_u8(cls, vec_u8: List[int]) -> "SubnetInfo":
    """Returns a SubnetInfo object from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return SubnetInfo._get_null()

    decoded = from_scale_encoding(vec_u8, ChainDataType.SubnetInfo)

    if decoded is None:
      return SubnetInfo._get_null()

    decoded = SubnetInfo.fix_decoded_values(decoded)

    return decoded

  @classmethod
  def list_from_vec_u8(cls, vec_u8: List[int]) -> List["SubnetInfo"]:
    """Returns a list of SubnetInfo objects from a ``vec_u8``."""

    decoded_list = from_scale_encoding(
      vec_u8, ChainDataType.SubnetInfo, is_vec=True
    )
    if decoded_list is None:
      return []

    decoded_list = [
      SubnetInfo.fix_decoded_values(decoded) for decoded in decoded_list
    ]
    return decoded_list

  @staticmethod
  def _subnet_data_to_namespace(data) -> "SubnetInfo":
    """
    Converts a SubnetInfo object to a namespace.

    Args:
      rewards_data (SubnetInfo): The SubnetInfo object.

    Returns:
      SubnetInfo: The SubnetInfo object.
    """
    data = SubnetInfo(**data)

    return data

@dataclass
class RewardsData:
  """
  Dataclass for model peer metadata.
  """

  peer_id: str
  score: int

  @classmethod
  def fix_decoded_values(cls, rewards_data_decoded: Any) -> "RewardsData":
    """Fixes the values of the RewardsData object."""
    rewards_data_decoded["peer_id"] = rewards_data_decoded["peer_id"]
    rewards_data_decoded["score"] = rewards_data_decoded["score"]

    return cls(**rewards_data_decoded)

  @classmethod
  def from_vec_u8(cls, vec_u8: List[int]) -> "RewardsData":
    """Returns a RewardsData object from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return RewardsData._get_null()

    decoded = from_scale_encoding(vec_u8, ChainDataType.RewardsData)

    if decoded is None:
      return RewardsData._get_null()

    decoded = RewardsData.fix_decoded_values(decoded)

    return decoded

  @classmethod
  def list_from_vec_u8(cls, vec_u8: List[int]) -> List["RewardsData"]:
    """Returns a list of RewardsData objects from a ``vec_u8``."""

    decoded_list = from_scale_encoding(
      vec_u8, ChainDataType.RewardsData, is_vec=True
    )
    if decoded_list is None:
      return []

    decoded_list = [
      RewardsData.fix_decoded_values(decoded) for decoded in decoded_list
    ]
    return decoded_list

  @classmethod
  def list_from_scale_info(cls, scale_info: Any) -> List["RewardsData"]:
    """Returns a list of RewardsData objects from a ``decoded_list``."""

    encoded_list = []
    for code in map(ord, str(scale_info)):
      encoded_list.append(code)


    decoded = ''.join(map(chr, encoded_list))

    json_data = ast.literal_eval(json.dumps(decoded))

    decoded_list = []
    for item in scale_info:
      decoded_list.append(
        RewardsData(
          peer_id=str(item["peer_id"]),
          score=int(str(item["score"])),
        )
      )

    return decoded_list

  @staticmethod
  def _rewards_data_to_namespace(rewards_data) -> "RewardsData":
    """
    Converts a RewardsData object to a namespace.

    Args:
      rewards_data (RewardsData): The RewardsData object.

    Returns:
      RewardsData: The RewardsData object.
    """
    data = RewardsData(**rewards_data)

    return data

  @staticmethod
  def _get_null() -> "RewardsData":
    rewards_data = RewardsData(
      peer_id="",
      score=0,
    )
    return rewards_data

@dataclass
class SubnetNodeInfo:
  """
  Dataclass for subnet node info.
  """
  subnet_node_id: int
  coldkey: str
  hotkey: str
  peer_id: str
  bootstrap_peer_id: str
  client_peer_id: str
  classification: str
  delegate_reward_rate: int
  last_delegate_reward_rate_update: int
  a: str
  b: str
  c: str
  stake_balance: int

  @classmethod
  def fix_decoded_values(cls, data_decoded: Any) -> "SubnetNodeInfo":
    """Fixes the values of the RewardsData object."""
    data_decoded["subnet_node_id"] = data_decoded["subnet_node_id"]
    data_decoded["coldkey"] = ss58_encode(
      data_decoded["coldkey"], 42
    )
    data_decoded["hotkey"] = ss58_encode(
      data_decoded["hotkey"], 42
    )
    data_decoded["peer_id"] = data_decoded["peer_id"]
    data_decoded["bootstrap_peer_id"] = data_decoded["bootstrap_peer_id"]
    data_decoded["client_peer_id"] = data_decoded["client_peer_id"]
    data_decoded["classification"] = data_decoded["classification"]
    data_decoded["delegate_reward_rate"] = data_decoded["delegate_reward_rate"]
    data_decoded["last_delegate_reward_rate_update"] = data_decoded["last_delegate_reward_rate_update"]
    data_decoded["a"] = data_decoded["a"]
    data_decoded["b"] = data_decoded["b"]
    data_decoded["c"] = data_decoded["c"]

    return cls(**data_decoded)

  @classmethod
  def from_vec_u8(cls, vec_u8: List[int]) -> "SubnetNodeInfo":
    """Returns a SubnetNodeInfo object from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return SubnetNodeInfo._get_null()

    decoded = from_scale_encoding(vec_u8, ChainDataType.SubnetNodeInfo)

    if decoded is None:
      return SubnetNodeInfo._get_null()

    decoded = SubnetNodeInfo.fix_decoded_values(decoded)

    return decoded

  @classmethod
  def list_from_vec_u8(cls, vec_u8: List[int]) -> List["SubnetNodeInfo"]:
    """Returns a list of SubnetNodeInfo objects from a ``vec_u8``."""

    decoded_list = from_scale_encoding(
      vec_u8, ChainDataType.SubnetNodeInfo, is_vec=True
    )
    if decoded_list is None:
      return []

    decoded_list = [
      SubnetNodeInfo.fix_decoded_values(decoded) for decoded in decoded_list
    ]
    return decoded_list

  @staticmethod
  def _subnet_node_info_to_namespace(data) -> "SubnetNodeInfo":
    """
    Converts a SubnetNodeInfo object to a namespace.

    Args:
      rewards_data (SubnetNodeInfo): The SubnetNodeInfo object.

    Returns:
      SubnetNodeInfo: The SubnetNodeInfo object.
    """
    data = SubnetNodeInfo(**data)

    return data

  @staticmethod
  def _get_null() -> "SubnetNodeInfo":
    subnet_node_info = SubnetNodeInfo(
      subnet_node_id=0,
      coldkey="000000000000000000000000000000000000000000000000",
      hotkey="000000000000000000000000000000000000000000000000",
      peer_id="000000000000000000000000000000000000000000000000",
      bootstrap_peer_id="000000000000000000000000000000000000000000000000",
      client_peer_id="000000000000000000000000000000000000000000000000",
      classification="",
      delegate_reward_rate=0,
      last_delegate_reward_rate_update=0,
      a="",
      b="",
      c="",
      stake_balance=0,
    )
    return subnet_node_info

@dataclass
class SubnetNode:
  """
  Dataclass for model peer metadata.
  """
  id: int
  hotkey: str
  peer_id: str
  bootstrap_peer_id: str
  client_peer_id: str
  classification: str
  delegate_reward_rate: int
  last_delegate_reward_rate_update: int
  a: str
  b: str
  c: str

  @classmethod
  def fix_decoded_values(cls, data_decoded: Any) -> "SubnetNode":
    """Fixes the values of the RewardsData object."""
    data_decoded["id"] = data_decoded["id"]
    data_decoded["hotkey"] = ss58_encode(
      data_decoded["hotkey"], 42
    )
    data_decoded["peer_id"] = data_decoded["peer_id"]
    data_decoded["bootstrap_peer_id"] = data_decoded["bootstrap_peer_id"]
    data_decoded["client_peer_id"] = data_decoded["client_peer_id"]
    data_decoded["classification"] = data_decoded["classification"]
    data_decoded["delegate_reward_rate"] = data_decoded["delegate_reward_rate"]
    data_decoded["last_delegate_reward_rate_update"] = data_decoded["last_delegate_reward_rate_update"]
    data_decoded["a"] = data_decoded["a"]
    data_decoded["b"] = data_decoded["b"]
    data_decoded["c"] = data_decoded["c"]

    return cls(**data_decoded)

  @classmethod
  def list_from_vec_u8(cls, vec_u8: List[int]) -> List["SubnetNode"]:
    """Returns a list of SubnetNode objects from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return []

    decoded_list = from_scale_encoding(
      vec_u8, ChainDataType.SubnetNode, is_vec=True
    )

    if decoded_list is None:
      return []

    decoded_list = [
      SubnetNode.fix_decoded_values(decoded) for decoded in decoded_list
    ]
    return decoded_list

  @classmethod
  def from_vec_u8(cls, vec_u8: List[int]) -> "SubnetNode":
    """Returns a SubnetNodeInfo object from a ``vec_u8``."""

    if len(vec_u8) == 0:
      return SubnetNode._get_null()

    decoded = from_scale_encoding(vec_u8, ChainDataType.SubnetNode)

    if decoded is None:
      return SubnetNode._get_null()

    decoded = SubnetNode.fix_decoded_values(decoded)

    return decoded

  @staticmethod
  def _subnet_node_to_namespace(data) -> "SubnetNode":
    """
    Converts a SubnetNode object to a namespace.

    Args:
      rewards_data (SubnetNode): The SubnetNode object.

    Returns:
      SubnetNode: The SubnetNode object.
    """
    data = SubnetNode(**data)

    return data

  @staticmethod
  def _get_null() -> "SubnetNode":
    subnet_node = SubnetNode(
      id=0,
      hotkey="000000000000000000000000000000000000000000000000",
      peer_id="000000000000000000000000000000000000000000000000",
      bootstrap_peer_id="000000000000000000000000000000000000000000000000",
      client_peer_id="000000000000000000000000000000000000000000000000",
      classification="",
      delegate_reward_rate=0,
      last_delegate_reward_rate_update=0,
      a="",
      b="",
      c="",
    )
    return subnet_node
