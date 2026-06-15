"""Tests for the TimelineEvent model and (de)serialization."""

from __future__ import annotations

import pytest

from nwt.core.errors import ValidationError
from nwt.core.event import TimelineEvent


def test_to_dict_has_required_fields_first() -> None:
    ev = TimelineEvent(
        id="000001",
        timestamp="2026-06-15T10:00:00Z",
        task="Initial scaffold",
        summary="Set up the project",
        reason="Started v0.1",
        files=["README.md"],
        tags=["setup"],
        parent=None,
    )
    d = ev.to_dict()
    # Required fields come first, optional fields are present only when set.
    assert list(d.keys())[:4] == ["id", "timestamp", "task", "summary"]
    assert d["reason"] == "Started v0.1"
    assert d["files"] == ["README.md"]
    assert d["tags"] == ["setup"]
    assert "parent" not in d


def test_from_dict_roundtrip() -> None:
    original = TimelineEvent(
        id="000007",
        timestamp="2026-06-15T10:00:00Z",
        task="Add activation",
        summary="Spread activation through graph",
        reason="Retrieval was slow",
        files=["activation.py", "retriever.py"],
        tags=["memory", "optimization"],
    )
    raw = original.to_json()
    restored = TimelineEvent.from_json(raw)
    assert restored == original


def test_from_dict_normalizes_tag_case() -> None:
    raw = (
        '{'
        '"id":"000001",'
        '"timestamp":"2026-06-15T10:00:00Z",'
        '"task":"t",'
        '"summary":"s",'
        '"tags":["Memory","Optimization","memory"]'
        '}'
    )
    ev = TimelineEvent.from_json(raw)
    # Lowercased and de-duplicated, original order preserved.
    assert ev.tags == ["memory", "optimization"]


def test_from_dict_rejects_unknown_field() -> None:
    bad = {
        "id": "000001",
        "timestamp": "2026-06-15T10:00:00Z",
        "task": "x",
        "summary": "y",
        "sneaky": "no",
    }
    with pytest.raises(ValidationError, match="unknown field"):
        TimelineEvent.from_dict(bad)


def test_from_dict_rejects_missing_field() -> None:
    bad = {
        "id": "000001",
        "timestamp": "2026-06-15T10:00:00Z",
        "task": "x",
        # no summary
    }
    with pytest.raises(ValidationError, match="summary"):
        TimelineEvent.from_dict(bad)


def test_from_dict_rejects_bad_id() -> None:
    bad = {
        "id": "abc",
        "timestamp": "2026-06-15T10:00:00Z",
        "task": "x",
        "summary": "y",
    }
    with pytest.raises(ValidationError, match="invalid event id"):
        TimelineEvent.from_dict(bad)


def test_from_dict_rejects_bad_timestamp() -> None:
    bad = {
        "id": "000001",
        "timestamp": "yesterday",
        "task": "x",
        "summary": "y",
    }
    with pytest.raises(ValidationError, match="invalid timestamp"):
        TimelineEvent.from_dict(bad)


def test_short_id_strips_zeros() -> None:
    ev = TimelineEvent(
        id="000042", timestamp="2026-06-15T10:00:00Z", task="x", summary="y"
    )
    assert ev.short_id() == "42"


def test_create_assigns_id_and_timestamp() -> None:
    ev = TimelineEvent.create(task="t", summary="s")
    assert ev.id == ""  # engine will allocate; factory leaves it empty
    assert ev.timestamp  # populated
