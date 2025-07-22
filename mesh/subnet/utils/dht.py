"""
Utilities for declaring and retrieving active model layers using a shared DHT.
"""
from __future__ import annotations

import math
from functools import partial
from typing import Any, Dict, List, Optional, Union

from mesh.dht import DHT, DHTNode, DHTValue
from mesh.dht.crypto import Ed25519SignatureValidator, RSASignatureValidator
from mesh.dht.routing import DHTKey
from mesh.p2p import PeerID
from mesh.subnet.data_structures import RemoteInfo, RemoteModuleInfo, ServerInfo, ServerState
from mesh.utils import DHTExpiration, MPFuture, get_dht_time, get_logger

logger = get_logger(__name__)

def declare_node(
    dht: DHT,
    key: DHTKey,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
    wait: bool = True,
):
    """
    Declare your node; update timestamps if declared previously

    :param key: key to store under
    :param wait: if True, awaits for declaration to finish, otherwise runs in background
    :param throughput: specify your performance in terms of compute throughput
    :param expiration_time: declared modules will be visible for this many seconds
    :returns: if wait, returns store status for every key (True = store succeeded, False = store rejected)
    """
    return dht.run_coroutine(
        partial(
            _store_node,
            key=key,
            subkey=dht.peer_id.to_base58(),
            server_info=server_info,
            expiration_time=expiration_time
        ),
        return_future=not wait,
    )

async def _store_node(
    dht: DHT,
    node: DHTNode,
    key: DHTKey,
    subkey: Any,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
) -> Dict[DHTKey, bool]:
    return await node.store(
        key=key,
        subkey=subkey,
        value=server_info.to_tuple(),
        expiration_time=expiration_time,
        num_workers=1,
    )

def get_node_infos(
    dht: DHT,
    uid: Any, # type: ignore
    expiration_time: Optional[DHTExpiration] = None,
    *,
    latest: bool = False,
    return_future: bool = False,
) -> Union[List[RemoteModuleInfo], MPFuture]:
    return dht.run_coroutine(
        partial(
            _get_node_infos,
            uid=uid,
            expiration_time=expiration_time,
            latest=latest,
        ),
        return_future=return_future,
    )

async def _get_node_infos(
    dht: DHT,
    node: DHTNode,
    uid: Any, # type: ignore
    expiration_time: Optional[DHTExpiration],
    latest: bool,
) -> List[RemoteModuleInfo]:
    if latest:
        assert expiration_time is None, "You should define either `expiration_time` or `latest`, not both"
        expiration_time = math.inf
    elif expiration_time is None:
        expiration_time = get_dht_time()
    num_workers = 1 if dht.num_workers is None else 1
    found: Dict[Any, DHTValue] = await node.get_many([uid], expiration_time, num_workers=num_workers) # type: ignore

    if found[uid] is None:
        return []
    peers = []
    inner_dict = found[uid].value

    modules: List[RemoteModuleInfo] = []
    for subkey, values in inner_dict.items():
        peers.append(PeerID.from_base58(subkey))
        server_info = ServerInfo.from_tuple(values.value)

        modules.append(
            RemoteModuleInfo(
                peer_id=PeerID.from_base58(subkey),
                server=server_info
            )
        )

    return modules

def store_data(
    dht: DHT,
    key: DHTKey,
    subkey: Optional[Any],
    data: Any,
    expiration_time: DHTExpiration,
    wait: bool = True,
):
    return dht.run_coroutine(
        partial(_store_data, key=key, subkey=subkey, value=data, expiration_time=expiration_time),
        return_future=False,
    )

async def _store_data(
    dht: DHT,
    node: DHTNode,
    key: Any,
    subkey: Optional[Any],
    value: Any,
    expiration_time: DHTExpiration,
) -> Dict[DHTKey, bool]:
    return await node.store(
        key=key,
        subkey=subkey,
        value=value,
        expiration_time=expiration_time,
        num_workers=32,
    )

def get_many_data(
    dht: DHT,
    uid: Any,
    expiration_time: Optional[DHTExpiration] = None,
    *,
    latest: bool = False,
    return_future: bool = False,
):
    return dht.run_coroutine(
        partial(
            _get_data,
            key=uid,
            expiration_time=expiration_time,
            latest=latest,
        ),
        return_future=return_future,
    )

async def _get_data(
    dht: DHT,
    node: DHTNode,
    key: Any,
    expiration_time: Optional[DHTExpiration],
    latest: bool,
) -> Any:
    found = await node.get_many([key], expiration_time)
    return found


"""
Validated entries
"""

def declare_node_rsa(
    dht: DHT,
    key: DHTKey,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
    wait: bool = True,
    record_validator: Optional[RSASignatureValidator] = None,
):
    """
    Declare your node; update timestamps if declared previously

    :param key: key to store under
    :param wait: if True, awaits for declaration to finish, otherwise runs in background
    :param throughput: specify your performance in terms of compute throughput
    :param expiration_time: declared modules will be visible for this many seconds
    :returns: if wait, returns store status for every key (True = store succeeded, False = store rejected)
    """

    return dht.run_coroutine(
        partial(_declare_declare_node_rsa,
            key=key,
            server_info=server_info,
            expiration_time=expiration_time,
            record_validator=record_validator
        ),
        return_future=not wait,
    )

async def _declare_declare_node_rsa(
    dht: DHT,
    node: DHTNode,
    key: DHTKey,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
    record_validator: Optional[RSASignatureValidator] = None,
) -> Dict[Any, bool]:
    subkey = dht.peer_id.to_base58() if record_validator is None else dht.peer_id.to_base58().encode() + record_validator.local_public_key

    return await node.store(
        keys=key,
        subkey=subkey,
        values=server_info.to_tuple(),
        expiration_time=expiration_time,
        num_workers=32,
    )

def declare_node_ed25519(
    dht: DHT,
    key: DHTKey,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
    wait: bool = True,
    record_validator: Optional[Ed25519SignatureValidator] = None,
):
    """
    Declare your node; update timestamps if declared previously

    :param key: key to store under
    :param wait: if True, awaits for declaration to finish, otherwise runs in background
    :param throughput: specify your performance in terms of compute throughput
    :param expiration_time: declared modules will be visible for this many seconds
    :returns: if wait, returns store status for every key (True = store succeeded, False = store rejected)
    """

    return dht.run_coroutine(
        partial(_declare_declare_node_ed25519,
            key=key,
            server_info=server_info,
            expiration_time=expiration_time,
            record_validator=record_validator
        ),
        return_future=not wait,
    )

async def _declare_declare_node_ed25519(
    dht: DHT,
    node: DHTNode,
    key: DHTKey,
    server_info: ServerInfo,
    expiration_time: DHTExpiration,
    record_validator: Optional[Ed25519SignatureValidator] = None,
) -> Dict[Any, bool]:
    subkey = dht.peer_id.to_base58() if record_validator is None else dht.peer_id.to_base58().encode() + record_validator.local_public_key

    return await node.store(
        keys=key,
        subkey=subkey,
        values=server_info.to_tuple(),
        expiration_time=expiration_time,
        num_workers=32,
    )

def store_data_rsa(
    dht: DHT,
    key: DHTKey,
    data: Any, # fill in the data type here
    expiration_time: DHTExpiration,
    wait: bool = True,
    subkey: Optional[Any] = None,
    record_validator: Optional[RSASignatureValidator] = None,
):
    dht.run_coroutine(
        partial(_store_data_rsa, key=key, value=data, expiration_time=expiration_time, subkey=subkey, record_validator=record_validator),
        return_future=False,
    )

async def _store_data_rsa(
    dht: DHT,
    node: DHTNode,
    key: Any,
    value: Any,
    expiration_time: DHTExpiration,
    subkey: Optional[Any] = None,
    record_validator: Optional[RSASignatureValidator] = None,
) -> Dict[DHTKey, bool]:
    subkey = dht.peer_id.to_base58() if record_validator is None else dht.peer_id.to_base58().encode() + record_validator.local_public_key

    return await node.store(
        key=key,
        subkey=subkey,
        value=value,
        expiration_time=expiration_time,
        num_workers=32,
    )


def store_data_ed25519(
    dht: DHT,
    key: DHTKey,
    data: Any, # fill in the data type here
    expiration_time: DHTExpiration,
    wait: bool = True,
    subkey: Optional[Any] = None,
    record_validator: Optional[Ed25519SignatureValidator] = None,
):
    dht.run_coroutine(
        partial(_store_data_ed25519, key=key, subkey=subkey, value=data, expiration_time=expiration_time, record_validator=record_validator),
        return_future=False,
    )

async def _store_data_ed25519(
    dht: DHT,
    node: DHTNode,
    key: Any,
    value: Any,
    expiration_time: DHTExpiration,
    subkey: Optional[Any] = None,
    record_validator: Optional[Ed25519SignatureValidator] = None,
) -> Dict[DHTKey, bool]:
    subkey = dht.peer_id.to_base58() if record_validator is None else dht.peer_id.to_base58().encode() + record_validator.local_public_key

    return await node.store(
        key=key,
        subkey=subkey,
        value=value,
        expiration_time=expiration_time,
        num_workers=32,
    )

# old

# def declare_active_modules(
#     dht: DHT,
#     uids: Sequence[Any], # type: ignore
#     server_info: ServerInfo,
#     expiration_time: DHTExpiration,
#     wait: bool = True,
# ) -> Union[Dict[Any, bool], MPFuture[Dict[Any, bool]]]: # type: ignore
#     """
#     Declare that your node serves the specified modules; update timestamps if declared previously

#     :param uids: a list of module ids to declare
#     :param wait: if True, awaits for declaration to finish, otherwise runs in background
#     :param throughput: specify your performance in terms of compute throughput
#     :param expiration_time: declared modules will be visible for this many seconds
#     :returns: if wait, returns store status for every key (True = store succeeded, False = store rejected)
#     """
#     if isinstance(uids, str):
#         uids = [uids]
#     if not isinstance(uids, list):
#         uids = list(uids)
#     for uid in uids:
#         assert isinstance(uid, Any) and UID_DELIMITER in uid and CHAIN_DELIMITER not in uid

#     return dht.run_coroutine(
#         partial(_declare_active_modules, uids=uids, server_info=server_info, expiration_time=expiration_time),
#         return_future=not wait,
#     )


# async def _declare_active_modules(
#     dht: DHT,
#     node: DHTNode,
#     uids: List[Any], # type: ignore
#     server_info: ServerInfo,
#     expiration_time: DHTExpiration,
# ) -> Dict[Any, bool]: # type: ignore
#     num_workers = len(uids) if dht.num_workers is None else min(len(uids), dht.num_workers)
#     return await node.store_many(
#         keys=uids,
#         subkeys=[dht.peer_id.to_base58()] * len(uids),
#         values=[server_info.to_tuple()] * len(uids),
#         expiration_time=expiration_time,
#         num_workers=num_workers,
#     )


# def get_remote_module_infos(
#     dht: DHT,
#     uids: Sequence[Any], # type: ignore
#     expiration_time: Optional[DHTExpiration] = None,
#     active_adapter: Optional[str] = None,
#     *,
#     latest: bool = False,
#     return_future: bool = False,
# ) -> Union[List[RemoteModuleInfo], MPFuture]:
#     return dht.run_coroutine(
#         partial(
#             _get_remote_module_infos,
#             uids=uids,
#             active_adapter=active_adapter,
#             expiration_time=expiration_time,
#             latest=latest,
#         ),
#         return_future=return_future,
#     )


# async def _get_remote_module_infos(
#     dht: DHT,
#     node: DHTNode,
#     uids: List[Any], # type: ignore
#     active_adapter: Optional[str],
#     expiration_time: Optional[DHTExpiration],
#     latest: bool,
# ) -> List[RemoteModuleInfo]:
#     if latest:
#         assert expiration_time is None, "You should define either `expiration_time` or `latest`, not both"
#         expiration_time = math.inf
#     elif expiration_time is None:
#         expiration_time = get_dht_time()
#     num_workers = len(uids) if dht.num_workers is None else min(len(uids), dht.num_workers)
#     found: Dict[Any, DHTValue] = await node.get_many(uids, expiration_time, num_workers=num_workers) # type: ignore

#     modules = [RemoteModuleInfo(uid=uid, servers={}) for uid in uids]
#     for module_info in modules:
#         metadata = found[module_info.uid]
#         if metadata is None or not isinstance(metadata.value, dict):
#             if metadata is not None:
#                 logger.warning(f"Incorrect metadata for {module_info.uid}: {metadata}")
#             continue

#         for peer_id, server_info in metadata.value.items():
#             try:
#                 peer_id = PeerID.from_base58(peer_id)
#                 server_info = ServerInfo.from_tuple(server_info.value)

#                 if active_adapter and active_adapter not in server_info.adapters:
#                     logger.debug(f"Skipped server {peer_id} since it does not have adapter {active_adapter}")
#                     continue

#                 module_info.servers[peer_id] = server_info
#             except (TypeError, ValueError) as e:
#                 logger.warning(f"Incorrect peer entry for uid={module_info.uid}, peer_id={peer_id}: {e}")
#     return modules


def get_routing_table(
    dht: DHT,
    *,
    return_future: bool = False,
):
    return dht.run_coroutine(
        partial(
            _get_routing_table,
        ),
        return_future=return_future,
    )

async def _get_routing_table(
    dht: DHT,
    node: DHTNode,
):
    return node.protocol.routing_table


def compute_spans(module_infos: List[RemoteModuleInfo], *, min_state: ServerState) -> Dict[PeerID, RemoteInfo]:
    spans = {}
    for index, info in enumerate(module_infos):
        if info.server.state.value < min_state.value:
            continue

    return spans
