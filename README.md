# calculator-HT-subnet

A simple distributed calculator built on Hypertensor infrastructure. Nodes can perform mathematical calculations for each other over a P2P network.

## Setup

```bash
cd mesh
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Fix protobuf compatibility
pip install "protobuf==3.20.3"
cd mesh/proto
protoc --python_out=. --proto_path=. *.proto
./fix_import.sh
cd ../..
```

## Running

Start two nodes in separate terminals:

**Terminal 1 (Bootstrap node):**
```bash
mesh-server-mock --host_maddrs /ip4/0.0.0.0/tcp/31330 /ip4/0.0.0.0/udp/31330/quic --announce_maddrs /ip4/127.0.0.1/tcp/31330 /ip4/127.0.0.1/udp/31330/quic --new_swarm --identity_path server2.id --subnet_id 1 --subnet_node_id 1
```

**Terminal 2 (Peer node):**
```bash
mesh-server-mock --public_ip 127.0.0.1 --port 31331 --identity_path server3.id --subnet_id 1 --subnet_node_id 2 --initial_peers /ip4/127.0.0.1/tcp/31330/p2p/PEER_ID_FROM_TERMINAL_1
```

Replace `PEER_ID_FROM_TERMINAL_1` with the actual peer ID shown in terminal 1 output.

## Testing

```bash
python test_live_network.py
```

This will connect to the network and test basic arithmetic operations like "4 * 3", "15 + 27", etc.

## What It Does

- Nodes discover each other via DHT
- Clients can send math expressions to any node
- Nodes calculate results and return them
- Uses custom protobuf messages (no AI tensor complexity)
- Runs on official Hypertensor infrastructure

## Supported Operations

Basic arithmetic: `+`, `-`, `*`, `/`, `()` 

Examples: `4 * 3`, `(5 + 3) * 2`, `100 / 4`