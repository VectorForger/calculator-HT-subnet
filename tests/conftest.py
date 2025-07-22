import gc

import psutil
import pytest

from mesh.utils.crypto import Ed25519PrivateKey, RSAPrivateKey
from mesh.utils.logging import get_logger, use_mesh_log_handler
from mesh.utils.mpfuture import MPFuture

use_mesh_log_handler("in_root_logger")
logger = get_logger(__name__)

@pytest.fixture(autouse=True, scope="session")
def cleanup_children_rsa():
    yield

    with RSAPrivateKey._process_wide_key_lock:
        RSAPrivateKey._process_wide_key = None

    gc.collect()  # Call .__del__() for removed objects

    MPFuture.reset_backend()

    children = psutil.Process().children(recursive=True)
    if children:
        _gone, alive = psutil.wait_procs(children, timeout=1)
        logger.debug(f"Cleaning up {len(alive)} leftover child processes")
        for child in alive:
            child.terminate()
        _gone, alive = psutil.wait_procs(alive, timeout=1)
        for child in alive:
            child.kill()

@pytest.fixture(autouse=True, scope="session")
def cleanup_children_ed25519():
    yield

    with Ed25519PrivateKey._process_wide_key_lock:
        Ed25519PrivateKey._process_wide_key = None

    gc.collect()  # Call .__del__() for removed objects

    MPFuture.reset_backend()

    children = psutil.Process().children(recursive=True)
    if children:
        _gone, alive = psutil.wait_procs(children, timeout=1)
        logger.debug(f"Cleaning up {len(alive)} leftover child processes")
        for child in alive:
            child.terminate()
        _gone, alive = psutil.wait_procs(alive, timeout=1)
        for child in alive:
            child.kill()
