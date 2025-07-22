import os
import re
from subprocess import PIPE, Popen
from tempfile import TemporaryDirectory

import pytest

# pytest tests/test_start_server.py -rP


def cleanup_process(process, timeout=5):
    try:
        process.terminate()
        process.wait(timeout=timeout)  # Add timeout to wait
    except:  # noqa: E722
        process.kill()
        process.wait(timeout=timeout)

@pytest.mark.xfail(reason="Flaky test", strict=False)
def test_cli_run_server_identity_path():
    pattern = r"Running DHT node on \[(.+)\],"

    with TemporaryDirectory() as tempdir:
        id_path = os.path.join(tempdir, "id")

        cloned_env = os.environ.copy()
        # overriding the loglevel to prevent debug print statements
        cloned_env["MESH_LOGLEVEL"] = "INFO"

        common_server_args = ["--hidden_dim", "4", "--num_handlers", "1"]

        server_1_proc = Popen(
            ["mesh-server", "--num_experts", "1", "--identity_path", id_path] + common_server_args,
            stderr=PIPE,
            text=True,
            encoding="utf-8",
            env=cloned_env,
        )

        line = server_1_proc.stderr.readline()
        assert "Generating new identity" in line

        line = server_1_proc.stderr.readline()
        addrs_pattern_result = re.search(pattern, line)
        assert addrs_pattern_result is not None, line
        addrs_1 = set(addrs_pattern_result.group(1).split(", "))
        ids_1 = set(a.split("/")[-1] for a in addrs_1)

        assert len(ids_1) == 1

        server_2_proc = Popen(
            ["mesh-server", "--num_experts", "1", "--identity_path", id_path] + common_server_args,
            stderr=PIPE,
            text=True,
            encoding="utf-8",
            env=cloned_env,
        )

        line = server_2_proc.stderr.readline()
        addrs_pattern_result = re.search(pattern, line)
        assert addrs_pattern_result is not None, line
        addrs_2 = set(addrs_pattern_result.group(1).split(", "))
        ids_2 = set(a.split("/")[-1] for a in addrs_2)

        assert len(ids_2) == 1

        server_3_proc = Popen(
            ["mesh-server", "--num_experts", "1"] + common_server_args,
            stderr=PIPE,
            text=True,
            encoding="utf-8",
            env=cloned_env,
        )

        line = server_3_proc.stderr.readline()
        addrs_pattern_result = re.search(pattern, line)
        assert addrs_pattern_result is not None, line
        addrs_3 = set(addrs_pattern_result.group(1).split(", "))
        ids_3 = set(a.split("/")[-1] for a in addrs_3)

        assert len(ids_3) == 1

        assert ids_1 == ids_2
        assert ids_1 != ids_3
        assert ids_2 != ids_3

        assert addrs_1 != addrs_2
        assert addrs_1 != addrs_3
        assert addrs_2 != addrs_3

        for p in [server_1_proc, server_2_proc, server_3_proc]:
            cleanup_process(p)
