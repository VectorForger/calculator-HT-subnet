import dataclasses
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import pydantic.v1 as pydantic

from mesh import PeerID

# from mesh.pallet.module_uid import ModuleUID

ModuleUID = str
UID_DELIMITER = "."  # delimits parts of one module uid, e.g. "bloom.transformer.h.4.self_attention"
CHAIN_DELIMITER = " "  # delimits multiple uids in a sequence, e.g. "bloom.layer3 bloom.layer4"


def parse_uid(uid: ModuleUID) -> Tuple[str, int]: # type: ignore
    assert CHAIN_DELIMITER not in uid, "parse_uid() does not support chained UIDs"
    dht_prefix, index = uid.split(UID_DELIMITER)
    return dht_prefix, int(index)


@pydantic.dataclasses.dataclass
class ModelInfo:
    num_blocks: pydantic.conint(ge=1, strict=True) # type: ignore
    repository: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, source: dict):
        return cls(**source)


class ServerState(Enum):
    OFFLINE = 0
    JOINING = 1
    ONLINE = 2

class ServerClass(Enum):
    HOSTER = "hoster"
    VALIDATOR = "validator"

RPS = pydantic.confloat(ge=0, allow_inf_nan=False, strict=True)

"""
Create server node data to store
"""
@pydantic.dataclasses.dataclass
class ServerInfo:
    state: ServerState
    role: ServerClass
    throughput: RPS

    public_name: Optional[str] = None
    version: Optional[str] = None

    inference_rps: Optional[RPS] = None # type: ignore

    using_relay: Optional[bool] = None
    next_pings: Optional[Dict[str, pydantic.confloat(ge=0, strict=True)]] = None # type: ignore

    def to_tuple(self) -> Tuple[int, str, float, dict]:
        extra_info = dataclasses.asdict(self)
        del extra_info["state"], extra_info["throughput"], extra_info["role"]
        return (self.state.value, self.role.value, self.throughput, extra_info)

    @classmethod
    def from_tuple(cls, source: tuple):
        if not isinstance(source, tuple):
            raise TypeError(f"Expected a tuple, got {type(source)}")
        state, role, throughput = source[:3]
        extra_info = source[3] if len(source) > 2 else {}
        # pydantic will validate existing fields and ignore extra ones
        return cls(state=ServerState(state), role=role, throughput=throughput, **extra_info)

@dataclasses.dataclass
class RemoteModuleInfo:
    """A remote module"""
    peer_id: PeerID
    server: ServerInfo

@dataclasses.dataclass
class RemoteInfo:
    """A chain of remote blocks served by one specific remote peer"""

    # peer_id: PeerID
    peer_id: str
    server_info: ServerInfo

    @property
    def state(self) -> ServerState:
        return self.server_info.state

    @property
    def throughput(self) -> float:
        return self.server_info.throughput

@dataclasses.dataclass
class RemoteHosterInfo:
    """A chain of remote blocks served by one specific remote peer"""

    peer_id: str
    server_info: ServerInfo

    @property
    def state(self) -> ServerState:
        return self.server_info.state

    @property
    def throughput(self) -> float:
        return self.server_info.throughput

RPCInfo = Dict[str, Any]

Handle = int


@dataclasses.dataclass(frozen=True)
class InferenceMetadata:
    uid: ModuleUID
    prefix_length: int
    cache_handles: Tuple[Handle, ...]
    active_adapter: Optional[str]

class QuantType(Enum):
    NONE = 0
    INT8 = 1  # 8-bit as in the LLM.int8() paper
    NF4 = 2  # 4-bit as in the QLoRA paper
