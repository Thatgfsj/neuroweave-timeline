"""Layout of the on-disk workspace.

All paths are resolved relative to the project root — the directory in
which the user ran ``nwt init``. Every helper in this module is a pure
function over a :class:`Path`, so the same layout can be exercised from
tests with a temporary directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nwt.core.time import utc_now_iso

#: Name of the directory holding all NWT state for a project.
WORKSPACE_DIR = ".nwt"

#: Subdirectory holding event files (one JSON per event).
TIMELINE_DIR = "timeline"

#: Subdirectory holding non-linear relation edges.
RELATIONS_DIR = "relations"

#: Subdirectory reserved for v0.2 snapshots. Created on init for forward
#: compatibility; used by `nwt compact` for pre-rewrite backups.
SNAPSHOTS_DIR = "snapshots"

#: Subdirectory holding derived search indices. Owned by
#: :mod:`nwt.storage.indices`; safe to delete at any time.
INDICES_DIR = "indices"


@dataclass(frozen=True)
class Workspace:
    """Resolved paths inside a project's ``.nwt/`` directory.

    Use :func:`open_workspace` to construct one; it raises if the workspace
    does not exist (callers that want to create one should use
    :func:`init_workspace` instead).
    """

    root: Path  # the project root (parent of .nwt/)

    @property
    def nwt_dir(self) -> Path:
        return self.root / WORKSPACE_DIR

    @property
    def timeline_dir(self) -> Path:
        return self.nwt_dir / TIMELINE_DIR

    @property
    def relations_dir(self) -> Path:
        return self.nwt_dir / RELATIONS_DIR

    @property
    def snapshots_dir(self) -> Path:
        return self.nwt_dir / SNAPSHOTS_DIR

    @property
    def indices_dir(self) -> Path:
        return self.nwt_dir / INDICES_DIR

    @property
    def metadata_file(self) -> Path:
        return self.nwt_dir / "metadata.json"

    @property
    def counter_file(self) -> Path:
        return self.nwt_dir / ".counter.json"

    def read_project_name(self) -> str | None:
        """Read the project name from metadata.json (None if unreadable)."""
        import json

        try:
            meta = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        name = meta.get("project_name")
        return name if isinstance(name, str) else None

    def event_file(self, event_id: str) -> Path:
        """Return the canonical path for an event file."""
        return self.timeline_dir / f"{event_id}.json"

    def relation_file(self, source_id: str) -> Path:
        """Return the path of the file holding relations *out of* ``source_id``.

        Edges are stored as one file per source node, keeping each write
        small and avoiding the "rewrite the world on every link" problem.
        """
        return self.relations_dir / f"{source_id}.json"


def is_initialized(root: Path) -> bool:
    """True if ``root`` already contains a usable NWT workspace."""
    return (root / WORKSPACE_DIR / "metadata.json").is_file()


def open_workspace(root: Path) -> Workspace:
    """Open an existing workspace, raising if it isn't initialized.

    ``root`` should be the project root, not the ``.nwt/`` directory itself.
    """
    from nwt.core.errors import NotInitializedError

    if not is_initialized(root):
        raise NotInitializedError(
            f"no NWT workspace found at {root} (run `nwt init` first)"
        )
    return Workspace(root=root.resolve())


def init_workspace(root: Path, *, project_name: str | None = None) -> Workspace:
    """Create a fresh ``.nwt/`` directory tree.

    Idempotent semantics: refuses to clobber an existing workspace. Use
    ``nwt reinit`` (not implemented in v0.1) to override.
    """
    from nwt.core.errors import AlreadyInitializedError

    root = root.resolve()
    if is_initialized(root):
        raise AlreadyInitializedError(
            f"workspace already exists at {root / WORKSPACE_DIR}"
        )

    ws = Workspace(root=root)
    ws.nwt_dir.mkdir(parents=True, exist_ok=True)
    ws.timeline_dir.mkdir(parents=True, exist_ok=True)
    ws.relations_dir.mkdir(parents=True, exist_ok=True)
    ws.snapshots_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "project_name": project_name or root.name,
        "created_at": utc_now_iso(),
        "format": "nwt/0.2",
    }
    ws.metadata_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # counter file starts at 1
    ws.counter_file.write_text(json.dumps({"next": 1}), encoding="utf-8")

    return ws
