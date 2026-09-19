"""Deterministic Evolution Summaries (Phase 5).

The spec asks for "100 events → 10 milestones → 1 project story". Without
LLM planning in the MVP, we have to compress deterministically. The
heuristic below is good enough that an agent reading the result can
reconstruct the project's history, and it runs in milliseconds.

Milestone selection score::

    score(e) = descendants(e) * 2
             + (5 if 'milestone' in e.tags else 0)
             + (5 if 'release'   in e.tags else 0)
             + (5 if e.importance == 'milestone' else 0)
             + (3 if e.importance == 'high'      else 0)
             + (2 if e.reason           else 0)
             + (1 if e.files            else 0)

The top ``max_milestones`` events by score become the project's
milestones. Ties are broken by id order (older wins) so the output is
stable across runs.

Descendant counts for every event are computed in one O(V+E) pass using
integer bitsets propagated in reverse topological order — equivalent to
running a BFS per event (which was O(V·(V+E))) but fast enough for
five-figure timelines.

The *project story* is a structured bundle:

* project name + first/last event timestamps
* ordered list of milestones
* the file that changed most often (the "spine file")
* the set of decision events (those with a non-empty ``reason``)
* events flagged ``high`` or ``milestone`` importance
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable

from nwt.core.event import TimelineEvent
from nwt.core.time import short_date as _short_date
from nwt.graph.builder import EvolutionGraph


@dataclass
class ProjectStory:
    """A compressed, agent-friendly summary of a project's timeline."""

    project_name: str | None
    first_event: TimelineEvent | None
    last_event: TimelineEvent | None
    event_count: int
    milestones: list[TimelineEvent] = field(default_factory=list)
    spine_file: str | None = None
    decisions: list[TimelineEvent] = field(default_factory=list)
    important: list[TimelineEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-ready form shared verbatim by the CLI and MCP surfaces."""
        return {
            "project_name": self.project_name,
            "first_event": self.first_event.to_dict() if self.first_event else None,
            "last_event": self.last_event.to_dict() if self.last_event else None,
            "event_count": self.event_count,
            "spine_file": self.spine_file,
            "milestones": [ev.to_dict() for ev in self.milestones],
            "decisions": [ev.to_dict() for ev in self.decisions],
            "important": [ev.to_dict() for ev in self.important],
        }

    def to_text(self) -> str:
        """Render the story as plain text suitable for LLM context."""
        lines: list[str] = []
        title = self.project_name or "project"
        lines.append(f"# {title} — evolution summary")
        lines.append("")
        if self.first_event and self.last_event:
            t0 = _short_date(self.first_event.timestamp)
            t1 = _short_date(self.last_event.timestamp)
            lines.append(f"span: {t0} → {t1}  ({self.event_count} events)")
        else:
            lines.append(f"({self.event_count} events)")
        lines.append("")

        if self.milestones:
            lines.append("milestones:")
            for ev in self.milestones:
                marker = "  - " + ev.short_id() + "  " + ev.task
                if ev.reason:
                    marker += f"  — {ev.reason}"
                lines.append(marker)
            lines.append("")

        if self.important:
            lines.append("important events (by importance):")
            for level in ("milestone", "high"):
                group = [ev for ev in self.important if ev.importance == level]
                if group:
                    joined = ", ".join(
                        f"[{ev.short_id()}] {ev.task}" for ev in group
                    )
                    lines.append(f"  {level}: {joined}")
            lines.append("")

        if self.spine_file:
            lines.append(f"spine file: {self.spine_file}")
            lines.append("")

        if self.decisions:
            lines.append("decisions (events with stated reasons):")
            for ev in self.decisions[:20]:
                lines.append(f"  - [{ev.short_id()}] {ev.task}: {ev.reason}")
            if len(self.decisions) > 20:
                lines.append(f"  ... and {len(self.decisions) - 20} more")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


# --- public API --------------------------------------------------------------


def descendant_counts(graph: EvolutionGraph) -> dict[str, int]:
    """Reachable-descendant counts for every event, in one O(V+E) pass.

    Equivalent to ``len(graph.descendants(v))`` per node (set semantics,
    diamonds deduped) but computed with integer bitsets propagated in
    reverse topological order. Nodes on a (hand-crafted) cycle fall back
    to a per-node BFS.
    """
    ids = list(graph.events)
    indegree = {eid: len(graph.incoming.get(eid, ())) for eid in ids}
    queue = deque(eid for eid in ids if indegree[eid] == 0)
    topo: list[str] = []
    while queue:
        cur = queue.popleft()
        topo.append(cur)
        for edge in graph.outgoing.get(cur, ()):
            indegree[edge.target] -= 1
            if indegree[edge.target] == 0:
                queue.append(edge.target)

    bit = {eid: 1 << i for i, eid in enumerate(ids)}
    for cur in reversed(topo):
        mask = bit[cur]
        for edge in graph.outgoing.get(cur, ()):
            target = edge.target
            if target in bit and target != cur:
                mask |= bit[target]
        bit[cur] = mask

    # Each mask includes the node itself; ``descendants()`` excludes it.
    counts = {eid: bit[eid].bit_count() - 1 for eid in topo}
    for eid in ids:
        if eid not in counts:  # cycle: fall back to exact BFS
            counts[eid] = len(graph.descendants(eid))
    return counts


def milestones(
    events: Iterable[TimelineEvent],
    graph: EvolutionGraph | None = None,
    *,
    max_milestones: int = 10,
) -> list[TimelineEvent]:
    """Return the top-``max_milestones`` events by impact score."""
    events = list(events)
    if not events:
        return []

    counts = descendant_counts(graph) if graph is not None else {}

    def score(ev: TimelineEvent) -> tuple[int, int]:
        # Sort key: (-score, id) — highest score wins, ties go to oldest.
        s = 0
        s += counts.get(ev.id, 0) * 2
        if "milestone" in ev.tags:
            s += 5
        if "release" in ev.tags:
            s += 5
        if ev.importance == "milestone":
            s += 5
        if ev.importance == "high":
            s += 3
        if ev.reason:
            s += 2
        if ev.files:
            s += 1
        return (-s, int(ev.id) if ev.id else 0)

    ranked = sorted(events, key=score)
    return ranked[:max_milestones]


def build_story(
    events: Iterable[TimelineEvent],
    *,
    project_name: str | None = None,
    graph: EvolutionGraph | None = None,
    max_milestones: int = 10,
) -> ProjectStory:
    """Build a :class:`ProjectStory` from the project's events."""
    events = list(events)
    events.sort(key=lambda e: e.id)

    first = events[0] if events else None
    last = events[-1] if events else None

    file_counter: Counter[str] = Counter()
    decisions: list[TimelineEvent] = []
    important: list[TimelineEvent] = []
    for ev in events:
        for f in ev.files:
            file_counter[f] += 1
        if ev.reason:
            decisions.append(ev)
        if ev.importance in ("high", "milestone"):
            important.append(ev)

    spine = file_counter.most_common(1)[0][0] if file_counter else None

    return ProjectStory(
        project_name=project_name,
        first_event=first,
        last_event=last,
        event_count=len(events),
        milestones=milestones(events, graph, max_milestones=max_milestones),
        spine_file=spine,
        decisions=decisions,
        important=important,
    )


# --- helpers -----------------------------------------------------------------
