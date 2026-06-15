"""The TimelineEvent data model.

Events are the atoms of NWT. Each one records a single meaningful action in
the project — a decision, a refactor, a file creation, a bug fix — together
with the *reason* it happened. Together they form the evolution graph.

Serialization format is JSON, with field order chosen for human readability
when files are inspected directly on disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from nwt.core.errors import ValidationError
from nwt.core.ids import format_id, parse_id

# Required fields on every event. ``parent`` is optional (null for the first
# event in a chain). Everything else has a sensible default.
_REQUIRED_FIELDS = ("id", "timestamp", "task", "summary")


@dataclass
class TimelineEvent:
    """A single node in the project timeline.

    Attributes:
        id: Zero-padded 6-digit string, allocated by the engine.
        timestamp: ISO 8601 string in UTC (``2026-06-15T10:00:00Z`` style;
            ``Z`` suffix or ``+00:00`` are both accepted on read).
        task: Short imperative title ("Add activation engine").
        summary: One or two sentences describing what was done.
        reason: Why it was done. Optional but strongly encouraged — this is
            the field that turns NWT from a log into a *history*.
        files: Project-relative file paths this event touched.
        tags: Free-form labels (e.g. ``"memory"``, ``"refactor"``,
            ``"milestone"``). Tags are lowercased on normalize.
        parent: Id of the preceding event in the linear chain, or None.
        meta: Escape hatch for forward-compatible fields. The engine never
            inspects this; CLI/MCP output exposes it verbatim.
    """

    task: str
    summary: str
    id: str = ""
    timestamp: str = ""
    reason: str | None = None
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    parent: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # ----- construction helpers ------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        task: str,
        summary: str,
        reason: str | None = None,
        files: Iterable[str] | None = None,
        tags: Iterable[str] | None = None,
        parent: str | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> "TimelineEvent":
        """Build a new event with a freshly-allocated id and timestamp.

        Use this in code paths that talk to a real workspace (the engine
        calls this internally). For tests, use :meth:`from_dict` so the id
        stays deterministic.
        """
        return cls(
            id=event_id or "",
            timestamp=timestamp or _utc_now_iso(),
            task=task,
            summary=summary,
            reason=reason,
            files=list(files or []),
            tags=_normalize_tags(tags or []),
            parent=parent,
            meta=dict(meta or {}),
        )

    # ----- (de)serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict with stable field order."""
        d: dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "task": self.task,
            "summary": self.summary,
        }
        if self.reason is not None:
            d["reason"] = self.reason
        if self.files:
            d["files"] = list(self.files)
        if self.tags:
            d["tags"] = list(self.tags)
        if self.parent is not None:
            d["parent"] = self.parent
        if self.meta:
            d["meta"] = dict(self.meta)
        return d

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineEvent":
        """Construct an event from a parsed JSON object.

        Performs strict validation — unknown fields raise, missing required
        fields raise, wrong types raise. Use :meth:`from_json` to get the
        same behaviour from a string.
        """
        if not isinstance(data, dict):
            raise ValidationError(f"event must be a JSON object, got {type(data).__name__}")

        unknown = set(data) - set(_REQUIRED_FIELDS) - {
            "reason", "files", "tags", "parent", "meta",
        }
        if unknown:
            raise ValidationError(
                f"event has unknown field(s): {sorted(unknown)}"
            )

        for name in _REQUIRED_FIELDS:
            if name not in data:
                raise ValidationError(f"event missing required field: {name!r}")
            if not isinstance(data[name], str) or not data[name].strip():
                raise ValidationError(f"event field {name!r} must be a non-empty string")

        try:
            parse_id(data["id"])
        except ValueError as e:
            raise ValidationError(str(e)) from e

        try:
            _parse_iso(data["timestamp"])
        except ValueError as e:
            raise ValidationError(f"invalid timestamp {data['timestamp']!r}: {e}") from e

        reason = data.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValidationError("'reason' must be a string when present")

        files = data.get("files", [])
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            raise ValidationError("'files' must be a list of strings")

        tags = data.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ValidationError("'tags' must be a list of strings")

        parent = data.get("parent")
        if parent is not None:
            if not isinstance(parent, str):
                raise ValidationError("'parent' must be a string when present")
            try:
                parse_id(parent)
            except ValueError as e:
                raise ValidationError(f"invalid parent id {parent!r}: {e}") from e

        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            raise ValidationError("'meta' must be an object when present")

        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            task=data["task"],
            summary=data["summary"],
            reason=reason,
            files=list(files),
            tags=_normalize_tags(tags),
            parent=parent,
            meta=dict(meta),
        )

    @classmethod
    def from_json(cls, text: str) -> "TimelineEvent":
        return cls.from_dict(json.loads(text))

    # ----- presentation --------------------------------------------------------

    def short_id(self) -> str:
        """Return the id stripped of leading zeros — useful for terse CLI output."""
        return str(int(self.id)) if self.id else self.id

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        parent = f" ← {self.parent}" if self.parent else ""
        files = f"  files={self.files}" if self.files else ""
        return f"[{self.short_id()}] {self.task}{parent}{files}"


# ----- helpers ----------------------------------------------------------------


def _utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, accepting a trailing ``Z``."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    """Lowercase, strip, dedupe while preserving order."""
    seen: dict[str, None] = {}
    for t in tags:
        if not isinstance(t, str):
            raise ValidationError(f"tag must be a string, got {type(t).__name__}")
        norm = t.strip().lower()
        if norm and norm not in seen:
            seen[norm] = None
    return list(seen)
