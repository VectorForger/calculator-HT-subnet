from __future__ import annotations

from typing import Optional, Union

from mesh.dht.routing import DHTID, BinaryDHTValue, Subkey
from mesh.utils.serializer_v2 import MSGPackSerializer
from mesh.utils.timed_storage_v2 import DHTExpiration, KeyType, TimedStorage, ValueType, get_dht_time


@MSGPackSerializer.ext_serializable(0x50)
class DictionaryDHTValue(TimedStorage[Subkey, BinaryDHTValue]):
    """a dictionary-like DHT value type that maps sub-keys to values with individual expirations"""

    latest_expiration_time = float("-inf")
    latest_created_at = float("-inf")

    def store(self, key: KeyType, value: ValueType, expiration_time: DHTExpiration) -> bool:
        self.latest_expiration_time = max(self.latest_expiration_time, expiration_time)
        self.latest_created_at = max(self.latest_created_at, get_dht_time())
        return super().store(key, value, expiration_time)

    def packb(self) -> bytes:
        """custom behavior for MSGPackSerializer.dumps"""
        packed_items = [[key, value, expiration_time, created_at] for key, (value, expiration_time, created_at) in self.items()]
        return MSGPackSerializer.dumps([self.maxsize, self.latest_expiration_time, self.latest_created_at, packed_items])

    @classmethod
    def unpackb(cls, raw: bytes) -> DictionaryDHTValue:
        maxsize, latest_expiration_time, latest_created_at, items = MSGPackSerializer.loads(raw)
        with DictionaryDHTValue(maxsize).freeze() as new_dict:
            for key, value, expiration_time, created_at in items:
                new_dict.store(key, value, expiration_time)
            new_dict.latest_expiration_time = latest_expiration_time
            new_dict.latest_created_at = latest_created_at
            return new_dict


class DHTLocalStorage(TimedStorage[DHTID, Union[BinaryDHTValue, DictionaryDHTValue]]):
    """A dictionary-like storage that can store binary values and/or nested dictionaries until expiration"""

    def store(
        self, key: DHTID, value: BinaryDHTValue, expiration_time: DHTExpiration, subkey: Optional[Subkey] = None
    ) -> bool:
        """
        Store a (key, value) pair locally at least until expiration_time. See class docstring for details.
        If subkey is not None, adds a subkey-value pair to a dictionary associated with :key: (see store_subkey below)
        :returns: True if new value was stored, False it was rejected (current value is newer)
        """
        if subkey is not None:  # add one sub-key
            return self.store_subkey(key, subkey, value, expiration_time)
        else:  # store regular key
            return super().store(key, value, expiration_time)

    def store_subkey(self, key: DHTID, subkey: Subkey, value: BinaryDHTValue, expiration_time: DHTExpiration) -> bool:
        """
        Save a (sub-key, value) into a dictionary associated with a given key.
         1) if self[key] is empty, create a new dictionary and add sub-key there
         2) if self[key] is a dictionary (DictionaryDHTValue), store {sub-key: value, expiration} to that storage
         3) if self[key] is a normal value with smaller expiration time, overwrite it with a dictionary and add sub-key
        :returns: True if new entry was stored, False it was rejected (current value is newer)
        """
        previous_value, previous_expiration_time, previous_created_at = self.get(key) or (b"", -float("inf"), -float("inf"))
        if isinstance(previous_value, BinaryDHTValue) and expiration_time > previous_expiration_time:
            new_storage = DictionaryDHTValue()
            new_storage.store(subkey, value, expiration_time)
            return super().store(key, new_storage, new_storage.latest_expiration_time)
        elif isinstance(previous_value, DictionaryDHTValue):
            if expiration_time > previous_value.latest_expiration_time:
                super().store(key, previous_value, expiration_time)  # refresh expiration time
            return previous_value.store(subkey, value, expiration_time)
        else:
            return False
