"""Event id generation.

Ids are zero-padded 6-digit strings ("000001", "000002", ...). They are
sequential within a single project, allocated by reading the workspace's
metadata counter and persisting the increment atomically. This makes them
human-readable, lexicographically sortable, and easy to type in a CLI
("nwt show 42").
"""

from __future__ import annotations

import threading
from pathlib import Path

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


def next_id(counter_file: Path) -> str:
    """Atomically allocate the next event id and persist the new counter.

    Writes a small JSON document to ``counter_file`` containing
    ``{"next": <n>}``. Uses a lock so two concurrent writers in the same
    process don't collide; cross-process safety relies on the
    ``os.replace`` atomic rename used by the storage layer.
    """
    import json
    import os
    import tempfile

    with _counter_lock:
        if counter_file.exists():
            data = json.loads(counter_file.read_text(encoding="utf-8"))
            current = int(data.get("next", 1))
        else:
            current = 1

        new_id = format_id(current)
        new_counter = {"next": current + 1}

        # Write to a temp file in the same directory, then atomically replace.
        counter_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".counter-", suffix=".tmp", dir=counter_file.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(new_counter, f)
            os.replace(tmp_path, counter_file)
        except Exception:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
            raise

        return new_id
