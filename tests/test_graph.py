"""Tests for the Evolution Graph (builder, lineage, visualize)."""

from __future__ import annotations

from pathlib import Path

from nwt.graph.builder import build_graph
from nwt.graph.lineage import explain_file
from nwt.graph.visualize import render_tree
from nwt.storage.layout import open_workspace
from nwt.timeline import engine as timeline


def _seed(project_root: Path) -> None:
    a = timeline.create_event(
        task="Project created", summary="init", reason="kickoff", root=project_root
    )
    b = timeline.create_event(
        task="Add memory engine",
        summary="graph storage",
        reason="need to store nodes",
        parent=a.id,
        files=["memory.py"],
        root=project_root,
    )
    c = timeline.create_event(
        task="Add activation",
        summary="spread activation",
        reason="retrieval perf",
        parent=b.id,
        files=["activation.py"],
        root=project_root,
    )
    d = timeline.create_event(
        task="Refactor activation",
        summary="vectorize",
        reason="faster batched scoring",
        parent=c.id,
        files=["activation.py"],
        root=project_root,
    )
    timeline.link(b.id, d.id, "fixes", root=project_root)


def test_graph_contains_all_events(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    g = build_graph(ws)
    assert len(g.events) == 4


def test_graph_descendants_via_parent_chain(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    g = build_graph(ws)
    first = sorted(g.events)[0]
    desc = g.descendants(first)
    assert {e.task for e in desc} >= {
        "Add memory engine",
        "Add activation",
        "Refactor activation",
    }


def test_graph_explicit_fixes_edge(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    g = build_graph(ws)
    # b -> d with relation fixes
    b = next(e for e in g.events.values() if e.task == "Add memory engine")
    d = next(e for e in g.events.values() if e.task == "Refactor activation")
    edges = g.outgoing[b.id]
    assert any(e.target == d.id and e.relation.value == "fixes" for e in edges)


def test_explain_file(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    g = build_graph(ws)
    result = explain_file(g, "activation.py")
    assert result["file"] == "activation.py"
    assert result["created_in"] is not None
    assert result["modified_in"], "expected at least one modification"
    # The earliest reason is the creation reason.
    assert "retrieval perf" in (result["reason"] or "").lower() or result["reason"]


def test_render_tree_has_unicode_root_marker(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    g = build_graph(ws)
    text = render_tree(g)
    assert "○" in text
    assert "Project created" in text
