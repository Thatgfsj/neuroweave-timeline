"""ASCII visualization of the Evolution Graph (Phase 6).

The output mirrors the spec's example::

        ○ Project Created
        │
        ○ Memory Engine Added
        │
        ○ Activation Introduced
        │
        ...

We render roots as a stack of vertical chains, with a small separator
between independent branches. Each node is the event's short id plus
its task title.
"""

from __future__ import annotations

from typing import TextIO

from nwt.graph.builder import EvolutionGraph


def render_tree(
    graph: EvolutionGraph,
    *,
    max_per_chain: int = 200,
    file: TextIO | None = None,
) -> str:
    """Render the graph as an ASCII tree.

    ``max_per_chain`` caps the length of any single linear chain to keep
    output readable for very long projects. Each branch (root) is
    printed in turn.
    """
    import io

    out = file or io.StringIO()
    roots = graph.roots()

    if not roots:
        out.write("(empty timeline)\n")
        return out.getvalue() if file is None else ""

    for idx, root in enumerate(roots):
        if idx > 0:
            out.write("\n")
        _render_branch(graph, root.id, out, max_per_chain)

    return out.getvalue() if file is None else ""


def _render_branch(graph: EvolutionGraph, root_id: str, out, max_per_chain: int) -> None:
    # Build a linear chain via the explicit "follows" relation (i.e. parent links).
    # We prefer follows because it represents the narrative spine; other edges
    # (fixes, extends) are branches off the spine and would be shown as forks.
    #
    # When a node has multiple follows-children (siblings), we pick the oldest
    # by id to continue the chain. The remaining siblings are rendered as
    # forks at the parent.
    chain: list[str] = []
    cur: str | None = root_id
    seen: set[str] = set()
    while cur and cur in graph.events and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        follows_children = [
            e.target
            for e in graph.outgoing.get(cur, ())
            if e.relation.value == "follows" and e.target not in seen
        ]
        follows_children.sort()  # oldest id first
        cur = follows_children[0] if follows_children else None
        if len(chain) >= max_per_chain:
            break

    # Render the spine, with each node's children listed as indented forks
    # immediately below the node's marker line. The vertical "│" connector
    # to the next spine node goes at the end of the segment.
    for i, eid in enumerate(chain):
        ev = graph.events[eid]
        marker = "○" if i == 0 else "│"
        out.write(f"{marker} {ev.short_id():>4}  {ev.task}\n")

        # Collect children: siblings (follows-but-not-spine-next) and any
        # non-follows typed edges, in stable order.
        children: list[tuple[str, str]] = []
        cur_follows = sorted(
            e.target
            for e in graph.outgoing.get(eid, ())
            if e.relation.value == "follows"
        )
        spine_next = chain[i + 1] if i + 1 < len(chain) else None
        for sib in cur_follows:
            if sib != spine_next:
                children.append(("sibling", sib))
        for edge in graph.outgoing.get(eid, ()):
            if edge.relation.value != "follows":
                children.append((edge.relation.value, edge.target))

        for j, (kind, target) in enumerate(children):
            branch = "└─" if j == len(children) - 1 else "├─"
            target_ev = graph.events[target]
            out.write(
                f"      {branch} {kind:<8} \u2192 [{target_ev.short_id():>4}] {target_ev.task}\n"
            )

        if i < len(chain) - 1:
            out.write("│\n")
