"""End-to-end tests for the Click CLI.

We invoke the CLI as a subprocess so we exercise argument parsing, exit
codes, and the on-disk side effects in one go.

Each test creates its own fresh directory — we do *not* use the
shared ``project_root`` fixture because the CLI tests need to drive
``nwt init`` themselves.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _fresh_root(tmp_path: Path) -> Path:
    p = tmp_path / "cli_proj"
    p.mkdir()
    return p


def _run(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nwt.cli.main", "--root", str(project_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_log_history_show(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    assert _run(project_root, "init", "--name", "demo").returncode == 0

    r = _run(project_root, "log", "Scaffold project", "--reason", "start")
    assert r.returncode == 0, r.stderr
    assert "logged" in r.stdout

    r = _run(
        project_root,
        "log",
        "Add activation",
        "--summary",
        "spread",
        "--reason",
        "retrieval",
        "--files",
        "activation.py",
        "--tags",
        "memory,perf",
        "--parent",
        "1",
    )
    assert r.returncode == 0, r.stderr

    r = _run(project_root, "history")
    assert "Scaffold project" in r.stdout
    assert "Add activation" in r.stdout

    r = _run(project_root, "show", "1")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["task"] == "Scaffold project"


def test_search_and_search_file(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(
        project_root,
        "log",
        "Refactor activation",
        "--summary",
        "vectorize",
        "--files",
        "activation.py",
        "--reason",
        "perf",
        "--tags",
        "refactor",
    )

    r = _run(project_root, "search", "perf")
    assert "Refactor activation" in r.stdout

    r = _run(project_root, "search-file", "activation.py")
    assert "Refactor activation" in r.stdout

    r = _run(project_root, "search-tag", "refactor")
    assert "Refactor activation" in r.stdout


def test_link_and_graph(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(project_root, "log", "A")
    _run(project_root, "log", "B")
    r = _run(project_root, "link", "1", "2", "--relation", "fixes")
    assert r.returncode == 0, r.stderr
    r = _run(project_root, "graph")
    assert "○" in r.stdout
    assert "fixes" in r.stdout


def test_story_and_explain(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init", "--name", "demo")
    _run(project_root, "log", "Project created", "--reason", "kickoff")
    _run(
        project_root,
        "log",
        "Add activation",
        "--summary",
        "spread",
        "--files",
        "activation.py",
        "--reason",
        "retrieval",
        "--parent",
        "1",
    )
    r = _run(project_root, "story")
    assert "demo — evolution summary" in r.stdout
    r = _run(project_root, "explain", "activation.py")
    assert "activation.py" in r.stdout
    assert "created in" in r.stdout
    assert "retrieval" in r.stdout


def test_init_fails_when_already_initialized(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    r = _run(project_root, "init")
    assert r.returncode != 0
    assert "already exists" in r.stderr


def test_log_auto_chains_without_parent(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(project_root, "log", "first")
    _run(project_root, "log", "second")
    r = _run(project_root, "show", "2")
    payload = json.loads(r.stdout)
    assert payload["parent"] == "000001"


def test_log_parent_none_starts_branch(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(project_root, "log", "first")
    _run(project_root, "log", "fork", "--parent", "none")
    r = _run(project_root, "show", "2")
    payload = json.loads(r.stdout)
    assert "parent" not in payload


def test_diff_reversed_fails_cleanly(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(project_root, "log", "one", "--files", "a.py")
    _run(project_root, "log", "two", "--files", "a.py")
    r = _run(project_root, "diff", "2", "1")
    assert r.returncode != 0
    assert "error:" in r.stderr
    assert "Traceback" not in r.stderr

    ok = _run(project_root, "diff", "1", "2")
    assert ok.returncode == 0
    assert "In both (likely modified): a.py" in ok.stdout


def test_diff_rejects_same_event(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    _run(project_root, "log", "one")
    r = _run(project_root, "diff", "1", "1")
    assert r.returncode != 0
    assert "itself" in r.stderr


def test_compact_dry_run_flag(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    for i in range(4):
        _run(project_root, "log", f"t{i}", "--tags", "x")
    r = _run(project_root, "compact", "--dry-run")
    assert r.returncode == 0
    assert "Would compact" in r.stdout
    # Still 4 events on disk afterwards.
    r = _run(project_root, "history")
    assert r.stdout.count("t") >= 4


def test_compact_reports_backup(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    for i in range(4):
        _run(project_root, "log", f"t{i}", "--tags", "x")
    r = _run(project_root, "compact")
    assert r.returncode == 0
    assert "backup:" in r.stdout
    assert "000001.json" in r.stdout or "Compacted" in r.stdout


def test_install_git_hook_and_status(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    (project_root / ".git").mkdir()  # hook installer only needs .git/
    _run(project_root, "init")

    r = _run(project_root, "install-git-hook", "--strict")
    assert r.returncode == 0, r.stderr
    hook = project_root / ".git" / "hooks" / "post-commit"
    assert hook.is_file()
    text = hook.read_text(encoding="utf-8")
    # --root must precede the subcommand (click group option) and the
    # hook must invoke log-commit — the wrong order once disabled the
    # whole auto-grow path.
    assert "--root" in text
    assert "log-commit" in text
    assert text.index("--root") < text.index("log-commit")

    r = _run(project_root, "git-hook-status")
    assert r.returncode == 0
    assert "installed" in r.stdout
    assert "strict: yes" in r.stdout


def test_install_git_hook_requires_repo(tmp_path: Path) -> None:
    project_root = _fresh_root(tmp_path)
    _run(project_root, "init")
    r = _run(project_root, "install-git-hook")
    assert r.returncode != 0
    assert "not a git repository" in r.stderr
