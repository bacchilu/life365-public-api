import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def acquire_job_lock(lock_path: Path) -> Generator[bool]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
