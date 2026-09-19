"""Secondary search indices (``files.json``, ``tags.json``).

This module is the single owner of index layout, atomicity, and repair.
Other modules go through :class:`IndexStore` and never touch
``.nwt/indices/`` themselves. The indices are derived, rebuildable data:
a corrupt index is repaired from the canonical event files on the next
read or write, never treated as data loss.

Every mutation (and query) runs under an exclusive cross-process lock
on ``.nwt/indices/.lock``, so concurrent ``nwt log`` processes cannot
crash on a mid-rewrite index or silently lose entries.
"""

from __future__ import annotations

import json
from pathlib import Path

from nwt.core.event import TimelineEvent
from nwt.core.lockfile import exclusive_lock
from nwt.storage.atomic import write_text_atomic
from nwt.storage.layout import Workspace
from nwt.storage.reader import read_all_events


class IndexStore:
    """Read/update/rebuild the ``files`` and ``tags`` indices."""

    def __init__(self, ws: Workspace) -> None:
        self._ws = ws

    # --- paths ----------------------------------------------------------------

    @property
    def files_path(self) -> Path:
        return self._ws.indices_dir / "files.json"

    @property
    def tags_path(self) -> Path:
        return self._ws.indices_dir / "tags.json"

    @property
    def lock_path(self) -> Path:
        return self._ws.indices_dir / ".lock"

    # --- queries ----------------------------------------------------------------

    def by_file(self, path: str) -> list[str]:
        """Event ids whose ``files`` list contains ``path`` (exact key).

        Falls back to a case-insensitive key match, so a Windows-style
        ``A/B.PY`` query still finds ``a/b.py`` on any platform.
        """
        with exclusive_lock(self.lock_path):
            mapping = self._load_unlocked(self.files_path)
        ids = mapping.get(path)
        if ids is None:
            lowered = path.lower()
            ids = next(
                (v for k, v in mapping.items() if k.lower() == lowered), None
            )
        return list(ids or ())

    def by_tag(self, tag: str) -> list[str]:
        """Event ids carrying ``tag`` (exact key; tags are lowercased)."""
        with exclusive_lock(self.lock_path):
            mapping = self._load_unlocked(self.tags_path)
        return list(mapping.get(tag, ()))

    # --- mutation -----------------------------------------------------------------

    def update(self, event: TimelineEvent) -> None:
        """Fold ``event`` into both indices.

        Idempotent per event id: stale entries for the same id are
        removed first so rewritten events (renames, new tag sets) are
        reflected exactly.
        """
        with exclusive_lock(self.lock_path):
            self._ws.indices_dir.mkdir(parents=True, exist_ok=True)
            files = self._load_unlocked(self.files_path)
            tags = self._load_unlocked(self.tags_path)

            for mapping in (files, tags):
                for key in list(mapping):
                    ids = mapping[key]
                    if event.id in ids:
                        ids.remove(event.id)
                        if not ids:
                            del mapping[key]

            for f in event.files:
                files.setdefault(f, []).append(event.id)
            for t in event.tags:
                tags.setdefault(t, []).append(event.id)

            self._dump(self.files_path, files)
            self._dump(self.tags_path, tags)

    def rebuild(self) -> None:
        """Recompute both indices from the canonical event files. Idempotent."""
        with exclusive_lock(self.lock_path):
            self._rebuild_unlocked()

    # --- internals (callers hold the lock) ----------------------------------------

    def _rebuild_unlocked(self) -> None:
        idx = self._ws.indices_dir
        if idx.exists():
            for child in idx.glob("*.json"):
                child.unlink()
        idx.mkdir(parents=True, exist_ok=True)

        files: dict[str, list[str]] = {}
        tags: dict[str, list[str]] = {}
        for ev in read_all_events(self._ws):
            for f in ev.files:
                files.setdefault(f, []).append(ev.id)
            for t in ev.tags:
                tags.setdefault(t, []).append(ev.id)

        self._dump(self.files_path, files)
        self._dump(self.tags_path, tags)

    def _load_unlocked(self, path: Path) -> dict:
        """Load one index file, self-healing corruption via rebuild.

        Corruption means unparsable JSON *or* the right shape with wrong
        value types (``{"a.py": 1}`` used to wedge the write path with a
        TypeError) — both are rebuilt from the canonical events.
        """
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            self._rebuild_unlocked()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            if not isinstance(data, dict):
                return {}

        clean: dict[str, list[str]] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, list) and all(
                isinstance(i, str) for i in value
            ):
                clean[key] = value
        if len(clean) != len(data):
            # Wrong-typed entries: rebuild so the index reflects reality.
            self._rebuild_unlocked()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            if isinstance(data, dict):
                clean = {
                    k: v for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, list)
                    and all(isinstance(i, str) for i in v)
                }
        return clean

    def _dump(self, path: Path, data: dict) -> None:
        write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
