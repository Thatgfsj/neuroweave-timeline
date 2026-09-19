"""Event id generation.

Ids are zero-padded 6-digit strings ("000001", "000002", ...). They are
sequential within a single project, allocated by reading the workspace's
metadata counter and persisting the increment under a cross-process lock.
This makes them human-readable, lexicographically sortable, and easy to
type in a CLI ("nwt show 42").
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from nwt.core.lockfile import exclusive_lock

#: Width of zero-padded event ids. 6 digits supports up to 999 999 events
#: per project, which is enough for years of work and keeps files small.
ID_WIDTH = 6

_counter_lock = threading.Lock()


def format_id(n: int) -> str:
    """Format a positive integer as a zero-padded event id."""
    if n < 1:
        raise ValueError(f"event counter must be >= 1, got {n}")
    return str(n).zfill(ID_WIDTH)


def parse_id(value: str) -> int:
    """Parse an event id back into its integer counter value."""
    s = value.strip()
    if not s.isdigit():
        raise ValueError(f"invalid event id: {value!r}")
    return int(s)


def canonical(value: str) -> str:
    """Parse an id (padded or not) and return its zero-padded form."""
    return format_id(parse_id(value))


def _read_current(fh) -> int:
    """Read the counter value from an open, already-locked file handle.

    A garbage or out-of-range value heals to 1; the writer skips ids
    whose event files already exist, so the counter converges on the
    truth either way.
    """
    fh.seek(0)
    raw = fh.read()
    try:
        current = int(json.loads(raw).get("next", 1))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return 1
    return current if current >= 1 else 1


def next_id(counter_file: Path) -> str:
    """Atomically allocate the next event id and persist the new counter.

    The counter file is locked across processes for the whole
    read-increment-write cycle, so two concurrent ``nwt log`` processes
    cannot allocate the same id. Callers should still be prepared to
    skip an allocated id whose event file already exists (see
    ``storage.writer.write_event``) — that heals a counter that fell
    behind a hand-edited or restored timeline.
    """
    with _counter_lock:
        counter_file = Path(counter_file)  # accept str paths like the old API
        with exclusive_lock(counter_file) as fh:
            current = _read_current(fh)
            new_id = format_id(current)
            fh.seek(0)
            fh.write(json.dumps({"next": current + 1}))
            fh.truncate()
        return new_id
