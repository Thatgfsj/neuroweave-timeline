"""MCP server exposing NWT as four tools.

The server speaks Model Context Protocol over stdio. Once an agent
connects, it can:

* ``create_event``  — append an event to the timeline
* ``search_history`` — substring search across the timeline
* ``get_project_story`` — return a compressed project story
* ``explain_file`` — explain why a given file exists

Run it with::

    nwt-mcp                 # if installed as a script
    python -m nwt.mcp.server

The server picks up the workspace from the current working directory.
Pass ``NWT_ROOT`` to point at a different project.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from nwt import __version__
from nwt.core.errors import NWTError
from nwt.graph.builder import build_graph
from nwt.graph.lineage import explain_file
from nwt.storage.layout import Workspace, open_workspace
from nwt.timeline import engine as timeline
from nwt.timeline.summary import build_story


def _resolve_root() -> Path:
    """Workspace root: ``$NWT_ROOT`` if set, else the current directory."""
    env = os.environ.get("NWT_ROOT")
    return Path(env) if env else Path.cwd()


def _open_or_error() -> Workspace:
    try:
        return open_workspace(_resolve_root())
    except NWTError as e:
        raise RuntimeError(str(e)) from e


mcp = FastMCP(
    "neuroweave-timeline",
    instructions=(
        "NeuroWeave Timeline records the evolution of a project: every "
        "decision, refactor, and file change becomes a node in a durable "
        "timeline. Use create_event to record work as you do it, "
        "search_history to find what happened, get_project_story for a "
        "high-level summary, and explain_file to trace a file's history."
    ),
)


# --- tool: create_event -------------------------------------------------------


@mcp.tool()
def create_event(
    task: str,
    summary: str,
    reason: str | None = None,
    files: list[str] | None = None,
    tags: list[str] | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    """Append a new event to the project's timeline.

    Args:
        task: Short imperative title (e.g. "Add activation engine").
        summary: One or two sentences describing what was done.
        reason: Why this change was made. Strongly encouraged — this is
            what turns NWT from a log into a *history*.
        files: Project-relative file paths this event touched.
        tags: Free-form labels (e.g. ``["memory", "optimization"]``).
        parent: Id of the preceding event in the linear chain, or null
            to start a new branch.

    Returns:
        The persisted event as a dict (including its allocated id and
        timestamp).
    """
    ev = timeline.create_event(
        task=task,
        summary=summary,
        reason=reason,
        files=files,
        tags=tags,
        parent=parent,
        root=_resolve_root(),
    )
    return ev.to_dict()


# --- tool: search_history -----------------------------------------------------


@mcp.tool()
def search_history(
    query: str,
    limit: int | None = None,
    search_files: bool = True,
    search_tags: bool = True,
) -> list[dict[str, Any]]:
    """Search the timeline.

    Args:
        query: Substring to search for (case-insensitive). Matched against
            task, summary, reason, file paths, and tags.
        limit: Cap on the number of results.
        search_files: Include file paths in the search.
        search_tags: Include tags in the search.

    Returns:
        A list of matching events, ordered by id ascending. Each event
        is a dict; see ``create_event`` for the field set.
    """
    events = timeline.search(query, root=_resolve_root(), limit=limit)
    if not (search_files and search_tags):
        # Re-filter when caller wants a narrower scope.
        q = query.strip().lower()
        out: list = []
        for ev in events:
            haystacks: list[str] = [ev.task, ev.summary, ev.reason or ""]
            if search_files:
                haystacks.append(" ".join(ev.files))
            if search_tags:
                haystacks.append(" ".join(ev.tags))
            if any(q in h.lower() for h in haystacks):
                out.append(ev)
        events = out
    return [ev.to_dict() for ev in events]


# --- tool: get_project_story --------------------------------------------------


@mcp.tool()
def get_project_story(max_milestones: int = 10) -> dict[str, Any]:
    """Return a compressed project story.

    The story contains:
        * project name and first/last event timestamps
        * up to ``max_milestones`` milestone events
        * the file that changed most often (the "spine file")
        * all decision events (those with a non-empty reason)

    Returns:
        A dict mirroring the structure of :class:`ProjectStory`, plus a
        human-readable ``text`` rendering for direct LLM consumption.
    """
    ws = _open_or_error()
    events = timeline.list_events(root=_resolve_root())
    g = build_graph(ws)
    name = _read_project_name(ws)
    story = build_story(
        events, project_name=name, graph=g, max_milestones=max_milestones
    )
    return {
        "project_name": story.project_name,
        "event_count": story.event_count,
        "first_event": story.first_event.to_dict() if story.first_event else None,
        "last_event": story.last_event.to_dict() if story.last_event else None,
        "spine_file": story.spine_file,
        "milestones": [ev.to_dict() for ev in story.milestones],
        "decisions": [ev.to_dict() for ev in story.decisions],
        "text": story.to_text(),
    }


# --- tool: explain_file -------------------------------------------------------


@mcp.tool()
def explain_file(file_path: str) -> dict[str, Any]:
    """Explain why a file exists.

    Args:
        file_path: Project-relative path to the file (e.g. ``activation.py``).

    Returns:
        A dict with keys ``file``, ``created_in``, ``modified_in``,
        ``events``, ``reason`` and a human-readable ``text`` rendering.

    Example:
        >>> explain_file("activation.py")
        {
          "file": "activation.py",
          "created_in": 23,
          "modified_in": [45, 67],
          "reason": "Improve graph retrieval performance.",
          "text": "activation.py\\n  created in event 23\\n  ..."
        }
    """
    ws = _open_or_error()
    g = build_graph(ws)
    result = explain_file(g, file_path)

    lines = [f"# {result['file']}"]
    if result["created_in"] is not None:
        lines.append(f"created in:  event {result['created_in']}")
    if result["modified_in"]:
        lines.append(
            "modified in: " + ", ".join(str(n) for n in result["modified_in"])
        )
    if result["reason"]:
        lines.append("")
        lines.append("reason:")
        lines.append(f"  {result['reason']}")
    for ev in result["events"]:
        lines.append(f"  - [{ev.short_id()}] {ev.task}  ({ev.summary})")

    return {
        "file": result["file"],
        "created_in": result["created_in"],
        "modified_in": result["modified_in"],
        "reason": result["reason"],
        "events": [ev.to_dict() for ev in result["events"]],
        "text": "\n".join(lines) + "\n",
    }


# --- helpers -----------------------------------------------------------------


def _read_project_name(ws: Workspace) -> str | None:
    import json

    try:
        meta = json.loads(ws.metadata_file.read_text(encoding="utf-8"))
        name = meta.get("project_name")
        return name if isinstance(name, str) else None
    except (OSError, json.JSONDecodeError):
        return None


# --- entry point --------------------------------------------------------------


def main() -> None:
    """Run the MCP server on stdio."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
