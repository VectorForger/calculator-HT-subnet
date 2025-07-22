import json
import os
from pathlib import Path

import torch
from dotenv import load_dotenv

load_dotenv(os.path.join(Path.cwd(), '.env'))

"""
Default bootstrap nodes

# How to use:
    Add PUBLIC_INITIAL_PEERS in the .env file as:

    PUBLIC_INITIAL_PEERS = ['/ip4/{IP}/tcp/{PORT}/p2p/{PeerID}']
"""
raw_peers = os.getenv('PUBLIC_INITIAL_PEERS')
if raw_peers is None:
    raise ValueError("PUBLIC_INITIAL_PEERS not set in .env")

# If the string is quoted (single or double), strip those quotes
if (raw_peers.startswith('"') and raw_peers.endswith('"')) or \
   (raw_peers.startswith("'") and raw_peers.endswith("'")):
    raw_peers = raw_peers[1:-1]

try:
    PUBLIC_INITIAL_PEERS = json.loads(raw_peers)
except json.JSONDecodeError as e:
    raise ValueError(f"Failed to parse PUBLIC_INITIAL_PEERS as JSON: {e}")

# The reachability API is currently used only when connecting to the public swarm
REACHABILITY_API_URL = "https://health.subnet-name.com"

DTYPE_MAP = dict(bfloat16=torch.bfloat16, float16=torch.float16, float32=torch.float32, auto="auto")

"""
Commit-reveal schema phases

Each commit must be by the x% of the epoch with reveals after up until the end
using the previous epochs random tensor from the DHT storage
"""
HOSTER_COMMIT_PHASE = 0.8

"""
The validator commits based on the previous epochs hosters commit-reveals
"""
VALIDATOR_COMMIT_PHASE = 0.5
