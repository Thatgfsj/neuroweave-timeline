"""Git integration: grow the timeline from ``git commit``.

``nwt install-git-hook`` writes a small managed block into
``.git/hooks/post-commit``; on every commit the hook calls
``nwt log-commit``, which turns the commit into a timeline event:

* ``task`` / ``summary`` come from the commit subject,
* ``reason`` comes from a ``Reason:`` line in the commit body,
* ``files`` come from the commit's changed paths,
* the event auto-chains onto the latest event and carries the full
  SHA in ``meta`` for idempotence (a commit is logged at most once).

With ``--strict`` the hook refuses to log commits without a ``Reason:``
line (exiting non-zero so the omission is visible). With
``--ai-command "claude -p"`` the hook asks an external model to fill in
a missing reason.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from nwt.core.errors import NWTError
from nwt.core.event import TimelineEvent
from nwt.storage.atomic import write_text_atomic
from nwt.storage.layout import Workspace, is_initialized, open_workspace
from nwt.storage.reader import read_all_events
from nwt.timeline import engine as timeline

MARKER_BEGIN = "# >>> nwt post-commit hook >>>"
MARKER_END = "# <<< nwt post-commit hook <<<"

_HOOK_TEMPLATE = """#!/bin/sh
{begin}
# Installed by `nwt install-git-hook`. Remove this block to uninstall.
nwt --root "$(git rev-parse --show-toplevel)" log-commit{flags} || exit 1
{end}
"""

_REASON_RE = re.compile(r"^\s*reason\s*:\s*(.+)$", re.IGNORECASE)


# --- install / status --------------------------------------------------------


def _resolve_hooks_dir(root: Path) -> Path:
    """Locate the hooks directory, including git worktrees.

    A plain repo has ``.git/hooks``. A worktree has ``.git`` as a *file*
    (``gitdir: <path>``); hooks then live in the common dir's ``hooks``
    (``<gitdir>/commondir`` points at it).
    """
    git_dir = root / ".git"
    if git_dir.is_dir():
        return git_dir / "hooks"
    if git_dir.is_file():
        first_line = git_dir.read_text(encoding="utf-8", errors="replace").strip()
        if first_line.lower().startswith("gitdir:"):
            target = first_line.split(":", 1)[1].strip()
            gitdir = Path(target)
            if not gitdir.is_absolute():
                gitdir = (root / gitdir).resolve()
            commondir_file = gitdir / "commondir"
            if commondir_file.is_file():
                common = Path(commondir_file.read_text(encoding="utf-8").strip())
                if not common.is_absolute():
                    common = (gitdir / common).resolve()
                return common / "hooks"
            return gitdir / "hooks"
    raise NWTError(
        f"not a git repository: {root} (git hooks live in .git/hooks — run `git init` first)"
    )


def install_hook(root: str | Path, *, strict: bool = False, ai_command: str | None = None) -> Path:
    """Write the NWT-managed post-commit hook into ``root``'s git repo.

    Refuses to touch a post-commit hook that exists but was not installed
    by NWT (no marker); an existing NWT hook is updated in place, which is
    how you change ``--strict`` / ``--ai-command`` later. The workspace
    must be initialized first — a hook that fires without one would fail
    on every commit.
    """
    root = Path(root)
    hooks_dir = _resolve_hooks_dir(root)

    if not is_initialized(root):
        raise NWTError(
            f"no NWT workspace at {root} (run `nwt init` before installing the hook, "
            "or the hook will fail on every commit)"
        )

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-commit"

    if hook_path.is_file():
        existing = hook_path.read_text(encoding="utf-8", errors="replace")
        if MARKER_BEGIN not in existing:
            raise NWTError(
                "a post-commit hook already exists and is not NWT-managed; "
                "merge it manually or remove it first"
            )

    flags = " --strict" if strict else ""
    if ai_command:
        # The command is embedded in a double-quoted sh string; reject
        # anything that could break out of it (quotes, expansions,
        # backticks, semicolons) rather than trying to escape sh safely.
        bad = [ch for ch in '"`$;&|<>' if ch in ai_command]
        if bad:
            raise NWTError(
                f"--ai-command must not contain {', '.join(map(repr, bad))} "
                "(it is embedded in the hook script verbatim)"
            )
        flags += f' --ai-command "{ai_command}"'
    block = _HOOK_TEMPLATE.format(
        begin=MARKER_BEGIN, flags=flags, end=MARKER_END
    )
    write_text_atomic(hook_path, block)
    try:
        os.chmod(hook_path, 0o755)
    except OSError:
        pass  # exec bits are best-effort (no-op on Windows)
    return hook_path


def hook_status(root: str | Path) -> dict:
    """Report whether the NWT post-commit hook is installed and its flags."""
    root = Path(root)
    try:
        hook_path = _resolve_hooks_dir(root) / "post-commit"
    except NWTError:
        hook_path = root / ".git" / "hooks" / "post-commit"

    installed = strict = False
    ai_command: str | None = None
    if hook_path.is_file():
        text = hook_path.read_text(encoding="utf-8", errors="replace")
        if MARKER_BEGIN in text:
            installed = True
            strict = "--strict" in text
            match = re.search(r'--ai-command\s+"([^"]+)"', text)
            ai_command = match.group(1) if match else None

    status: dict = {
        "hook_installed": installed,
        "hook_path": str(hook_path),
        "strict": strict,
        "ai_command": ai_command,
        "workspace_initialized": is_initialized(root),
        "latest_event": None,
    }
    if status["workspace_initialized"]:
        events = read_all_events(open_workspace(root))
        if events:
            last = max(events, key=lambda e: int(e.id))
            status["latest_event"] = {
                "id": last.id,
                "task": last.task,
                "tags": last.tags,
            }
    return status


# --- log-commit --------------------------------------------------------------


def log_commit(
    root: str | Path,
    *,
    strict: bool = False,
    ai_command: str | None = None,
) -> TimelineEvent | None:
    """Log the repository's latest commit as a timeline event.

    Returns ``None`` when the commit is already logged (the hook fires on
    every commit; this keeps manual re-runs and hook replays idempotent).
    Raises :class:`NWTError` in strict mode when the commit carries no
    ``Reason:`` line.
    """
    root = Path(root)
    ws: Workspace = open_workspace(root)

    sha, subject, body, files = _read_last_commit(root)
    if not sha:
        raise NWTError("no commits found in this repository")

    for ev in read_all_events(ws):
        if ev.meta.get("sha") == sha:
            return None  # already logged — idempotent

    reason = _extract_reason(body)
    if reason is None and ai_command:
        reason = _ask_ai(ai_command, subject, body)
    if reason is None and strict:
        raise NWTError(
            f"commit {sha[:7]} has no 'Reason:' line (--strict refuses to log it); "
            "amend the commit or drop --strict"
        )

    subject = subject.strip() or "(no commit message)"
    ev = timeline.create_event(
        task=subject.splitlines()[0][:200],
        summary=subject,
        reason=reason,
        files=files,
        tags=["commit"],
        meta={"sha": sha},
        root=root,
    )
    return ev


# --- helpers -----------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise NWTError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _read_last_commit(root: Path) -> tuple[str, str, str, list[str]]:
    """Return ``(sha, subject, body, changed_files)`` for HEAD.

    Merge commits get their changed files from ``diff-tree -m`` (a plain
    ``git show --name-only`` reports nothing for them, which would
    silently drop every file the branch touched). Files are deduped in
    first-seen order across parents.
    """
    header = _git(root, "show", "-1", "--no-patch", "--pretty=format:%H%x1e%s%x1e%b")
    parts = header.split("\x1e")
    if len(parts) < 3:
        raise NWTError("could not parse the last commit (unexpected git output)")
    sha, subject, body = parts[0].strip(), parts[1], parts[2]

    # rev-list (not rev-parse, whose --parents output is unreliable
    # across git versions) tells us the parent count: >2 items means
    # HEAD is a merge.
    parents = _git(root, "rev-list", "--parents", "-1", "HEAD").split()
    if len(parents) > 2:  # HEAD + 2+ parents → merge commit
        file_out = _git(
            root, "diff-tree", "-m", "--root", "--no-commit-id",
            "--name-only", "-r", "HEAD",
        )
    else:
        file_out = _git(root, "show", "-1", "--name-only", "--pretty=format:")

    files: list[str] = []
    for line in file_out.splitlines():
        line = line.strip()
        if line and line not in files:
            files.append(line)
    return sha, subject, body, files


def _extract_reason(body: str) -> str | None:
    for line in body.splitlines():
        match = _REASON_RE.match(line)
        if match:
            return match.group(1).strip()
    return None


def _ask_ai(ai_command: str, subject: str, body: str) -> str | None:
    """Ask an external model for a missing reason; never raises."""
    prompt = (
        "Write one concise sentence explaining WHY this commit was made. "
        "Reply with the sentence only.\n\n"
        f"Subject: {subject}\nBody:\n{body}"
    )
    try:
        result = subprocess.run(
            shlex.split(ai_command) + [prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode == 0:
            line = next((l.strip() for l in result.stdout.splitlines() if l.strip()), "")
            if line:
                return line[:500]
        print(f"nwt: ai-command failed, logging without reason: {result.stderr.strip()}",
              flush=True)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        print(f"nwt: ai-command failed, logging without reason: {e}", flush=True)
    return None
