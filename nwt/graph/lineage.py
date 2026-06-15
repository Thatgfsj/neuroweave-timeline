"""Lineage helpers — answering "where did this come from?"."""

from __future__ import annotations

from nwt.core.event import TimelineEvent
from nwt.graph.builder import EvolutionGraph


def explain_file(graph: EvolutionGraph, file_path: str) -> dict:
    """Return a structured answer to "why does this file exist?".

    Output is shaped for direct rendering by the CLI and for use as an
    MCP tool response. Format::

        {
            "file": "activation.py",
            "created_in": 23 | None,
            "modified_in": [45, 67],
            "events": [<TimelineEvent>, ...],
            "reason": "Improve graph retrieval performance." | None,
        }
    """
    events: list[TimelineEvent] = [
        ev for ev in graph.events.values() if file_path in ev.files
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
