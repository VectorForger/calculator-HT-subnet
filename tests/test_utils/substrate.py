import os
import re
from subprocess import PIPE, Popen

_DHT_START_PATTERN = re.compile(r"Running a DHT instance. To connect other peers to this one, use (.+)$")
_SUBSTRATE_START_PATTERN = re.compile(r"Frontier Node")

# python tests/test_utils/substrate.py

def start_substrate_node():
    binary_path = os.path.expanduser("~/polkadot-sdk-solochain-template/target/release/solochain-template-node")

    if not os.path.exists(binary_path):
        raise FileNotFoundError(f"Node binary not found at {binary_path}")

    substrate_node_proc = Popen(
        [binary_path, "--dev"],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        encoding="utf-8",
    )

    first_line = substrate_node_proc.stderr.readline()
    substrate_pattern_match = _SUBSTRATE_START_PATTERN.search(first_line)
    assert substrate_pattern_match is not None, first_line

    substrate_node_proc.stderr.close()

    substrate_node_proc.terminate()

    substrate_node_proc.wait()

if __name__ == "__main__":
  start_substrate_node()
