"""Build an in-memory Evolution Graph from a workspace.

The graph treats every event as a node and every relation (including the
implicit ``parent`` chain) as a directed edge. The graph is small enough
to live in memory: thousands of events are still well under a megabyte
when stored as plain Python objects, and graph operations are O(V+E).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable

from nwt.core.event import TimelineEvent
from nwt.core.relations import Relation
from nwt.storage.layout import Workspace
from nwt.storage.reader import read_all_events, read_all_relations


@dataclass
class Edge:
    """A directed edge in the Evolution Graph."""

    source: str
    target: str
    relation: Relation


@dataclass
class EvolutionGraph:
    """Directed multigraph over timeline events.

    Edges are grouped by source node for O(1) forward lookup. Reverse
    lookups (who points at me?) are also O(1) thanks to ``incoming``.
    """

    events: dict[str, TimelineEvent] = field(default_factory=dict)
    outgoing: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    incoming: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))

    # --- queries --------------------------------------------------------------

    def event(self, event_id: str) -> TimelineEvent:
        return self.events[event_id]

    def children(self, event_id: str) -> list[Edge]:
        return list(self.outgoing.get(event_id, ()))

    def parents(self, event_id: str) -> list[Edge]:
        return list(self.incoming.get(event_id, ()))

    def ancestors(self, event_id: str) -> list[TimelineEvent]:
        """All events reachable by following incoming edges, BFS, dedup."""
        seen: set[str] = set()
        order: list[str] = []
        q: deque[str] = deque([event_id])
        while q:
            cur = q.popleft()
            for edge in self.incoming.get(cur, ()):
                if edge.source in seen or edge.source == event_id:
                    continue
                seen.add(edge.source)
                order.append(edge.source)
                q.append(edge.source)
        return [self.events[eid] for eid in order if eid in self.events]

    def descendants(self, event_id: str) -> list[TimelineEvent]:
        """All events reachable by following outgoing edges, BFS, dedup."""
        seen: set[str] = set()
        order: list[str] = []
        q: deque[str] = deque([event_id])
        while q:
            cur = q.popleft()
            for edge in self.outgoing.get(cur, ()):
                if edge.target in seen or edge.target == event_id:
                    continue
                seen.add(edge.target)
                order.append(edge.target)
                q.append(edge.target)
        return [self.events[eid] for eid in order if eid in self.events]

    def linear_chain(self, event_id: str) -> list[TimelineEvent]:
        """Follow ``parent`` links backwards to produce a clean linear history."""
        chain: list[TimelineEvent] = []
        cur_id: str | None = event_id
        seen: set[str] = set()
        while cur_id and cur_id in self.events and cur_id not in seen:
            seen.add(cur_id)
            chain.append(self.events[cur_id])
            cur_id = self.events[cur_id].parent
        chain.reverse()
        return chain

    def roots(self) -> list[TimelineEvent]:
        """Events with no incoming edges — the heads of independent branches."""
        heads = [eid for eid in self.events if not self.incoming.get(eid)]
        return [self.events[eid] for eid in sorted(heads)]

    # --- pretty printing ------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-ready snapshot of the graph (for the MCP tools)."""
        return {
            "nodes": [
                {
                    "id": ev.id,
                    "task": ev.task,
                    "summary": ev.summary,
                    "reason": ev.reason,
                    "files": ev.files,
                    "tags": ev.tags,
                    "timestamp": ev.timestamp,
                }
                for ev in sorted(self.events.values(), key=lambda e: e.id)
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation.value,
                }
                for edges in self.outgoing.values()
                for e in edges
            ],
        }


# --- factory -----------------------------------------------------------------


def build_graph(ws: Workspace) -> EvolutionGraph:
    """Construct an :class:`EvolutionGraph` from a workspace."""
    events = {ev.id: ev for ev in read_all_events(ws)}
    g = EvolutionGraph(events=events)

    # Implicit parent chain → "follows" edges.
    for ev in events.values():
        if ev.parent and ev.parent in events:
            edge = Edge(source=ev.parent, target=ev.id, relation=Relation.FOLLOWS)
            g.outgoing[ev.parent].append(edge)
            g.incoming[ev.id].append(edge)

    # Explicit typed relations.
    raw = read_all_relations(ws)
    for source_id, edges in raw.items():
        if source_id not in events:
            continue
        for target_id, relation in edges:
            if target_id not in events:
                continue
            edge = Edge(source=source_id, target=target_id, relation=relation)
            g.outgoing[source_id].append(edge)
            g.incoming[target_id].append(edge)

    return g
