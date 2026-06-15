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
