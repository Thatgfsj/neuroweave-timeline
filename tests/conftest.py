"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from nwt.storage.layout import init_workspace


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A fresh temporary project root with an initialized NWT workspace."""
    root = tmp_path / "proj"
    root.mkdir()
    init_workspace(root, project_name="test-project")
    return root
