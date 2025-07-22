import asyncio
import functools
import re

import requests
from async_timeout import timeout

import mesh
from mesh.subnet.protocols.mock_protocol import MockProtocol

info_cache = mesh.TimedStorage()


async def check_reachability(peer_id, _, node, *, fetch_info=False, connect_timeout=5, expiration=300, use_cache=True):
    if use_cache:
        entry = info_cache.get(peer_id)
        if entry is not None:
            return entry.value

    try:
        async with timeout(connect_timeout):
            if fetch_info:
                # For Peer
                stub = MockProtocol.get_server_stub(node.p2p, peer_id)
                response = await stub.rpc_info(mesh.proto.runtime_pb2.Empty())
                rpc_info = mesh.MSGPackSerializer.loads(response.serialized_info)
                rpc_info["ok"] = True
            else:
                # For Bootstrap
                await node.p2p._client.connect(peer_id, [])
                await node.p2p._client.disconnect(peer_id)
                rpc_info = {"ok": True}
    except Exception as e:
        if not isinstance(e, asyncio.TimeoutError):
            message = str(e) if str(e) else repr(e)
            if message == "protocol not supported":
                return {"ok": True}
        else:
            message = f"Failed to connect in {connect_timeout:.0f} sec. Firewall may be blocking connections"
        rpc_info = {"ok": False, "error": message}

    info_cache.store(peer_id, rpc_info, mesh.get_dht_time() + expiration)
    return rpc_info


async def check_reachability_parallel(peer_ids, dht, node, *, fetch_info=False):
    rpc_infos = await asyncio.gather(
        *[check_reachability(peer_id, dht, node, fetch_info=fetch_info) for peer_id in peer_ids]
    )
    return dict(zip(peer_ids, rpc_infos))

async def get_peers_ips(dht, dht_node):
    return await dht_node.p2p.list_peers()

@functools.cache
def get_location(ip_address):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_address}")
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {}

def extract_peer_ip_info(multiaddr_str):
    if ip_match := re.search(r"/ip4/(\d+\.\d+\.\d+\.\d+)", multiaddr_str):
        return get_location(ip_match[1])
    return {}
