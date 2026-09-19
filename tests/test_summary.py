"""Tests for deterministic Evolution Summaries (Phase 5)."""

from __future__ import annotations

from pathlib import Path

from nwt.graph.builder import build_graph
from nwt.storage.layout import open_workspace
from nwt.timeline import engine as timeline
from nwt.timeline.summary import build_story, milestones


def _seed(project_root: Path) -> None:
    a = timeline.create_event(
        task="Project created", summary="init", reason="kickoff", root=project_root
    )
    b = timeline.create_event(
        task="Add memory engine",
        summary="graph",
        reason="need storage",
        parent=a.id,
        files=["memory.py"],
        root=project_root,
    )
    timeline.create_event(
        task="Decay",
        summary="decay mechanism",
        reason="forgetting",
        parent=b.id,
        files=["memory.py"],
        tags=["milestone"],
        root=project_root,
    )
    timeline.create_event(
        task="Activation",
        summary="spread",
        reason="retrieval",
        parent=b.id,
        files=["activation.py"],
        tags=["milestone"],
        root=project_root,
    )
    timeline.create_event(
        task="Refactor",
        summary="cleanup",
        reason="clarity",
        parent=b.id,
        files=["activation.py"],
        root=project_root,
    )


def test_milestones_picks_milestone_tagged(project_root: Path) -> None:
    _seed(project_root)
    events = timeline.list_events(root=project_root)
    top = milestones(events, max_milestones=2)
    tagsets = [set(ev.tags) for ev in top]
    assert any("milestone" in s for s in tagsets)


def test_build_story_structure(project_root: Path) -> None:
    _seed(project_root)
    ws = open_workspace(project_root)
    events = timeline.list_events(root=project_root)
    g = build_graph(ws)
    story = build_story(events, project_name="nwt", graph=g)
    assert story.project_name == "nwt"
    assert story.event_count == 5
    assert story.first_event is not None
    assert story.last_event is not None
    # Spine file: the file touched most often is memory.py or activation.py (tie at 2).
    assert story.spine_file in {"memory.py", "activation.py"}
    # Decisions: events with reasons. The seeded events all have reasons.
    assert len(story.decisions) == 5
    text = story.to_text()
    assert "nwt — evolution summary" in text
    assert "milestones:" in text
    assert "decisions (events with stated reasons):" in text


def test_story_groups_by_importance(project_root: Path) -> None:
    timeline.create_event(task="plain", summary="s", root=project_root)
    timeline.create_event(task="big fix", summary="s", importance="high",
                          parent="none", root=project_root)
    timeline.create_event(task="launch", summary="s", importance="milestone",
                          parent="none", root=project_root)
    story = build_story(timeline.list_events(root=project_root), project_name="p")
    levels = {ev.importance for ev in story.important}
    assert levels == {"high", "milestone"}
    text = story.to_text()
    assert "important events (by importance):" in text
    assert "milestone: [3] launch" in text
    d = story.to_dict()
    assert {e["task"] for e in d["important"]} == {"big fix", "launch"}


def test_milestones_importance_boosts_rank(project_root: Path) -> None:
    timeline.create_event(task="plain", summary="s", reason="why", root=project_root)
    timeline.create_event(task="flagged", summary="s", importance="milestone",
                          parent="none", root=project_root)
    top = milestones(timeline.list_events(root=project_root), max_milestones=1)
    assert top[0].task == "flagged"


def test_descendant_counts_match_naive_bfs(project_root: Path) -> None:
    """The O(V+E) bitset pass must agree with per-node BFS semantics."""
    from nwt.graph.builder import build_graph
    from nwt.storage.layout import open_workspace
    from nwt.timeline.summary import descendant_counts

    # Diamond: 1 -> 2 -> 4, 1 -> 3 -> 4, plus a branch 2 -> 5.
    a = timeline.create_event(task="a", summary="s", root=project_root)
    b = timeline.create_event(task="b", summary="s", parent=a.id, root=project_root)
    c = timeline.create_event(task="c", summary="s", parent=a.id, root=project_root)
    d = timeline.create_event(task="d", summary="s", parent=b.id, root=project_root)
    timeline.create_event(task="e", summary="s", parent=b.id, root=project_root)
    timeline.link(c.id, d.id, "extends", root=project_root)

    ws = open_workspace(project_root)
    g = build_graph(ws)
    fast = descendant_counts(g)
    for ev in g.events.values():
        assert fast[ev.id] == len(g.descendants(ev.id)), ev.id
    # The diamond tip is reachable from the root exactly once.
    assert fast[a.id] == 4
