"""Write events and relations to a workspace.

Writers go through :mod:`nwt.storage.atomic` so the timeline is never
half-written, even if the process is killed mid-write. Writers also
maintain secondary indices under ``.nwt/indices/`` for fast search; the
indices are derived data and can be deleted at any time without losing
information.
"""

from __future__ import annotations

import json
from pathlib import Path

from nwt.core.errors import EventNotFoundError, ValidationError
from nwt.core.event import TimelineEvent
from nwt.core.ids import format_id
from nwt.core.relations import Relation
from nwt.storage.atomic import write_text_atomic
from nwt.storage.layout import Workspace


# --- events ------------------------------------------------------------------


def write_event(ws: Workspace, event: TimelineEvent) -> TimelineEvent:
    """Persist ``event`` to disk, updating indices.

    If ``event.id`` is empty, allocate the next id from the workspace
    counter. Returns the event with its id (and final timestamp) filled
    in. Raises :class:`EventNotFoundError` if a referenced parent does
    not exist.
    """
    from nwt.core.ids import ID_WIDTH, parse_id

    if not event.id:
        from nwt.core.ids import next_id

        event.id = next_id(ws.counter_file)
    else:
        # Validate id format.
        try:
            format_id(int(event.id))
        except (TypeError, ValueError) as e:
            raise ValidationError(f"bad event id {event.id!r}: {e}") from e

    if event.parent is not None:
        # Accept short or non-padded parent ids; pad to canonical form so
        # the file lookup succeeds.
        try:
            n = parse_id(event.parent)
        except ValueError as e:
            raise ValidationError(f"bad parent id {event.parent!r}: {e}") from e
        canonical_parent = str(n).zfill(ID_WIDTH)
        if not ws.event_file(canonical_parent).is_file():
            raise EventNotFoundError(event.parent)
        event.parent = canonical_parent

    write_text_atomic(ws.event_file(event.id), event.to_json() + "\n")
    _update_file_index(ws, event)
    _update_tag_index(ws, event)
    return event


# --- relations ---------------------------------------------------------------


def write_relation(ws: Workspace, source: str, target: str, relation: Relation) -> None:
    """Append a directed edge ``source --relation--> target``.

    Both endpoints must exist as events. Duplicate edges are silently
    ignored (idempotent).
    """
    if source == target:
        from nwt.core.errors import RelationError

        raise RelationError("cannot link an event to itself")
    for node in (source, target):
        if not ws.event_file(node).is_file():
            raise EventNotFoundError(node)

    path = ws.relation_file(source)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"source": source, "edges": []}

    for edge in data.get("edges", []):
        if edge.get("target") == target and Relation.parse(edge.get("relation")) == relation:
            return  # duplicate, nothing to do

    data.setdefault("edges", []).append(
        {"target": target, "relation": relation.value}
    )
    write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# --- secondary indices -------------------------------------------------------
#
# These are tiny JSON files used by the search/CLI for fast lookup. They are
# rebuildable from the canonical event files, so a corrupt index is never
# a data-loss event.

_INDICES_DIR = "indices"


def _indices_dir(ws: Workspace) -> Path:
    p = ws.nwt_dir / _INDICES_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _update_file_index(ws: Workspace, event: TimelineEvent) -> None:
    """Record ``path -> [event_ids...]`` for every file the event touches."""
    p = _indices_dir(ws) / "files.json"
    data: dict[str, list[str]] = {}
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
    # Remove this event from every list first, so renames are reflected.
    for path_key, ids in list(data.items()):
        if event.id in ids:
            ids.remove(event.id)
            if not ids:
                del data[path_key]
    for path_key in event.files:
        data.setdefault(path_key, []).append(event.id)
    write_text_atomic(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _update_tag_index(ws: Workspace, event: TimelineEvent) -> None:
    p = _indices_dir(ws) / "tags.json"
    data: dict[str, list[str]] = {}
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
    for tag, ids in list(data.items()):
        if event.id in ids:
            ids.remove(event.id)
            if not ids:
                del data[tag]
    for tag in event.tags:
        data.setdefault(tag, []).append(event.id)
    write_text_atomic(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def rebuild_indices(ws: Workspace) -> None:
    """Recompute the secondary indices from the canonical event files.

    Useful after manual edits or after upgrading NWT. Idempotent.
    """
    # Wipe the indices directory and rebuild.
    idx = ws.nwt_dir / _INDICES_DIR
    if idx.exists():
        for child in idx.glob("*.json"):
            child.unlink()
    idx.mkdir(parents=True, exist_ok=True)

    events = []
    for path in sorted(ws.timeline_dir.glob("*.json")):
        if path.name.startswith("."):
            continue
        events.append(TimelineEvent.from_json(path.read_text(encoding="utf-8")))

    files: dict[str, list[str]] = {}
    tags: dict[str, list[str]] = {}
    for ev in events:
        for f in ev.files:
            files.setdefault(f, []).append(ev.id)
        for t in ev.tags:
            tags.setdefault(t, []).append(ev.id)

    write_text_atomic(
        idx / "files.json", json.dumps(files, indent=2, ensure_ascii=False) + "\n"
    )
    write_text_atomic(
        idx / "tags.json", json.dumps(tags, indent=2, ensure_ascii=False) + "\n"
    )
