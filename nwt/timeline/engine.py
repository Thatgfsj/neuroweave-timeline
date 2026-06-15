"""High-level timeline engine.

The engine wraps the storage layer behind the verbs the spec asks for:
``create_event``, ``get_event``, ``list_events``, ``link``, ``search``.
Both the CLI and the MCP server talk to this module — they should never
read or write ``.nwt/`` files directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from nwt.core.errors import ValidationError
from nwt.core.event import TimelineEvent
from nwt.core.ids import parse_id
from nwt.core.relations import Relation
from nwt.storage.layout import Workspace, open_workspace
from nwt.storage.reader import read_all_events, read_all_relations, read_event, read_relations
from nwt.storage.writer import write_event, write_relation


def _resolve_workspace(root: str | Path | None = None) -> Workspace:
    """Open the workspace rooted at ``root`` (default: cwd)."""
    if root is None:
        root = Path.cwd()
    return open_workspace(Path(root))


# --- public API --------------------------------------------------------------


def create_event(
    *,
    task: str,
    summary: str,
    reason: str | None = None,
    files: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    parent: str | None = None,
    timestamp: str | None = None,
    meta: dict | None = None,
    root: str | Path | None = None,
) -> TimelineEvent:
    """Append a new event to the project's timeline.

    Returns the persisted event, complete with allocated id and timestamp.
    Use ``parent=<id>`` to continue an existing chain; omit it to start a
    new branch.
    """
    if not task or not task.strip():
        raise ValidationError("'task' is required and must be non-empty")
    if not summary or not summary.strip():
        raise ValidationError("'summary' is required and must be non-empty")

    ws = _resolve_workspace(root)
    ev = TimelineEvent.create(
        task=task.strip(),
        summary=summary.strip(),
        reason=reason.strip() if reason else None,
        files=files,
        tags=tags,
        parent=parent,
        timestamp=timestamp,
        meta=meta,
    )
    return write_event(ws, ev)


def get_event(event_id: str, *, root: str | Path | None = None) -> TimelineEvent:
    """Fetch a single event by id (with or without zero padding)."""
    ws = _resolve_workspace(root)
    canonical = _canonical_id(ws, event_id)
    return read_event(ws, canonical)


def list_events(
    *,
    root: str | Path | None = None,
    limit: int | None = None,
    offset: int = 0,
    reverse: bool = False,
) -> list[TimelineEvent]:
    """Return all events in id order (``reverse=True`` for newest first)."""
    ws = _resolve_workspace(root)
    events = read_all_events(ws)
    events.sort(key=lambda e: e.id, reverse=reverse)
    if offset:
        events = events[offset:]
    if limit is not None:
        events = events[:limit]
    return events


def search(
    query: str,
    *,
    root: str | Path | None = None,
    limit: int | None = None,
) -> list[TimelineEvent]:
    """Substring search across task, summary, reason, files, and tags.

    Case-insensitive. Returns events ordered by id ascending. Empty
    query returns nothing.
    """
    if not query or not query.strip():
        return []
    ws = _resolve_workspace(root)
    q = query.strip().lower()
    out: list[TimelineEvent] = []
    for ev in read_all_events(ws):
        if _matches(ev, q):
            out.append(ev)
        if limit is not None and len(out) >= limit:
            break
    return out


def search_by_file(path: str, *, root: str | Path | None = None) -> list[TimelineEvent]:
    """Return every event that touched the given file path.

    Uses the ``files`` index when available, falling back to a full scan.
    """
    ws = _resolve_workspace(root)
    idx = ws.nwt_dir / "indices" / "files.json"
    if idx.is_file():
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        ids = data.get(path) or []
        if ids:
            out: list[TimelineEvent] = []
            for eid in ids:
                try:
                    out.append(read_event(ws, eid))
                except Exception:
                    continue
            return out
    # Fallback: scan.
    return [ev for ev in read_all_events(ws) if path in ev.files]


def search_by_tag(tag: str, *, root: str | Path | None = None) -> list[TimelineEvent]:
    """Return every event carrying ``tag`` (case-insensitive)."""
    ws = _resolve_workspace(root)
    idx = ws.nwt_dir / "indices" / "tags.json"
    needle = tag.strip().lower()
    if idx.is_file():
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        ids = data.get(needle) or []
        if ids:
            out: list[TimelineEvent] = []
            for eid in ids:
                try:
                    out.append(read_event(ws, eid))
                except Exception:
                    continue
            return out
    return [ev for ev in read_all_events(ws) if needle in ev.tags]


def link(
    source: str,
    target: str,
    relation: str | Relation,
    *,
    root: str | Path | None = None,
) -> None:
    """Create a typed edge from ``source`` to ``target``.

    Accepts the relation as a string (case-insensitive) or a
    :class:`Relation` enum value. See :class:`nwt.core.relations.Relation`
    for the supported set.
    """
    ws = _resolve_workspace(root)
    src = _canonical_id(ws, source)
    tgt = _canonical_id(ws, target)
    write_relation(ws, src, tgt, Relation.parse(relation))


def iter_relations(root: str | Path | None = None) -> dict[str, list[tuple[str, Relation]]]:
    """Return ``{source: [(target, relation), ...]}`` for the whole project."""
    ws = _resolve_workspace(root)
    return read_all_relations(ws)


# --- helpers -----------------------------------------------------------------


def _canonical_id(ws: Workspace, value: str) -> str:
    """Accept ids with or without leading zeros."""
    try:
        n = parse_id(value)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    if not ws.event_file(_zfill(n)).is_file():
        from nwt.core.errors import EventNotFoundError

        raise EventNotFoundError(_zfill(n))
    return _zfill(n)


def _zfill(n: int) -> str:
    from nwt.core.ids import ID_WIDTH

    return str(n).zfill(ID_WIDTH)


def _matches(ev: TimelineEvent, q: str) -> bool:
    haystacks = [
        ev.task.lower(),
        ev.summary.lower(),
        (ev.reason or "").lower(),
        " ".join(ev.files).lower(),
        " ".join(ev.tags).lower(),
    ]
    return any(q in h for h in haystacks)
