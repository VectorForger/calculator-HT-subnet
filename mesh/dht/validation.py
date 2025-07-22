import dataclasses
from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Iterable

from mesh.substrate.chain_functions import Hypertensor


@dataclasses.dataclass(init=True, repr=True, frozen=True)
class DHTRecord:
    key: bytes
    subkey: bytes
    value: bytes
    expiration_time: float

class DHTRecordRequestType(Enum):
    GET = "get"
    POST = "post"

class RecordValidatorBase(ABC):
    """
    Record validators are a generic mechanism for checking the DHT records including:
      - Enforcing a data schema (e.g. checking content types)
      - Enforcing security requirements (e.g. allowing only the owner to update the record)
    """

    @abstractmethod
    def validate(self, record: DHTRecord, type: DHTRecordRequestType) -> bool:
        """
        Should return whether the `record` is valid based on request type.
        The valid records should have been extended with sign_value().

        validate() is called when another DHT peer:
          - Asks us to store the record
          - Returns the record by our request
        """

        pass

    def sign_value(self, record: DHTRecord) -> bytes:
        """
        Should return `record.value` extended with the record's signature.

        Note: there's no need to overwrite this method if a validator doesn't use a signature.

        sign_value() is called after the application asks the DHT to store the record.
        """

        return record.value

    def strip_value(self, record: DHTRecord) -> bytes:
        """
        Should return `record.value` stripped of the record's signature.
        strip_value() is only called if validate() was successful.

        Note: there's no need to overwrite this method if a validator doesn't use a signature.

        strip_value() is called before the DHT returns the record by the application's request.
        """

        return record.value

    @property
    def priority(self) -> int:
        """
        Defines the order of applying this validator with respect to other validators.

        The validators are applied:
          - In order of increasing priority for signing a record
          - In order of decreasing priority for validating and stripping a record
        """

        return 0

    def merge_with(self, other: "RecordValidatorBase") -> bool:
        """
        By default, all validators are applied sequentially (i.e. we require all validate() calls
        to return True for a record to be validated successfully).

        However, you may want to define another policy for combining your validator classes
        (e.g. for schema validators, we want to require only one validate() call to return True
        because each validator bears a part of the schema).

        This can be achieved with overriding merge_with(). It should:

          - Return True if it has successfully merged the `other` validator to `self`,
            so that `self` became a validator that combines the old `self` and `other` using
            the necessary policy. In this case, `other` should remain unchanged.

          - Return False if the merging has not happened. In this case, both `self` and `other`
            should remain unchanged. The DHT will try merging `other` to another validator or
            add it as a separate validator (to be applied sequentially).
        """

        return False


class CompositeValidator(RecordValidatorBase):
    def __init__(self, validators: Iterable[RecordValidatorBase] = ()):
        self._validators = []
        self.extend(validators)

    def extend(self, validators: Iterable[RecordValidatorBase]) -> None:
        for new_validator in validators:
            for existing_validator in self._validators:
                if existing_validator.merge_with(new_validator):
                    break
            else:
                self._validators.append(new_validator)
        self._validators.sort(key=lambda item: item.priority)

    def validate(self, record: DHTRecord, type: DHTRecordRequestType) -> bool:
        for i, validator in enumerate(reversed(self._validators)):
            if not validator.validate(record, type):
                return False
            if i < len(self._validators) - 1:
                record = dataclasses.replace(record, value=validator.strip_value(record))
        return True

    def sign_value(self, record: DHTRecord) -> bytes:
        for validator in self._validators:
            record = dataclasses.replace(record, value=validator.sign_value(record))
        return record.value

    def strip_value(self, record: DHTRecord) -> bytes:
        for validator in reversed(self._validators):
            record = dataclasses.replace(record, value=validator.strip_value(record))
        return record.value



class PredicateValidator(RecordValidatorBase):
    """
    A general-purpose DHT validator that delegates all validation logic to a custom callable.

    This is a minimal validator that can enforce any condition on the entire DHTRecord.
    Useful for filtering keys, expiration time, value content, or any combination thereof.

    Example:
        def my_record_predicate(record: DHTRecord) -> bool:
            now = time.time()

            if not record.key.startswith(b"score:"):
                logger.debug(f"Rejected record: key {record.key} does not start with b'score:'")
                return False

            if len(record.value) <= 10:
                logger.debug(f"Rejected record: value length {len(record.value)} <= 10")
                return False

            if not (now <= record.expiration_time <= now + 3600):
                logger.debug(f"Rejected record: expiration_time {record.expiration_time} outside next hour")
                return False

            return True

        PredicateValidator(record_predicate=my_record_predicate)

    This can be used to ensure keys match a specific format, or nodes are doing something within a certain period
    of time in relation to the blockchain, i.e., ensuring a commit-reveal schema where the commit is submitted by the
    first half of the epoch and the reveal is done on the second half of the epoch.

    Attributes:
        record_predicate (Callable[[DHTRecord], bool]): A user-defined function that receives a record and returns True if valid.
    """

    def __init__(
        self,
        record_predicate: Callable[[DHTRecord], bool] = lambda r: True,
    ):
        self.record_predicate = record_predicate

    def validate(self, record: DHTRecord, type: DHTRecordRequestType) -> bool:
        return self.record_predicate(record)

    def sign_value(self, record: DHTRecord) -> bytes:
        return record.value

    def strip_value(self, record: DHTRecord) -> bytes:
        return record.value

    def merge_with(self, other: RecordValidatorBase) -> bool:
        if not isinstance(other, PredicateValidator):
            return False

        # Ignore another KeyValidator instance (it doesn't make sense to have several
        # instances of this class) and report successful merge
        return True

class HypertensorPredicateValidator(RecordValidatorBase):
    """
    A general-purpose DHT validator that delegates all validation logic to a custom callable
    that takes in a epoch data function.

    This is a minimal validator that can enforce any condition on the entire DHTRecord.
    Useful for filtering keys, expiration time, value content, or any combination thereof.

    This can be used to ensure keys match a specific format, or nodes are doing something within a certain period
    of time in relation to the blockchain, i.e., ensuring a commit-reveal schema where the commit is submitted by the
    first half of the epoch and the reveal is done on the second half of the epoch.

    Attributes:
        record_predicate (Callable[[DHTRecord], bool]): A user-defined function that receives a record and returns True if valid.
    """

    def __init__(
        self,
        hypertensor: Hypertensor,
        record_predicate: Callable[[DHTRecord, DHTRecordRequestType], bool] = lambda r: True
    ):
        self.record_predicate = record_predicate
        self.hypertensor = hypertensor

    def validate(self, record: DHTRecord, type: DHTRecordRequestType) -> bool:
        return self.record_predicate(record, type, self._epoch_data())

    def sign_value(self, record: DHTRecord) -> bytes:
        return record.value

    def strip_value(self, record: DHTRecord) -> bytes:
        return record.value

    def _epoch_data(self):
        # Get epoch data from the blockchain and calulate the remaining
        return self.hypertensor.get_epoch_data()

    def merge_with(self, other: RecordValidatorBase) -> bool:
        if not isinstance(other, HypertensorPredicateValidator):
            return False

        # Ignore another KeyValidator instance (it doesn't make sense to have several
        # instances of this class) and report successful merge
        return True

class HypertensorSlotPredicateValidator(RecordValidatorBase):
    """
    A general-purpose DHT validator that delegates all validation logic to a custom callable.

    Uses the Hypertensor `get_subnet_epoch_data` as a parameter for the predicate

    This is a minimal validator that can enforce any condition on the entire DHTRecord.
    Useful for filtering keys, expiration time, value content, or any combination thereof.

    This can be used to ensure keys match a specific format, or nodes are doing something within a certain period
    of time in relation to the blockchain, i.e., ensuring a commit-reveal schema where the commit is submitted by the
    first half of the epoch and the reveal is done on the second half of the epoch.

    Attributes:
        record_predicate (Callable[[DHTRecord], bool]): A user-defined function that receives a record and returns True if valid.
    """

    def __init__(
        self,
        hypertensor: Hypertensor,
        subnet_id: int,
        record_predicate: Callable[[DHTRecord, DHTRecordRequestType], bool] = lambda r: True
    ):
        self.record_predicate = record_predicate
        self.hypertensor = hypertensor
        self.subnet_id = subnet_id
        self.slot = None

    def validate(self, record: DHTRecord, type: DHTRecordRequestType) -> bool:
        return self.record_predicate(record, type, self._epoch_data())

    def sign_value(self, record: DHTRecord) -> bytes:
        return record.value

    def strip_value(self, record: DHTRecord) -> bytes:
        return record.value

    def _epoch_data(self):
        # Get epoch data from the blockchain and calulate the remaining
        if self.slot is None:
            self.slot = self.hypertensor.get_subnet_slot(self.subnet_id)
        return self.hypertensor.get_subnet_epoch_data(self.slot)

    def merge_with(self, other: RecordValidatorBase) -> bool:
        if not isinstance(other, HypertensorSlotPredicateValidator):
            return False

        # Ignore another KeyValidator instance (it doesn't make sense to have several
        # instances of this class) and report successful merge
        return True
