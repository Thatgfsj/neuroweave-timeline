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


# --- auto-chain (default parent) ----------------------------------------------


def test_create_event_auto_chains_to_latest(project_root: Path) -> None:
    a = timeline.create_event(task="a", summary="a", root=project_root)
    b = timeline.create_event(task="b", summary="b", root=project_root)
    c = timeline.create_event(task="c", summary="c", root=project_root)
    assert b.parent == a.id
    assert c.parent == b.id


def test_create_event_explicit_branch(project_root: Path) -> None:
    a = timeline.create_event(task="a", summary="a", root=project_root)
    fork = timeline.create_event(task="f", summary="f", parent="none", root=project_root)
    assert fork.parent is None
    other = timeline.create_event(task="o", summary="o", parent=a.id, root=project_root)
    assert other.parent == a.id


def test_create_event_rejects_unknown_parent(project_root: Path) -> None:
    with pytest.raises(EventNotFoundError):
        timeline.create_event(task="a", summary="a", parent="42", root=project_root)


# --- diff validation -----------------------------------------------------------


def test_diff_reversed_range_raises(project_root: Path) -> None:
    for i in range(3):
        timeline.create_event(task=f"t{i}", summary=f"s{i}", root=project_root)
    with pytest.raises(ValidationError, match="comes after"):
        timeline.diff_events("3", "1", root=project_root)


def test_diff_same_event_raises(project_root: Path) -> None:
    timeline.create_event(task="t", summary="s", root=project_root)
    timeline.create_event(task="t2", summary="s2", root=project_root)
    with pytest.raises(ValidationError, match="itself"):
        timeline.diff_events("1", "1", root=project_root)


def test_diff_files_in_both_key(project_root: Path) -> None:
    timeline.create_event(task="a", summary="a", files=["x.py", "y.py"], root=project_root)
    timeline.create_event(task="b", summary="b", files=["x.py", "z.py"],
                          parent="none", root=project_root)
    result = timeline.diff_events("1", "2", root=project_root)
    assert result["files_in_both"] == ["x.py"]
    assert result["files_added"] == ["z.py"]
    assert result["files_removed"] == ["y.py"]
    assert "files_modified" not in result


# --- compact (destructive rewrite) ---------------------------------------------


def _seed_for_compact(root) -> None:
    """3 same-tag events, 1 other-tag event, 1 later same-tag event."""
    timeline.create_event(task="t1", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t2", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t3", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t4", summary="s", tags=["y"], root=root)
    timeline.create_event(task="t5", summary="s", tags=["x"], root=root)
    timeline.link("4", "5", "fixes", root=root)


def test_compact_merges_and_cleans_store(project_root: Path) -> None:
    _seed_for_compact(project_root)
    result = timeline.compact_events(root=project_root, min_group_size=3)

    # Reported counts must match what is actually on disk (regression:
    # compact used to claim 4 -> 2 while leaving every old file behind).
    assert result["merged"] == 2
    assert result["compacted_count"] == 3
    on_disk = sorted(p.name for p in (project_root / ".nwt" / "timeline").glob("*.json"))
    assert len(on_disk) == 3
    events = timeline.list_events(root=project_root)
    assert len(events) == result["compacted_count"]
    assert events[0].task == "t1 ... t3"
    assert events[0].meta["compacted"] == ["000001", "000002", "000003"]


def test_compact_preserves_relations_and_chains(project_root: Path) -> None:
    _seed_for_compact(project_root)
    timeline.link("1", "4", "caused_by", root=project_root)
    result = timeline.compact_events(root=project_root, min_group_size=3)

    rels = timeline.iter_relations(root=project_root)
    flat = [(s, t, r.value) for s, outs in rels.items() for t, r in outs]
    # 4 --fixes--> 5 becomes 000002 --fixes--> 000003;
    # 1 --caused_by--> 4 becomes 000001 --caused_by--> 000002.
    assert ("000002", "000003", "fixes") in flat
    assert ("000001", "000002", "caused_by") in flat
    assert result["backup"] is not None
    assert Path(result["backup"]).is_dir()


def test_compact_resets_counter(project_root: Path) -> None:
    _seed_for_compact(project_root)
    timeline.compact_events(root=project_root, min_group_size=3)
    fresh = timeline.create_event(task="after", summary="s", parent="none", root=project_root)
    assert fresh.id == "000004"


def test_compact_dry_run_changes_nothing(project_root: Path) -> None:
    _seed_for_compact(project_root)
    before = sorted(p.name for p in (project_root / ".nwt" / "timeline").glob("*.json"))
    result = timeline.compact_events(root=project_root, min_group_size=3, dry_run=True)
    assert result["dry_run"] is True
    assert result["backup"] is None
    after = sorted(p.name for p in (project_root / ".nwt" / "timeline").glob("*.json"))
    assert before == after
    assert len(timeline.list_events(root=project_root)) == 5


def test_compact_respects_time_window(project_root: Path) -> None:
    timeline.create_event(task="a", summary="s", tags=["x"],
                          timestamp="2026-01-01T00:00:00Z", root=project_root)
    timeline.create_event(task="b", summary="s", tags=["x"],
                          timestamp="2026-01-01T05:00:00Z", parent="none", root=project_root)
    timeline.create_event(task="c", summary="s", tags=["x"],
                          timestamp="2026-01-01T10:00:00Z", parent="none", root=project_root)
    # 5h gaps: a 2h window must not merge them.
    result = timeline.compact_events(root=project_root, time_window_seconds=7200)
    assert result["merged"] == 0
    # A 6h window merges all three.
    result = timeline.compact_events(root=project_root, time_window_seconds=21600)
    assert result["merged"] == 2


def test_compact_rejects_invalid_params(project_root: Path) -> None:
    # min_group <= 1 used to "merge" single events into corrupted
    # self-duplicates while reporting "no events to compact".
    with pytest.raises(ValidationError, match="min_group_size"):
        timeline.compact_events(root=project_root, min_group_size=1)
    with pytest.raises(ValidationError, match="min_group_size"):
        timeline.compact_events(root=project_root, min_group_size=0)
    with pytest.raises(ValidationError, match="time_window_seconds"):
        timeline.compact_events(root=project_root, time_window_seconds=-1)


def test_compact_keeps_chain_connected(project_root: Path) -> None:
    # A merged group's head used to lose its parent, splitting the graph.
    a = timeline.create_event(task="root", summary="s", root=project_root)
    for i in range(4):
        timeline.create_event(task=f"t{i}", summary="s", tags=["grp"], root=project_root)
    timeline.compact_events(root=project_root, min_group_size=3)
    events = timeline.list_events(root=project_root)
    assert len(events) == 2
    assert events[1].parent == a.id


def test_search_by_file_query_normalization(project_root: Path) -> None:
    timeline.create_event(task="a", summary="a", files=["src/foo.py"], root=project_root)
    assert [e.task for e in timeline.search_by_file("src\\foo.py", root=project_root)]
    assert [e.task for e in timeline.search_by_file("./src/foo.py", root=project_root)]
    assert [e.task for e in timeline.search_by_file("src/../src/foo.py", root=project_root)]
    # Case-insensitive fallback (Windows-style queries).
    assert [e.task for e in timeline.search_by_file("SRC/FOO.PY", root=project_root)]
    assert timeline.search_by_file("nope.py", root=project_root) == []


def test_list_and_search_reject_negative_limits(project_root: Path) -> None:
    timeline.create_event(task="a", summary="a", root=project_root)
    with pytest.raises(ValidationError):
        timeline.list_events(root=project_root, limit=-1)
    with pytest.raises(ValidationError):
        timeline.list_events(root=project_root, offset=-2)
    with pytest.raises(ValidationError):
        timeline.search("a", root=project_root, limit=-1)
