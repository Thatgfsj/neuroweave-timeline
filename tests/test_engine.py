"""Tests for the public timeline engine API."""

from __future__ import annotations

from pathlib import Path

import pytest

from nwt.core.errors import EventNotFoundError, ValidationError
from nwt.timeline import engine as timeline


def test_create_and_get(project_root: Path) -> None:
    ev = timeline.create_event(
        task="Implement activation",
        summary="Add activation spreading",
        reason="Graph retrieval was slow",
        files=["activation.py"],
        tags=["memory"],
        root=project_root,
    )
    got = timeline.get_event(ev.id, root=project_root)
    assert got.id == ev.id
    assert got.task == "Implement activation"
    assert got.reason == "Graph retrieval was slow"


def test_get_accepts_short_id(project_root: Path) -> None:
    ev = timeline.create_event(task="x", summary="y", root=project_root)
    got = timeline.get_event(str(int(ev.id)), root=project_root)
    assert got.id == ev.id


def test_get_unknown_raises(project_root: Path) -> None:
    with pytest.raises(EventNotFoundError):
        timeline.get_event("999999", root=project_root)


def test_create_rejects_empty_task(project_root: Path) -> None:
    with pytest.raises(ValidationError):
        timeline.create_event(task="", summary="x", root=project_root)
    with pytest.raises(ValidationError):
        timeline.create_event(task="   ", summary="x", root=project_root)


def test_list_events_with_limit_and_offset(project_root: Path) -> None:
    for i in range(5):
        timeline.create_event(task=f"t{i}", summary=f"s{i}", root=project_root)
    page = timeline.list_events(root=project_root, limit=2, offset=1)
    assert [e.task for e in page] == ["t1", "t2"]


def test_list_events_reverse(project_root: Path) -> None:
    for i in range(3):
        timeline.create_event(task=f"t{i}", summary=f"s{i}", root=project_root)
    rev = timeline.list_events(root=project_root, reverse=True)
    assert [e.task for e in rev] == ["t2", "t1", "t0"]


def test_search_finds_in_summary_and_reason(project_root: Path) -> None:
    timeline.create_event(
        task="A", summary="alpha", reason="contains the word graph", root=project_root
    )
    timeline.create_event(
        task="B", summary="beta", reason="mentions activation.py", root=project_root
    )
    timeline.create_event(
        task="C", summary="gamma", tags=["memory"], root=project_root
    )
    res = timeline.search("graph", root=project_root)
    assert [e.task for e in res] == ["A"]
    res = timeline.search("activation.py", root=project_root)
    assert [e.task for e in res] == ["B"]
    res = timeline.search("memory", root=project_root)
    assert [e.task for e in res] == ["C"]


def test_search_by_file_and_tag(project_root: Path) -> None:
    timeline.create_event(task="a", summary="a", files=["foo.py"], root=project_root)
    timeline.create_event(task="b", summary="b", files=["foo.py", "bar.py"], root=project_root)
    timeline.create_event(task="c", summary="c", tags=["release"], root=project_root)
    by_file = timeline.search_by_file("foo.py", root=project_root)
    assert {e.task for e in by_file} == {"a", "b"}
    by_tag = timeline.search_by_tag("release", root=project_root)
    assert {e.task for e in by_tag} == {"c"}


def test_link_creates_relation(project_root: Path) -> None:
    a = timeline.create_event(task="a", summary="a", root=project_root)
    b = timeline.create_event(task="b", summary="b", root=project_root)
    timeline.link(a.id, b.id, "fixes", root=project_root)
    rels = timeline.iter_relations(root=project_root)
    assert rels[a.id] == [(b.id, "fixes")]
