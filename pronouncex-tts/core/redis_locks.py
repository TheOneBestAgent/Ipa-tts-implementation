import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


def merge_lock(
    client: Any,
    job_id: str,
    timeout: int = 60,
    blocking_timeout: float = 1.0,
) -> Any:
    return client.lock(
        f"px:lock:merge:{job_id}",
        timeout=timeout,
        blocking_timeout=blocking_timeout,
    )


@contextmanager
def file_lock(path: Path, timeout: float = 1.0) -> Iterator[bool]:
    if fcntl is None:
        yield True
        return
    start = time.time()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - start >= timeout:
                    yield False
                    return
                time.sleep(0.05)
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
