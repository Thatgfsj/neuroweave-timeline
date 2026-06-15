"""Relationship types for the Evolution Graph.

Linear history uses the ``parent`` field on each event. Everything richer
(causality, fixes, replacements) is recorded as a typed edge in
``.nwt/relations/`` via :func:`nwt.timeline.engine.link`.
"""

from __future__ import annotations

from enum import Enum


class Relation(str, Enum):
    """Edge type connecting two timeline events.

    Stored as the lowercase string value in JSON, e.g. ``"fixes"``.
    """

    FOLLOWS = "follows"
    CAUSED_BY = "caused_by"
    FIXES = "fixes"
    REPLACES = "replaces"
    EXTENDS = "extends"

    @classmethod
    def parse(cls, value: object) -> "Relation":
        """Coerce a user-supplied string into a Relation.

        Accepts case-insensitive names and common aliases (``"cause"`` ->
        ``caused_by``).
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"relation must be a string, got {type(value).__name__}")

        s = value.strip().lower()
        aliases = {
            "cause": cls.CAUSED_BY,
            "caused": cls.CAUSED_BY,
            "follow": cls.FOLLOWS,
            "fix": cls.FIXES,
            "replace": cls.REPLACES,
            "extend": cls.EXTENDS,
        }
        if s in aliases:
            return aliases[s]
        for member in cls:
            if member.value == s:
                return member
        valid = ", ".join(repr(m.value) for m in cls)
        raise ValueError(f"unknown relation {value!r}. Valid: {valid}")
