"""High-level timeline engine.

The engine wraps the storage layer behind the verbs the spec asks for:
``create_event``, ``get_event``, ``list_events``, ``link``, ``search``.
Both the CLI and the MCP server talk to this module — they should never
read or write ``.nwt/`` files directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from nwt.core.errors import EventNotFoundError, ValidationError
from nwt.core.event import TimelineEvent, normalize_file
from nwt.core.ids import ID_WIDTH, canonical
from nwt.core.relations import Relation
from nwt.core.time import parse_iso
from nwt.storage.indices import IndexStore
from nwt.storage.layout import Workspace, open_workspace
from nwt.storage.reader import read_all_events, read_all_relations, read_event
from nwt.storage.writer import next_free_id, reset_counter, write_event, write_relation

#: Sentinel: append after the latest event (the default).
PARENT_AUTO = "auto"

#: Sentinel: explicitly start a new branch (no parent).
PARENT_NONE = "none"

_COMPACT_BACKUP_PREFIX = "pre-compact-"


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
    parent: str | None = PARENT_AUTO,
    importance: str = "normal",
    timestamp: str | None = None,
    meta: dict | None = None,
    root: str | Path | None = None,
) -> TimelineEvent:
    """Append a new event to the project's timeline.

    Returns the persisted event, complete with allocated id and timestamp.

    ``parent`` controls chain placement:

    * ``"auto"`` or ``None`` (default) — append after the latest event,
      so a plain sequence of ``nwt log`` calls forms one linear history.
    * ``"none"`` — start a new branch (no parent).
    * an event id — continue after that specific event.
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
        parent=_resolve_parent(ws, parent),
        importance=importance,
        timestamp=timestamp,
        meta=meta,
    )
    return write_event(ws, ev)


def _resolve_parent(ws: Workspace, parent: str | None) -> str | None:
    """Interpret the ``parent`` argument (see :func:`create_event`)."""
    if parent is None:
        spec = PARENT_AUTO
    else:
        spec = parent.strip()
        if spec.lower() == PARENT_AUTO:
            spec = PARENT_AUTO
        elif spec.lower() == PARENT_NONE:
            return None

    if spec == PARENT_AUTO:
        events = read_all_events(ws)
        if not events:
            return None
        return max(events, key=lambda e: int(e.id)).id

    try:
        resolved = canonical(spec)
    except ValueError as e:
        raise ValidationError(f"invalid parent id {parent!r}: {e}") from e
    if not ws.event_file(resolved).is_file():
        raise EventNotFoundError(resolved)
    return resolved


def get_event(event_id: str, *, root: str | Path | None = None) -> TimelineEvent:
    """Fetch a single event by id (with or without zero padding)."""
    ws = _resolve_workspace(root)
    return read_event(ws, _canonical_id(ws, event_id))


def list_events(
    *,
    root: str | Path | None = None,
    limit: int | None = None,
    offset: int = 0,
    reverse: bool = False,
) -> list[TimelineEvent]:
    """Return all events in id order (``reverse=True`` for newest first)."""
    if limit is not None and limit < 0:
        raise ValidationError("limit must be >= 0")
    if offset < 0:
        raise ValidationError("offset must be >= 0")
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
    if limit is not None and limit < 0:
        raise ValidationError("limit must be >= 0")
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

    The query is normalized the same way the stored paths are
    (:func:`nwt.core.event.normalize_file`), so ``src\\foo.py`` and
    ``./src/foo.py`` find the event that logged ``src/foo.py``. Uses the
    ``files`` index when available, falling back to a full scan.
    """
    ws = _resolve_workspace(root)
    key = normalize_file(path)
    ids = IndexStore(ws).by_file(key)
    if not ids and key != path:
        ids = IndexStore(ws).by_file(path)  # pre-normalization data
    if ids:
        out: list[TimelineEvent] = []
        for eid in ids:
            try:
                out.append(read_event(ws, eid))
            except Exception:
                continue
        return out
    # Fallback: scan (compare normalized forms).
    return [
        ev for ev in read_all_events(ws)
        if any(normalize_file(f) == key for f in ev.files)
    ]


def search_by_tag(tag: str, *, root: str | Path | None = None) -> list[TimelineEvent]:
    """Return every event carrying ``tag`` (case-insensitive)."""
    ws = _resolve_workspace(root)
    ids = IndexStore(ws).by_tag(tag.strip().lower())
    if ids:
        out: list[TimelineEvent] = []
        for eid in ids:
            try:
                out.append(read_event(ws, eid))
            except Exception:
                continue
        return out
    return [ev for ev in read_all_events(ws) if tag.strip().lower() in ev.tags]


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


def diff_events(
    from_id: str,
    to_id: str,
    *,
    root: str | Path | None = None,
) -> dict:
    """Compare two events and return the changes between them.

    ``from_id`` must precede ``to_id`` in the timeline; anything else
    raises :class:`ValidationError` instead of silently returning an
    empty range.

    Returns a dict with:
      - events: list of events between from and to (inclusive)
      - files_added: files present in to but not in from
      - files_removed: files present in from but not in to
      - files_in_both: files touched by both endpoint events (i.e.
        likely modified somewhere in between)
    """
    ws = _resolve_workspace(root)
    from_event = read_event(ws, _canonical_id(ws, from_id))
    to_event = read_event(ws, _canonical_id(ws, to_id))

    if from_event.id == to_event.id:
        raise ValidationError("cannot diff an event with itself")

    all_events = read_all_events(ws)
    all_events.sort(key=lambda e: e.id)

    ids = [e.id for e in all_events]
    from_idx = ids.index(from_event.id)
    to_idx = ids.index(to_event.id)
    if from_idx > to_idx:
        raise ValidationError(
            f"event {from_event.short_id()} comes after {to_event.short_id()}; "
            "pass the earlier event id first"
        )

    between = all_events[from_idx:to_idx + 1]

    from_files = set(from_event.files)
    to_files = set(to_event.files)

    return {
        "events": between,
        "files_added": sorted(to_files - from_files),
        "files_removed": sorted(from_files - to_files),
        "files_in_both": sorted(from_files & to_files),
    }


def compact_events(
    *,
    root: str | Path | None = None,
    time_window_seconds: int = 3600,
    min_group_size: int = 3,
    dry_run: bool = False,
) -> dict:
    """Merge consecutive events with the same tags that are close in time.

    Groups events where:
    - Same tags
    - Within time_window_seconds (default 1 hour)

    If a group has min_group_size or more events, they are merged into
    one. This is a destructive rewrite of the canonical store, so the
    implementation:

    1. backs up ``timeline/``, ``relations/`` and the counter to
       ``.nwt/snapshots/pre-compact-<ts>/``,
    2. renumbers the surviving events from 1,
    3. remaps ``parent`` fields and typed relations onto the new ids
       (a merged group's members all remap to the merged event),
    4. rebuilds indices and resets the counter.

    Pass ``dry_run=True`` to compute the result without touching disk.
    Returns a dict with original_count, compacted_count, merged,
    dry_run, and backup (path of the safety copy, or None).
    """
    if min_group_size < 2:
        raise ValidationError("min_group_size must be >= 2 (a group of 1 cannot merge)")
    if time_window_seconds < 0:
        raise ValidationError("time_window_seconds must be >= 0")

    ws = _resolve_workspace(root)
    events = read_all_events(ws)
    # Read relations before any destructive step: a corrupt relations
    # file must not leave the rewrite half-applied (the tolerant reader
    # skips malformed files with a warning; the backup preserves them).
    old_relations = read_all_relations(ws)
    events.sort(key=lambda e: e.id)

    no_change = {
        "original_count": len(events),
        "compacted_count": len(events),
        "merged": 0,
        "dry_run": dry_run,
        "backup": None,
    }
    if len(events) < min_group_size:
        return no_change

    # Group consecutive events with same tags, close in time.
    groups: list[list[TimelineEvent]] = [[events[0]]]
    for i in range(1, len(events)):
        prev = events[i - 1]
        curr = events[i]
        same_tags = sorted(curr.tags) == sorted(prev.tags)
        try:
            time_diff = (parse_iso(curr.timestamp) - parse_iso(prev.timestamp)).total_seconds()
        except (ValueError, TypeError):
            time_diff = float("inf")
        if same_tags and time_diff < time_window_seconds:
            groups[-1].append(curr)
        else:
            groups.append([curr])

    if not any(len(g) >= min_group_size for g in groups):
        return no_change

    # Build the surviving event list under fresh ids (1..N) plus an
    # old-id → new-id mapping. Every old id maps to some new id (merged
    # members map to the group's merged representative), so parents and
    # relations stay connected.
    new_events: list[TimelineEvent] = []
    sources: list[list[str]] = []  # old ids each new event stands for
    counter = 0
    for group in groups:
        if len(group) >= min_group_size:
            first, last = group[0], group[-1]
            counter += 1
            meta = dict(first.meta)
            meta["compacted"] = [e.id for e in group]
            new_events.append(TimelineEvent.create(
                task=f"{first.task} ... {last.task}",
                summary=f"Compacted {len(group)} events: {', '.join(e.task for e in group)}",
                reason=first.reason,
                files=list(dict.fromkeys(f for e in group for f in e.files)),
                tags=first.tags,
                importance=first.importance,
                parent=first.parent,
                event_id=format_compact_id(counter),
                timestamp=first.timestamp,
                meta=meta,
            ))
            sources.append([e.id for e in group])
        else:
            for ev in group:
                counter += 1
                sources.append([ev.id])
                ev.id = format_compact_id(counter)
                new_events.append(ev)

    id_map: dict[str, str] = {}
    for ev, old_ids in zip(new_events, sources):
        for old_id in old_ids:
            id_map[old_id] = ev.id

    # Remap parents onto the new id space; drop self-references and
    # dangling ids left over from hand-edited timelines.
    for ev in new_events:
        if ev.parent is not None:
            ev.parent = id_map.get(ev.parent)
            if ev.parent == ev.id:
                ev.parent = None

    merged = len(events) - len(new_events)
    if dry_run:
        return {
            "original_count": len(events),
            "compacted_count": len(new_events),
            "merged": merged,
            "dry_run": True,
            "backup": None,
        }

    # 1. Safety backup of everything the rewrite touches. The name
    # carries a uniquifier: two compacts within the same second (two
    # processes, or a retry) must not race on one backup directory.
    backup_dir = ws.snapshots_dir / (
        _COMPACT_BACKUP_PREFIX
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-" + uuid4().hex[:8]
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copytree(ws.timeline_dir, backup_dir / "timeline", dirs_exist_ok=True)
    if ws.relations_dir.is_dir():
        shutil.copytree(ws.relations_dir, backup_dir / "relations", dirs_exist_ok=True)
    if ws.counter_file.is_file():
        shutil.copy2(ws.counter_file, backup_dir / ".counter.json")

    # 2. Rewrite the canonical store under the new id space. Parent
    # checks are off because a (hand-crafted) forward reference may
    # legitimately point at a file written later in the same pass.
    for old_file in ws.timeline_dir.glob("*.json"):
        if not old_file.name.startswith("."):
            old_file.unlink()
    for ev in new_events:
        write_event(ws, ev, check_parent=False)

    # 3. Rewrite relations in the new id space. Edges pointing at events
    # merged into a group collapse onto the group's representative;
    # self-loops created by that collapse are dropped.
    if ws.relations_dir.is_dir():
        for rel_file in ws.relations_dir.glob("*.json"):
            if not rel_file.name.startswith("."):
                rel_file.unlink()
    seen_edges: set[tuple[str, str, Relation]] = set()
    for old_source, edges in old_relations.items():
        new_source = id_map.get(old_source)
        if new_source is None:
            continue
        for old_target, relation in edges:
            new_target = id_map.get(old_target)
            if new_target is None or new_target == new_source:
                continue
            key = (new_source, new_target, relation)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            write_relation(ws, new_source, new_target, relation)

    # 4. Derived data: fresh indices and a counter that matches reality.
    IndexStore(ws).rebuild()
    reset_counter(ws, len(new_events) + 1)

    return {
        "original_count": len(events),
        "compacted_count": len(new_events),
        "merged": merged,
        "dry_run": False,
        "backup": str(backup_dir),
    }


def format_compact_id(n: int) -> str:
    """Zero-pad a renumbered id using the canonical width."""
    return str(n).zfill(ID_WIDTH)


# --- helpers -----------------------------------------------------------------


def _canonical_id(ws: Workspace, value: str) -> str:
    """Accept ids with or without leading zeros; verify existence."""
    try:
        resolved = canonical(value)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    if not ws.event_file(resolved).is_file():
        raise EventNotFoundError(resolved)
    return resolved


def _matches(ev: TimelineEvent, q: str) -> bool:
    haystacks = [
        ev.task.lower(),
        ev.summary.lower(),
        (ev.reason or "").lower(),
        " ".join(ev.files).lower(),
        " ".join(ev.tags).lower(),
    ]
    return any(q in h for h in haystacks)
