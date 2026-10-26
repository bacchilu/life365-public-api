"""Local-only settings. Never load or use the application's DATABASE_URL."""

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = "local-postgres"
IMAGE = "postgres:18.6"
SANDBOX = "life365_sandbox"
TEST_DATABASE = "life365_public_api_test_customer_sync"


class LocalDatabaseError(Exception):
    """A local configuration or lifecycle failure without secret values."""


@contextmanager
def operation_lock() -> Iterator[None]:
    directory = ROOT / ".sandbox-db"
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise LocalDatabaseError(
            "Local database lock directory must belong to the current user"
        )
    directory.chmod(0o700)
    descriptor = os.open(
        directory / "operation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocalDatabaseError(
                "Another local database operation is running"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
