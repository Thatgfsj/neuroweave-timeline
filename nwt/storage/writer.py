"""Write events and relations to a workspace.

Writers go through :mod:`nwt.storage.atomic` so the timeline is never
half-written, even if the process is killed mid-write. Secondary indices
are maintained by :mod:`nwt.storage.indices`; they are derived data and
can be deleted at any time without losing information.
"""

from __future__ import annotations

import json
from pathlib import Path

from nwt.core.errors import EventNotFoundError, ValidationError
from nwt.core.event import TimelineEvent
from nwt.core.ids import canonical
from nwt.core.relations import Relation
from nwt.storage.atomic import write_text_atomic
from nwt.storage.indices import IndexStore
from nwt.storage.layout import Workspace


# --- events ------------------------------------------------------------------


def write_event(
    ws: Workspace, event: TimelineEvent, *, check_parent: bool = True
) -> TimelineEvent:
    """Persist ``event`` to disk, updating indices.

    If ``event.id`` is empty, allocate the next id from the workspace
    counter. Returns the event with its id (and final timestamp) filled
    in. Raises :class:`EventNotFoundError` if a referenced parent does
    not exist. Pass ``check_parent=False`` in bulk-rewrite paths (like
    compact) that may legitimately write a child before its parent.
    """
    if not event.id:
        event.id = next_free_id(ws)
    else:
        # Validate id format (accepts padded or unpadded input).
        try:
            event.id = canonical(event.id)
        except ValueError as e:
            raise ValidationError(f"bad event id {event.id!r}: {e}") from e

    if event.parent is not None:
        # Accept short or non-padded parent ids; pad to canonical form so
        # the file lookup succeeds.
        try:
            canonical_parent = canonical(event.parent)
        except ValueError as e:
            raise ValidationError(f"bad parent id {event.parent!r}: {e}") from e
        if check_parent:
            if not ws.event_file(canonical_parent).is_file():
                raise EventNotFoundError(event.parent)
            if canonical_parent == event.id:
                from nwt.core.errors import RelationError

                raise RelationError("an event cannot be its own parent")
        event.parent = canonical_parent

    write_text_atomic(ws.event_file(event.id), event.to_json() + "\n")
    IndexStore(ws).update(event)
    return event


def next_free_id(ws: Workspace) -> str:
    """Allocate an id from the counter, skipping ids already on disk.

    This heals a counter that fell behind the timeline (manual restore,
    an interrupted compact): the atomic rename makes the counter itself
    crash-safe, but a stale *value* would otherwise hand out a duplicate
    id and silently overwrite an existing event.
    """
    from nwt.core.ids import next_id

    event_id = next_id(ws.counter_file)
    while ws.event_file(event_id).is_file():
        event_id = next_id(ws.counter_file)
    return event_id


def reset_counter(ws: Workspace, next_value: int) -> None:
    """Point the counter at ``next_value`` (used after compact renumbering).

    Admin-level operation: callers are expected to have exclusive access
    to the workspace while renumbering (see ``engine.compact_events``).
    """
    if next_value < 1:
        raise ValidationError(f"counter must be >= 1, got {next_value}")
    write_text_atomic(ws.counter_file, json.dumps({"next": next_value}))


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


def rebuild_indices(ws: Workspace) -> None:
    """Recompute the secondary indices from the canonical event files.

    Kept as a module-level convenience; the implementation lives in
    :class:`nwt.storage.indices.IndexStore`.
    """
    IndexStore(ws).rebuild()
