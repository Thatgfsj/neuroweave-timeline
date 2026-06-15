"""Read events and relations from a workspace."""

from __future__ import annotations

import json
from pathlib import Path

from nwt.core.event import TimelineEvent
from nwt.core.relations import Relation
from nwt.storage.layout import Workspace


def read_event(ws: Workspace, event_id: str) -> TimelineEvent:
    """Load a single event. Raises :class:`EventNotFoundError` if missing."""
    from nwt.core.errors import EventNotFoundError

    path = ws.event_file(event_id)
    if not path.is_file():
        raise EventNotFoundError(event_id)
    return TimelineEvent.from_json(path.read_text(encoding="utf-8"))


def read_all_events(ws: Workspace) -> list[TimelineEvent]:
    """Load every event in the timeline, ordered by id ascending.

    Iterating the timeline directory lexicographically gives the same
    order as numeric order because ids are zero-padded to a fixed width.
    """
    events: list[TimelineEvent] = []
    if not ws.timeline_dir.is_dir():
        return events
    for path in sorted(ws.timeline_dir.glob("*.json")):
        if path.name.startswith("."):
            continue
        events.append(TimelineEvent.from_json(path.read_text(encoding="utf-8")))
    return events


def read_relations(ws: Workspace, source_id: str) -> list[tuple[str, Relation]]:
    """Return ``[(target_id, relation), ...]`` for edges leaving ``source_id``."""
    path = ws.relation_file(source_id)
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, Relation]] = []
    for edge in raw.get("edges", []):
        try:
            out.append((str(edge["target"]), Relation.parse(edge["relation"])))
        except (KeyError, ValueError):
            # Skip malformed rows defensively — the file is hand-editable.
            continue
    return out


def read_all_relations(ws: Workspace) -> dict[str, list[tuple[str, Relation]]]:
    """Return ``{source_id: [(target, relation), ...], ...}``."""
    result: dict[str, list[tuple[str, Relation]]] = {}
    if not ws.relations_dir.is_dir():
        return result
    for path in sorted(ws.relations_dir.glob("*.json")):
        if path.name.startswith("."):
            continue
        source_id = path.stem
        result[source_id] = read_relations(ws, source_id)
    return result
