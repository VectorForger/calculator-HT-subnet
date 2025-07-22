from dataclasses import dataclass
from enum import Enum


class Role(Enum):
    HOSTER = "hoster"
    VALIDATOR = "validator"


@dataclass
class NodeRole:
    role: Role
