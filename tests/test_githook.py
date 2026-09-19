"""Tests for the git integration (install-git-hook / log-commit / status)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nwt import githook
from nwt.core.errors import NWTError
from nwt.storage.layout import init_workspace, open_workspace
from nwt.storage.reader import read_all_events
from nwt.timeline import engine as timeline

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")

REPO = Path(__file__).resolve().parents[1]


def _run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def _out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _find_posix_shell() -> str | None:
    """Locate a Git-for-Windows shell for executing the hook script.

    ``shutil.which("sh"/"bash")`` on Windows can return the WSL
    ``system32\\bash.EXE``, which cannot run Windows-path scripts.
    Prefer the shell shipped next to git itself.
    """
    git_exe = shutil.which("git")
    candidates: list[Path] = []
    if git_exe:
        git_dir = Path(git_exe).resolve().parent  # .../cmd or .../bin
        candidates += [
            git_dir.parent / "bin" / "bash.exe",
            git_dir.parent / "usr" / "bin" / "sh.exe",
            git_dir / "bash.exe",
        ]
    which_sh = shutil.which("sh") or shutil.which("bash")
    if which_sh and "system32" not in which_sh.lower():
        candidates.append(Path(which_sh))
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "test@example.com")
    _run(repo, "config", "user.name", "Test")
    init_workspace(repo, project_name="hooked")
    (repo / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    _run(repo, "add", "hello.py")
    _run(repo, "commit", "-m", "Add hello module", "-m", "Reason: demo needs a greeter")
    return repo


def test_log_commit_records_reason_and_sha(git_repo: Path) -> None:
    ev = githook.log_commit(git_repo)
    assert ev is not None
    assert ev.task == "Add hello module"
    assert ev.reason == "demo needs a greeter"
    assert ev.tags == ["commit"]
    assert ev.files == ["hello.py"]
    assert len(ev.meta["sha"]) == 40


def test_log_commit_is_idempotent(git_repo: Path) -> None:
    assert githook.log_commit(git_repo) is not None
    assert githook.log_commit(git_repo) is None
    assert len(read_all_events(open_workspace(git_repo))) == 1


def test_log_commit_auto_chains(git_repo: Path) -> None:
    timeline.create_event(task="seed", summary="seed", root=git_repo)
    ev = githook.log_commit(git_repo)
    assert ev is not None
    assert ev.parent == "000001"


def test_strict_refuses_missing_reason(git_repo: Path) -> None:
    (git_repo / "second.txt").write_text("x\n", encoding="utf-8")
    _run(git_repo, "add", "second.txt")
    _run(git_repo, "commit", "-m", "No reason given")
    with pytest.raises(NWTError, match="Reason"):
        githook.log_commit(git_repo, strict=True)
    # Non-strict still logs it (without a reason).
    ev = githook.log_commit(git_repo)
    assert ev is not None
    assert ev.reason is None


def test_install_and_status(git_repo: Path) -> None:
    hook_path = githook.install_hook(git_repo, strict=True, ai_command="claude -p")
    text = hook_path.read_text(encoding="utf-8")
    assert githook.MARKER_BEGIN in text
    assert "--strict" in text
    # --root (group flag) must precede the subcommand.
    assert text.index("--root") < text.index("log-commit")

    status = githook.hook_status(git_repo)
    assert status["hook_installed"] is True
    assert status["strict"] is True
    assert status["ai_command"] == "claude -p"

    # Re-installing updates the managed block (flag change workflow).
    githook.install_hook(git_repo)
    status = githook.hook_status(git_repo)
    assert status["strict"] is False
    assert status["ai_command"] is None


def test_install_refuses_foreign_hook(git_repo: Path) -> None:
    hook_path = git_repo / ".git" / "hooks" / "post-commit"
    hook_path.parent.mkdir(exist_ok=True)
    hook_path.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    with pytest.raises(NWTError, match="not NWT-managed"):
        githook.install_hook(git_repo)


def test_install_requires_git_repo(tmp_path: Path) -> None:
    plain = tmp_path / "not_a_repo"
    plain.mkdir()
    with pytest.raises(NWTError, match="not a git repository"):
        githook.install_hook(plain)


def test_log_commit_requires_workspace(git_repo: Path) -> None:
    import shutil

    shutil.rmtree(git_repo / ".nwt")
    with pytest.raises(NWTError, match="nwt init"):
        githook.log_commit(git_repo)


# --- adversarial-round regressions ----------------------------------------------


def test_hook_script_runs_end_to_end(git_repo: Path) -> None:
    """Execute the real installed hook through a POSIX shell.

    Regression: the template once read `nwt log-commit --root ...` — an
    illegal argument order (root is a group-level flag), so every real
    commit failed with "No such option: --root" and no event was ever
    recorded. Only executing the script catches that class of bug.
    """
    sh = _find_posix_shell()
    if not sh:
        pytest.skip("no POSIX shell available")

    # Stub `nwt` on PATH *before* committing, so the hook that git
    # fires for real uses this repo's code, not whatever nwt happens
    # to be installed on the machine.
    stub_bin = git_repo / ".stub-bin"
    stub_bin.mkdir()
    stub = stub_bin / "nwt"
    python = str(sys.executable).replace("\\", "/")
    repo = str(REPO).replace("\\", "/")
    stub.write_text(f"#!/bin/sh\nexec '{python}' -m nwt.cli.main \"$@\"\n", encoding="utf-8")
    os.chmod(stub, 0o755)
    env = {**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}"}

    hook_path = githook.install_hook(git_repo)

    (git_repo / "second.py").write_text("x = 1\n", encoding="utf-8")
    _run(git_repo, "add", "second.py")
    commit_out = subprocess.run(
        ["git", "-C", str(git_repo), "commit", "-m", "Add second", "-m", "Reason: e2e check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    assert commit_out.returncode == 0, commit_out.stderr
    # The real post-commit hook ran during the commit and logged the
    # event (git may forward hook output on either stream).
    combined = commit_out.stdout + commit_out.stderr
    assert "logged [1] Add second" in combined, combined
    events = read_all_events(open_workspace(git_repo))
    assert any(
        e.task == "Add second" and e.reason == "e2e check" and e.files == ["second.py"]
        for e in events
    )

    # Running the hook again is idempotent.
    result = subprocess.run(
        [sh, str(hook_path)], cwd=git_repo, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert "already logged" in result.stdout


def test_log_commit_merges_record_files(git_repo: Path) -> None:
    branch = _out(git_repo, "rev-parse", "--abbrev-ref", "HEAD")
    _run(git_repo, "checkout", "-b", "feature")
    (git_repo / "feat.txt").write_text("f\n", encoding="utf-8")
    _run(git_repo, "add", "feat.txt")
    _run(git_repo, "commit", "-m", "Feature work", "-m", "Reason: feature")
    _run(git_repo, "checkout", branch)
    _run(git_repo, "merge", "--no-ff", "feature", "-m", "Merge feature")

    ev = githook.log_commit(git_repo)
    assert ev is not None
    # A merge commit used to record zero files (git show --name-only is
    # empty for merges), silently dropping everything the branch did.
    assert "feat.txt" in ev.files


def test_log_commit_unicode_filenames(git_repo: Path) -> None:
    (git_repo / "界面.txt").write_text("x\n", encoding="utf-8")
    _run(git_repo, "add", "界面.txt")
    _run(git_repo, "commit", "-m", "Add ui", "-m", "Reason: ui")
    ev = githook.log_commit(git_repo)
    assert ev is not None
    # core.quotepath escaping used to store octal mojibake, which made
    # the file unfindable via search-file.
    assert ev.files == ["界面.txt"]


def test_install_requires_initialized_workspace(tmp_path: Path) -> None:
    repo = tmp_path / "raw"
    repo.mkdir()
    _run(repo, "init")
    with pytest.raises(NWTError, match="nwt init"):
        githook.install_hook(repo)


def test_resolve_hooks_dir_supports_worktrees(tmp_path: Path) -> None:
    main_git = tmp_path / "main" / ".git"
    (main_git / "hooks").mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    gitdir = worktree / ".git"
    gitdir.write_text(f"gitdir: {main_git / 'worktrees' / 'wt'}\n", encoding="utf-8")
    (main_git / "worktrees" / "wt").mkdir(parents=True)
    (main_git / "worktrees" / "wt" / "commondir").write_text("../..\n", encoding="utf-8")

    assert githook._resolve_hooks_dir(worktree) == main_git / "hooks"


def test_install_rejects_dangerous_ai_command(git_repo: Path) -> None:
    # The command is embedded verbatim in a double-quoted sh string;
    # shell metacharacters would inject into every commit.
    for evil in ('x"y', "$(echo pwned)", "a; rm -rf /", "x`id`y"):
        with pytest.raises(NWTError, match="must not contain"):
            githook.install_hook(git_repo, ai_command=evil)
