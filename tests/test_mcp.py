"""Tests for the MCP tool layer.

These call the tool functions directly (FastMCP's decorator returns the
plain function) against a real temporary workspace. This layer had zero
coverage until the ``explain_file`` name-shadowing bug shipped — that
bug made the tool crash on every call with a TypeError, invisible to CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nwt.mcp import server as mcp_server
from nwt.timeline import engine as timeline


@pytest.fixture
def mcp_root(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point $NWT_ROOT at a fresh workspace for the tool functions."""
    monkeypatch.setenv("NWT_ROOT", str(project_root))
    return project_root


def test_create_event_tool(mcp_root: Path) -> None:
    out = mcp_server.create_event(
        task="Add activation engine",
        summary="spread activation",
        reason="retrieval was slow",
        files=["activation.py"],
        tags=["memory"],
    )
    assert out["task"] == "Add activation engine"
    assert out["id"]
    assert out["timestamp"]
    assert out["reason"] == "retrieval was slow"


def test_create_event_tool_auto_chains(mcp_root: Path) -> None:
    first = mcp_server.create_event(task="a", summary="a")
    second = mcp_server.create_event(task="b", summary="b")
    assert second["parent"] == first["id"]


def test_search_history_tool(mcp_root: Path) -> None:
    mcp_server.create_event(task="A", summary="alpha", reason="about graphs")
    mcp_server.create_event(task="B", summary="beta", reason="about caches")
    hits = mcp_server.search_history("graphs")
    assert [e["task"] for e in hits] == ["A"]


def test_search_history_scope_and_limit(mcp_root: Path) -> None:
    # Three tag matches plus one reason match; narrowing to tags only
    # must return 3 — and limit=2 must cap AFTER narrowing, not before.
    mcp_server.create_event(task="t1", summary="s", tags=["needle"])
    mcp_server.create_event(task="t2", summary="s", tags=["needle"])
    mcp_server.create_event(task="t3", summary="s", tags=["needle"])
    mcp_server.create_event(task="t4", summary="s", reason="needle in prose")

    hits = mcp_server.search_history("needle", search_files=False, search_tags=False)
    assert [e["task"] for e in hits] == ["t4"]

    hits = mcp_server.search_history("needle", limit=2)
    assert len(hits) == 2

    hits = mcp_server.search_history("needle", search_tags=True, search_files=False, limit=2)
    assert len(hits) == 2
    assert all(e["task"] != "t4" for e in hits)


def test_get_project_story_tool(mcp_root: Path) -> None:
    mcp_server.create_event(task="Kickoff", summary="start", reason="begin")
    story = mcp_server.get_project_story()
    assert story["project_name"] == "test-project"
    assert story["event_count"] == 1
    assert story["text"]
    assert "evolution summary" in story["text"]
    assert "important" in story


def test_get_project_story_negative_milestones(mcp_root: Path) -> None:
    # A negative cap used to silently drop one milestone; it now behaves
    # like "unlimited" (all milestones), matching the negative-limit
    # handling in search_history.
    for i in range(3):
        mcp_server.create_event(task=f"t{i}", summary="s", importance="milestone")
    story = mcp_server.get_project_story(max_milestones=-1)
    assert len(story["milestones"]) == 3


def test_explain_file_tool(mcp_root: Path) -> None:
    # Regression: the tool used to call itself (name shadowed the lineage
    # helper) and crashed with TypeError on every invocation.
    created = mcp_server.create_event(
        task="Add activation",
        summary="spread",
        reason="retrieval perf",
        files=["activation.py"],
    )
    mcp_server.create_event(task="Tune activation", summary="vectorize",
                            files=["activation.py"])
    out = mcp_server.explain_file("activation.py")
    assert out["file"] == "activation.py"
    assert out["created_in"] == int(created["id"])
    assert out["modified_in"] == [int(created["id"]) + 1]
    assert out["reason"] == "retrieval perf"
    assert out["text"]
    assert len(out["events"]) == 2


def test_explain_file_tool_unknown_file(mcp_root: Path) -> None:
    out = mcp_server.explain_file("ghost.py")
    assert out["created_in"] is None
    assert out["modified_in"] == []
    assert out["events"] == []
