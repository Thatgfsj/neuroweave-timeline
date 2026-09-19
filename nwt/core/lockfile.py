"""Cross-process exclusive file locks.

fcntl covers POSIX; msvcrt covers Windows. The lock lives on the file
itself (``exclusive_lock(path)``), so there is no separate lock state
to lose: whatever process holds the region locked, the others wait.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

try:  # POSIX
    import fcntl

    def _lock_exclusive(fh: IO) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

    def _unlock(fh: IO) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

except ImportError:  # Windows
    import msvcrt

    # msvcrt.locking(LK_LOCK) gives up after ~10 seconds and raises
    # OSError(36); keep retrying so waiting for the lock stays blocking
    # (matching flock semantics) instead of crashing the waiter.
    _LOCK_MAX_WAIT_ROUNDS = 600  # ~10 minutes, then fail loudly

    def _lock_exclusive(fh: IO) -> None:
        for _ in range(_LOCK_MAX_WAIT_ROUNDS):
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue
        from nwt.core.errors import NWTError

        raise NWTError(
            "timed out waiting for a workspace lock (~10 min); "
            "another NWT process may be stuck"
        )

    def _unlock(fh: IO) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def exclusive_lock(path: Path) -> Iterator[IO]:
    """Hold an exclusive cross-process lock on ``path`` and yield the handle.

    The file is created if missing. The yielded handle is opened
    ``"r+"`` — read and write the guarded state through it, then let the
    context exit (which unlocks and closes). On Windows the lock covers
    byte 0, so concurrent lockers queue; the same handle must do the
    I/O, because a second handle on Windows would be denied access to
    the locked region.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size == 0:
        # Seed so the region we lock exists on every platform.
        with open(path, "a", encoding="utf-8") as seed:
            seed.write("0\n")
    fh = open(path, "r+", encoding="utf-8")
    try:
        _lock_exclusive(fh)
        try:
            yield fh
        finally:
            _unlock(fh)
    finally:
        fh.close()
