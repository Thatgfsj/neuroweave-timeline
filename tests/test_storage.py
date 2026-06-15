"""Tests for the storage layer (layout, reader, writer, atomic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nwt.core.event import TimelineEvent
from nwt.core.errors import AlreadyInitializedError, EventNotFoundError, NotInitializedError
from nwt.core.ids import ID_WIDTH
from nwt.core.relations import Relation
from nwt.storage.layout import init_workspace, is_initialized, open_workspace
from nwt.storage.reader import read_all_events, read_relations
from nwt.storage.writer import write_event, write_relation


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
