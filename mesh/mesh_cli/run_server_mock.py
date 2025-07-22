import argparse
import logging

import configargparse
import torch

from mesh.subnet.constants import DTYPE_MAP, PUBLIC_INITIAL_PEERS
from mesh.subnet.data_structures import QuantType, ServerClass
from mesh.subnet.server.server import Server
from mesh.substrate.mock.chain_functions import MockHypertensor
from mesh.utils import limits
from mesh.utils.logging import get_logger, use_mesh_log_handler

use_mesh_log_handler("in_root_logger")

logger = get_logger(__name__)

"""
A mock CLI

Add required parameters to start a node

For example, if you're building an inference subnet, you may need a model name to load the model.
"""
def main():
    # fmt:off
    parser = configargparse.ArgParser(default_config_files=["config.yml"],
                                      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add('-c', '--config', required=False, is_config_file=True, help='config file path')
    parser.add_argument("--public_name", type=str, default=None, help="Public name to be reported in the leaderboard")

    group = parser.add_mutually_exclusive_group(required=False)
    parser.add_argument('--port', type=int, required=False,
                        help='Port this server listens to. '
                             'This is a simplified way to set the --host_maddrs and --announce_maddrs options (see below) '
                             'that sets the port across all interfaces (IPv4, IPv6) and protocols (TCP, etc.) '
                             'to the same number. Default: a random free port is chosen for each interface and protocol')
    parser.add_argument('--public_ip', type=str, required=False,
                        help='Your public IPv4 address, which is visible from the Internet. '
                             'This is a simplified way to set the --announce_maddrs option (see below).'
                             'Default: server announces IPv4/IPv6 addresses of your network interfaces')

    parser.add_argument("--no_auto_relay", action="store_false", dest="use_auto_relay",
                        help="Do not look for libp2p relays to become reachable if we are behind NAT/firewall")

    parser.add_argument('--host_maddrs', nargs='+', required=False,
                        help='Multiaddrs to listen for external connections from other peers')
    parser.add_argument('--announce_maddrs', nargs='+', required=False,
                        help='Visible multiaddrs the host announces for external connections from other peers')
    parser.add_argument('--daemon_startup_timeout', type=float, default=60,
                        help='Timeout for the libp2p daemon connecting to initial peers')
    parser.add_argument('--update_period', type=float, required=False, default=120,
                        help='Server will report blocks to DHT once in this many seconds')
    parser.add_argument('--expiration', type=float, required=False, default=None,
                        help='DHT entries will expire after this many seconds')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--initial_peers', type=str, nargs='+', required=False, default=PUBLIC_INITIAL_PEERS,
                       help='Multiaddrs of one or more DHT peers from the target swarm. Default: connects to the public swarm')
    group.add_argument('--new_swarm', action='store_true',
                       help='Start a new private swarm (i.e., do not connect to any initial peers)')
    parser.add_argument('--increase_file_limit', type=int, default=4096,
                        help='On *nix, increase the max number of files a server can open '
                             'before hitting "Too many open files" (set to zero to keep the system limit)')
    parser.add_argument('--identity_path', type=str, required=False, help='Path to identity file to be used in P2P')
    parser.add_argument('--subnet_id', type=int, required=False, default=None, help='Subnet ID running a node for ')
    parser.add_argument('--subnet_node_id', type=int, required=False, default=None, help='Subnet ID running a node for ')

    # fmt:on
    args = vars(parser.parse_args())
    args.pop("config", None)

    subnet_id = args.pop("subnet_id", False)
    subnet_node_id = args.pop("subnet_node_id", False)
    role = ServerClass.VALIDATOR

    host_maddrs = args.pop("host_maddrs")
    port = args.pop("port")
    if port is not None:
        assert host_maddrs is None, "You can't use --port and --host_maddrs at the same time"
    else:
        port = 0
    if host_maddrs is None:
        host_maddrs = [f"/ip4/0.0.0.0/tcp/{port}", f"/ip6/::/tcp/{port}"]

    announce_maddrs = args.pop("announce_maddrs")
    public_ip = args.pop("public_ip")
    if public_ip is not None:
        assert announce_maddrs is None, "You can't use --public_ip and --announce_maddrs at the same time"
        assert port != 0, "Please specify a fixed non-zero --port when you use --public_ip (e.g., --port 31337)"
        announce_maddrs = [f"/ip4/{public_ip}/tcp/{port}"]

    args["startup_timeout"] = args.pop("daemon_startup_timeout")

    file_limit = args.pop("increase_file_limit")
    if file_limit:
        limits.logger.setLevel(logging.WARNING)
        limits.increase_file_limit(file_limit, file_limit)

    if args.pop("new_swarm"):
        args["initial_peers"] = []

    if not torch.backends.openmp.is_available():
        # Necessary to prevent the server from freezing after forks
        torch.set_num_threads(1)

    hypertensor = MockHypertensor()

    server = Server(
        **args,
        host_maddrs=host_maddrs,
        announce_maddrs=announce_maddrs,
        role=role,
        subnet_id=subnet_id,
        subnet_node_id=subnet_node_id,
        hypertensor=hypertensor
    )

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Caught KeyboardInterrupt, shutting down")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
