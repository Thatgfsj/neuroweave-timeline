"""Lineage helpers — answering "where did this come from?"."""

from __future__ import annotations

from nwt.core.event import TimelineEvent, normalize_file
from nwt.graph.builder import EvolutionGraph


def explain_file(graph: EvolutionGraph, file_path: str) -> dict:
    """Return a structured answer to "why does this file exist?".

    The query is normalized like the stored paths, so ``src\\foo.py``
    finds events logged as ``src/foo.py``. Output is shaped for direct
    rendering by the CLI and for use as an MCP tool response. Format::

        {
            "file": "activation.py",
            "created_in": 23 | None,
            "modified_in": [45, 67],
            "events": [<TimelineEvent>, ...],
            "reason": "Improve graph retrieval performance." | None,
        }
    """
    want = normalize_file(file_path)
    events: list[TimelineEvent] = [
        ev for ev in graph.events.values()
        if any(normalize_file(f) == want for f in ev.files)
    ]
    events.sort(key=lambda e: e.id)

    created_in: int | None = None
    modified_in: list[int] = []
    for ev in events:
        if created_in is None:
            created_in = int(ev.id)
        else:
            modified_in.append(int(ev.id))

    # Heuristic: the "reason" comes from the earliest event that has one,
    # otherwise from the most recent event with a reason.
    reason: str | None = None
    for ev in events:
        if ev.reason:
            reason = ev.reason
            break

    return {
        "file": file_path,
        "created_in": created_in,
        "modified_in": modified_in,
        "events": events,
        "reason": reason,
    }


def to_json_dict(result: dict) -> dict:
    """JSON-ready form of an :func:`explain_file` result.

    Shared verbatim by the CLI and MCP surfaces so both render the same
    payload (each adds its own text rendering on top).
    """
    return {
        "file": result["file"],
        "created_in": result["created_in"],
        "modified_in": result["modified_in"],
        "reason": result["reason"],
        "events": [ev.to_dict() for ev in result["events"]],
    }
