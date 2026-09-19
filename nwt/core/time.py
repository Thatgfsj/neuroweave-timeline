"""Time helpers shared across NWT.

One place for ISO-8601 handling so a parsing fix lands everywhere at
once (this used to live, copy-pasted, in ``core.event``, ``timeline.engine``
and ``timeline.summary``).
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, accepting a trailing ``Z``."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def short_date(iso: str) -> str:
    """Return ``YYYY-MM-DD`` for an ISO timestamp (best effort)."""
    if not iso:
        return ""
    try:
        return parse_iso(iso).strftime("%Y-%m-%d")
    except ValueError:
        return iso.strip()[:10]
