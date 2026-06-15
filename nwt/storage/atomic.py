"""Atomic file writes.

We use a write-temp-then-rename pattern, which on POSIX and on modern
Windows (NTFS) is atomic at the directory-entry level. Readers therefore
either see the old file or the new one — never a half-written one. This
is what makes NWT safe to use from concurrent agents and from manual
edits at the same time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically.

    Creates parent directories as needed. The temp file lives in the same
    directory as the target so the final ``os.replace`` is a single
    directory-entry swap.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if Path(tmp).exists():
            try:
                Path(tmp).unlink()
            except OSError:
                pass
        raise


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if Path(tmp).exists():
            try:
                Path(tmp).unlink()
            except OSError:
                pass
        raise
