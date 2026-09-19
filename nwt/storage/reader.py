"""Read events and relations from a workspace.

Reads are defensive: the canonical files are hand-editable and
restorable from backups, so a corrupt file surfaces as a typed
:class:`CorruptEventError` (never a raw traceback), and malformed
relation files are skipped with a warning instead of poisoning graph
queries or a ``compact`` rewrite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from nwt.core.errors import CorruptEventError
from nwt.core.event import TimelineEvent
from nwt.core.relations import Relation
from nwt.storage.layout import Workspace


def read_event(ws: Workspace, event_id: str) -> TimelineEvent:
    """Load a single event. Raises :class:`EventNotFoundError` if missing."""
    path = ws.event_file(event_id)
    if not path.is_file():
        from nwt.core.errors import EventNotFoundError

        raise EventNotFoundError(event_id)
    return _parse_event_file(path)


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
        events.append(_parse_event_file(path))
    return events


def _parse_event_file(path: Path) -> TimelineEvent:
    try:
        return TimelineEvent.from_json(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise CorruptEventError(path) from e
    except json.JSONDecodeError as e:
        raise CorruptEventError(path) from e


def read_relations(ws: Workspace, source_id: str) -> list[tuple[str, Relation]]:
    """Return ``[(target_id, relation), ...]`` for edges leaving ``source_id``.

    A malformed file (bad JSON, wrong shape) is skipped with a warning:
    relations are derived state the user can recreate with ``nwt link``,
    and one bad file must not block graph queries or a compact rewrite.
    """
    path = ws.relation_file(source_id)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        _warn_skipped(path, e)
        return []
    if not isinstance(raw, dict):
        _warn_skipped(path, "not a JSON object")
        return []
    out: list[tuple[str, Relation]] = []
    for edge in raw.get("edges", []):
        try:
            out.append((str(edge["target"]), Relation.parse(edge["relation"])))
        except (KeyError, ValueError, TypeError):
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


def _warn_skipped(path: Path, reason: object) -> None:
    print(
        f"nwt: warning: skipping unreadable relations file {path} ({reason}); "
        "recreate edges with `nwt link` if needed",
        file=sys.stderr,
    )
