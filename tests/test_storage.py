"""Tests for the storage layer (layout, reader, writer, atomic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nwt.core.event import TimelineEvent
from nwt.core.errors import AlreadyInitializedError, EventNotFoundError, NotInitializedError, ValidationError
from nwt.core.ids import ID_WIDTH
from nwt.core.relations import Relation
from nwt.storage.layout import init_workspace, is_initialized, open_workspace
from nwt.storage.reader import read_all_events, read_event, read_relations
from nwt.storage.writer import reset_counter, write_event, write_relation
from nwt.timeline.engine import compact_events


def test_init_creates_directory_tree(project_root: Path) -> None:
    assert is_initialized(project_root)
    assert (project_root / ".nwt" / "timeline").is_dir()
    assert (project_root / ".nwt" / "relations").is_dir()
    assert (project_root / ".nwt" / "snapshots").is_dir()
    assert (project_root / ".nwt" / "metadata.json").is_file()
    assert (project_root / ".nwt" / ".counter.json").is_file()


def test_init_refuses_to_overwrite(project_root: Path) -> None:
    with pytest.raises(AlreadyInitializedError):
        init_workspace(project_root)


def test_open_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(NotInitializedError):
        open_workspace(tmp_path)


def test_write_event_allocates_sequential_ids(project_root: Path) -> None:
    ws = open_workspace(project_root)
    a = write_event(
        ws, TimelineEvent.create(task="first", summary="init")
    )
    b = write_event(
        ws, TimelineEvent.create(task="second", summary="more", parent=a.id)
    )
    c = write_event(
        ws, TimelineEvent.create(task="third", summary="final", parent=b.id)
    )
    assert a.id == "1".zfill(ID_WIDTH)
    assert b.id == "2".zfill(ID_WIDTH)
    assert c.id == "3".zfill(ID_WIDTH)
    assert b.parent == a.id


def test_write_event_rejects_missing_parent(project_root: Path) -> None:
    ws = open_workspace(project_root)
    with pytest.raises(EventNotFoundError):
        write_event(
            ws,
            TimelineEvent.create(task="x", summary="y", parent="999999"),
        )


def test_write_relation_is_idempotent(project_root: Path) -> None:
    ws = open_workspace(project_root)
    a = write_event(ws, TimelineEvent.create(task="a", summary="a"))
    b = write_event(ws, TimelineEvent.create(task="b", summary="b"))
    write_relation(ws, a.id, b.id, Relation.FIXES)
    write_relation(ws, a.id, b.id, Relation.FIXES)  # duplicate, must not append
    edges = read_relations(ws, a.id)
    assert edges == [(b.id, Relation.FIXES)]


def test_write_relation_to_self_raises(project_root: Path) -> None:
    from nwt.core.errors import RelationError

    ws = open_workspace(project_root)
    a = write_event(ws, TimelineEvent.create(task="a", summary="a"))
    with pytest.raises(RelationError):
        write_relation(ws, a.id, a.id, Relation.EXTENDS)


def test_file_index_tracks_events(project_root: Path) -> None:
    ws = open_workspace(project_root)
    a = write_event(
        ws, TimelineEvent.create(task="a", summary="a", files=["foo.py"])
    )
    b = write_event(
        ws, TimelineEvent.create(task="b", summary="b", files=["foo.py", "bar.py"])
    )
    idx = json.loads((ws.nwt_dir / "indices" / "files.json").read_text())
    assert idx["foo.py"] == [a.id, b.id]
    assert idx["bar.py"] == [b.id]


def test_atomic_write_survives_existing_files(project_root: Path) -> None:
    from nwt.storage.atomic import write_text_atomic

    p = project_root / "thing.json"
    p.write_text('{"old": true}', encoding="utf-8")
    write_text_atomic(p, '{"new": true}\n')
    assert json.loads(p.read_text(encoding="utf-8")) == {"new": True}


def test_read_all_events_in_id_order(project_root: Path) -> None:
    ws = open_workspace(project_root)
    write_event(ws, TimelineEvent.create(task="a", summary="a"))
    write_event(ws, TimelineEvent.create(task="b", summary="b"))
    events = read_all_events(ws)
    assert [e.task for e in events] == ["a", "b"]
    assert events[0].id < events[1].id


# --- IndexStore (nwt.storage.indices) ------------------------------------------


def test_index_store_lookup(project_root: Path) -> None:
    from nwt.storage.indices import IndexStore

    ws = open_workspace(project_root)
    a = write_event(ws, TimelineEvent.create(task="a", summary="a",
                                             files=["foo.py"], tags=["red"]))
    b = write_event(ws, TimelineEvent.create(task="b", summary="b", tags=["red"]))
    store = IndexStore(ws)
    assert store.by_file("foo.py") == [a.id]
    assert store.by_tag("red") == [a.id, b.id]


def test_index_store_self_heals_corruption(project_root: Path) -> None:
    from nwt.storage.indices import IndexStore

    ws = open_workspace(project_root)
    a = write_event(ws, TimelineEvent.create(task="a", summary="a", files=["foo.py"]))
    (ws.indices_dir / "files.json").write_text("{corrupt!", encoding="utf-8")

    # Reading through the store rebuilds instead of crashing...
    assert IndexStore(ws).by_file("foo.py") == [a.id]
    # ...and the write path survives a corrupt index too (it used to
    # raise JSONDecodeError while the read path tolerated it).
    b = write_event(ws, TimelineEvent.create(task="b", summary="b", files=["foo.py"]))
    assert IndexStore(ws).by_file("foo.py") == [a.id, b.id]


def test_index_wrong_value_types_self_heal(project_root: Path) -> None:
    # {"a.py": 1} used to wedge the write path with a TypeError and
    # {"a.py": "000003"} with an AttributeError; both must rebuild.
    from nwt.storage.indices import IndexStore

    ws = open_workspace(project_root)
    a = write_event(ws, TimelineEvent.create(
        task="a", summary="a", files=["foo.py"], tags=["red"]))
    (ws.indices_dir / "files.json").write_text('{"foo.py": 1}', encoding="utf-8")
    b = write_event(ws, TimelineEvent.create(
        task="b", summary="b", files=["foo.py"], tags=["red"]))
    (ws.indices_dir / "tags.json").write_text('{"red": "000001"}', encoding="utf-8")
    write_event(ws, TimelineEvent.create(
        task="c", summary="c", files=["foo.py"], tags=["red"]))
    assert IndexStore(ws).by_file("foo.py") == [a.id, b.id, "000003"]
    assert len(IndexStore(ws).by_tag("red")) == 3


def test_index_tracks_rewrites(project_root: Path) -> None:
    from nwt.storage.indices import IndexStore

    ws = open_workspace(project_root)
    ev = TimelineEvent.create(task="a", summary="a", files=["old.py"])
    write_event(ws, ev)
    ev.files = ["new.py"]
    write_event(ws, ev)  # same id, new files — old key must disappear
    store = IndexStore(ws)
    assert store.by_file("old.py") == []
    assert store.by_file("new.py") == [ev.id]


def test_counter_self_heals_behind_value(project_root: Path) -> None:
    # Simulate a counter that fell behind the timeline (restored backup,
    # torn compact): allocation must skip existing files, not overwrite.
    ws = open_workspace(project_root)
    first = write_event(ws, TimelineEvent.create(task="a", summary="a"))
    reset_counter(ws, 1)  # counter now points at an id that exists
    second = write_event(ws, TimelineEvent.create(task="b", summary="b"))
    assert second.id != first.id
    assert first.task == read_event(ws, first.id).task  # not overwritten


def test_reset_counter_validates(project_root: Path) -> None:
    ws = open_workspace(project_root)
    with pytest.raises(ValidationError):
        reset_counter(ws, 0)


# --- adversarial round: corrupt canonical data ---------------------------------


def test_corrupt_event_file_raises_typed_error(project_root: Path) -> None:
    from nwt.core.errors import CorruptEventError

    ws = open_workspace(project_root)
    write_event(ws, TimelineEvent.create(task="a", summary="a"))
    (ws.timeline_dir / "000001.json").write_text("{trunc", encoding="utf-8")
    with pytest.raises(CorruptEventError, match="corrupt event file"):
        read_all_events(ws)
    with pytest.raises(CorruptEventError):
        read_event(ws, "000001")


def test_compact_survives_corrupt_relations(project_root: Path) -> None:
    # A malformed relations file used to crash compact *after* it had
    # deleted the old events, leaving a half-rewritten workspace.
    _seed_compact_data(project_root)
    (project_root / ".nwt" / "relations" / "000004.json").write_text(
        "{corrupt", encoding="utf-8"
    )
    result = compact_events(root=project_root, min_group_size=3)
    assert result["compacted_count"] == 3
    assert len(read_all_events(open_workspace(project_root))) == 3
    import json as _json

    assert _json.loads((project_root / ".nwt" / ".counter.json").read_text()) == {"next": 4}


def test_counter_out_of_range_value_heals(project_root: Path) -> None:
    ws = open_workspace(project_root)
    first = write_event(ws, TimelineEvent.create(task="a", summary="a"))
    ws.counter_file.write_text('{"next": 0}', encoding="utf-8")
    second = write_event(ws, TimelineEvent.create(task="b", summary="b"))
    assert second.id != first.id  # healed (id 1 taken -> 2), no crash


def test_corrupt_event_cli_reports_cleanly(project_root: Path) -> None:
    # Round-2 red team: git-hook-status used to be the one command that
    # still crashed on a corrupt event file.
    import subprocess
    import sys

    ws = open_workspace(project_root)
    write_event(ws, TimelineEvent.create(task="a", summary="a"))
    (ws.timeline_dir / "000001.json").write_text("{trunc", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "nwt.cli.main", "--root", str(project_root),
         "git-hook-status"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "error: corrupt event file" in r.stderr
    assert "Traceback" not in r.stderr


def _seed_compact_data(root) -> None:
    from nwt.timeline import engine as timeline

    timeline.create_event(task="t1", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t2", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t3", summary="s", tags=["x"], root=root)
    timeline.create_event(task="t4", summary="s", tags=["y"], root=root)
    timeline.create_event(task="t5", summary="s", tags=["x"], root=root)
