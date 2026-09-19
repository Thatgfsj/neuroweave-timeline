"""Click-based CLI for NWT.

Command surface::

    nwt init
    nwt log TASK [--summary TEXT] [--reason TEXT] [--files f1,f2]
                 [--tags t1,t2] [--parent ID|none] [--timestamp ISO]
                 [--importance LEVEL]
    nwt history [--limit N] [--offset N] [--reverse]
    nwt show ID
    nwt search QUERY
    nwt search-file PATH
    nwt search-tag TAG
    nwt graph [--max N]
    nwt link SOURCE TARGET --relation RELATION
    nwt story [--max-milestones N]
    nwt explain PATH
    nwt diff FROM TO
    nwt compact [--time-window S] [--min-group N] [--dry-run]
    nwt rebuild-indices
    nwt install-git-hook [--strict] [--ai-command CMD]
    nwt git-hook-status
    nwt log-commit [--strict] [--ai-command CMD]

All commands share a single global ``--root`` flag pointing at the
project root (the directory containing ``.nwt/``). The default is the
current working directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from nwt import __version__
from nwt.core.errors import NWTError
from nwt.core.time import short_date
from nwt.graph.builder import build_graph
from nwt.graph.lineage import explain_file as explain_file_lineage
from nwt.graph.lineage import to_json_dict
from nwt.graph.visualize import render_tree
from nwt.storage.layout import init_workspace, open_workspace
from nwt.storage.writer import rebuild_indices
from nwt.timeline import engine as timeline
from nwt.timeline.summary import build_story


def _err(msg: str) -> None:
    click.secho(f"error: {msg}", fg="red", err=True)


def _ws(ctx: click.Context):
    """Open the workspace for the invoked command (raises NWTError)."""
    return open_workspace(ctx.obj["root"])


# --- root group --------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="nwt")
@click.option(
    "--root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd(),
    show_default=False,
    help="Project root (defaults to current directory).",
)
@click.pass_context
def cli(ctx: click.Context, root: Path) -> None:
    """NeuroWeave Timeline — process memory for your project."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


# --- workspace commands --------------------------------------------------------


@cli.command()
@click.option("--name", default=None, help="Project name to record in metadata.")
@click.pass_context
def init(ctx: click.Context, name: str | None) -> None:
    """Initialize a new .nwt/ workspace in the current directory."""
    try:
        ws = init_workspace(ctx.obj["root"], project_name=name)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho(f"initialized NWT workspace at {ws.nwt_dir}", fg="green")


# --- event commands -------------------------------------------------------------


@cli.command("log")
@click.argument("task")
@click.option("--summary", default=None, help="One-sentence description of the change.")
@click.option("--reason", default=None, help="Why this change was made.")
@click.option("--files", default=None, help="Comma-separated list of files touched.")
@click.option("--tags", default=None, help="Comma-separated list of tags.")
@click.option("--importance", default="normal",
              type=click.Choice(["low", "normal", "high", "milestone"], case_sensitive=False),
              help="Event importance level.")
@click.option("--parent", default=None,
              help="Parent event id, or 'none' to start a new branch "
                   "[default: append after the latest event].")
@click.option("--timestamp", default=None, help="Override timestamp (ISO 8601).")
@click.pass_context
def log_cmd(
    ctx: click.Context,
    task: str,
    summary: str | None,
    reason: str | None,
    files: str | None,
    tags: str | None,
    importance: str,
    parent: str | None,
    timestamp: str | None,
) -> None:
    """Append a new event to the timeline."""
    if not summary:
        summary = task  # sensible default — task doubles as summary
    try:
        ev = timeline.create_event(
            task=task,
            summary=summary,
            reason=reason,
            files=_split_csv(files),
            tags=_split_csv(tags),
            parent=parent,
            importance=importance,
            timestamp=timestamp,
            root=ctx.obj["root"],
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho(f"logged [{ev.short_id()}] {ev.task}", fg="green")


@cli.command()
@click.option("--limit", type=click.IntRange(min=0), default=None, help="Maximum number of events to show.")
@click.option("--offset", type=click.IntRange(min=0), default=0, help="Skip the first N events.")
@click.option("--reverse/--forward", default=False, help="Show newest first.")
@click.pass_context
def history(ctx: click.Context, limit: int | None, offset: int, reverse: bool) -> None:
    """Show the project timeline (oldest first by default)."""
    try:
        events = timeline.list_events(
            root=ctx.obj["root"], limit=limit, offset=offset, reverse=reverse
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    for ev in events:
        tag_str = f"  [{', '.join(ev.tags)}]" if ev.tags else ""
        imp_str = f"  ({ev.importance})" if ev.importance != "normal" else ""
        reason = f"\n      reason: {ev.reason}" if ev.reason else ""
        files = f"\n      files:  {', '.join(ev.files)}" if ev.files else ""
        click.echo(
            f"  [{ev.short_id()}] {short_date(ev.timestamp)}  {ev.task}{imp_str}{tag_str}{reason}{files}"
        )
    if not events:
        click.echo("(no events)")


@cli.command()
@click.argument("event_id")
@click.pass_context
def show(ctx: click.Context, event_id: str) -> None:
    """Show a single event in detail."""
    try:
        ev = timeline.get_event(event_id, root=ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.echo(json.dumps(ev.to_dict(), indent=2, ensure_ascii=False))


@cli.command()
@click.argument("query")
@click.option("--limit", type=click.IntRange(min=0), default=None)
@click.pass_context
def search(ctx: click.Context, query: str, limit: int | None) -> None:
    """Search across task, summary, reason, files, and tags."""
    try:
        results = timeline.search(query, root=ctx.obj["root"], limit=limit)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    for ev in results:
        click.echo(f"[{ev.short_id()}] {ev.task}  — {ev.summary}")
    if not results:
        click.echo("(no matches)")


@cli.command("search-file")
@click.argument("path")
@click.pass_context
def search_file(ctx: click.Context, path: str) -> None:
    """List every event that touched a given file."""
    try:
        results = timeline.search_by_file(path, root=ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    for ev in results:
        click.echo(f"[{ev.short_id()}] {ev.task}")
    if not results:
        click.echo("(no events touched this file)")


@cli.command("search-tag")
@click.argument("tag")
@click.pass_context
def search_tag(ctx: click.Context, tag: str) -> None:
    """List every event carrying a tag."""
    try:
        results = timeline.search_by_tag(tag, root=ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    for ev in results:
        click.echo(f"[{ev.short_id()}] {ev.task}")
    if not results:
        click.echo("(no events with that tag)")


@cli.command()
@click.argument("from_id")
@click.argument("to_id")
@click.pass_context
def diff(ctx: click.Context, from_id: str, to_id: str) -> None:
    """Show changes between two events (FROM must precede TO)."""
    try:
        result = timeline.diff_events(from_id, to_id, root=ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    events = result["events"]
    click.echo(f"Diff: [{events[0].short_id()}] → [{events[-1].short_id()}]")
    click.echo(f"Events: {len(events)} between these points")
    click.echo()

    if result["files_added"]:
        click.secho(f"Added: {', '.join(result['files_added'])}", fg="green")
    if result["files_removed"]:
        click.secho(f"Removed: {', '.join(result['files_removed'])}", fg="red")
    if result["files_in_both"]:
        click.echo(f"In both (likely modified): {', '.join(result['files_in_both'])}")

    click.echo()
    click.echo("Events in range:")
    for ev in events:
        click.echo(f"  [{ev.short_id()}] {short_date(ev.timestamp)} {ev.task}")


@cli.command()
@click.option("--time-window", type=click.IntRange(min=0), default=3600, show_default=True,
              help="Time window in seconds for grouping events.")
@click.option("--min-group", type=click.IntRange(min=2), default=3, show_default=True,
              help="Minimum group size to compact.")
@click.option("--dry-run", is_flag=True,
              help="Show what would be merged without touching disk.")
@click.pass_context
def compact(ctx: click.Context, time_window: int, min_group: int, dry_run: bool) -> None:
    """Merge consecutive events with same tags that are close in time."""
    try:
        result = timeline.compact_events(
            root=ctx.obj["root"],
            time_window_seconds=time_window,
            min_group_size=min_group,
            dry_run=dry_run,
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    if result["merged"] == 0:
        click.echo("No events to compact.")
        return
    label = "Would compact" if result["dry_run"] else "Compacted"
    click.echo(
        f"{label}: {result['original_count']} → {result['compacted_count']} events "
        f"(merged {result['merged']})"
    )
    if result["backup"]:
        click.secho(f"backup: {result['backup']}", fg="cyan")


# --- graph & summary commands ---------------------------------------------------


@cli.command()
@click.option("--max", "max_per_chain", type=click.IntRange(min=1), default=200, show_default=True,
              help="Maximum nodes per linear branch.")
@click.pass_context
def graph(ctx: click.Context, max_per_chain: int) -> None:
    """Render the Evolution Graph as a text tree."""
    try:
        g = build_graph(_ws(ctx))
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.echo(render_tree(g, max_per_chain=max_per_chain).rstrip())


@cli.command()
@click.argument("source")
@click.argument("target")
@click.option(
    "--relation", "-r", required=True,
    type=click.Choice(
        ["follows", "caused_by", "fixes", "replaces", "extends"], case_sensitive=False
    ),
)
@click.pass_context
def link(ctx: click.Context, source: str, target: str, relation: str) -> None:
    """Create a typed edge between two events."""
    try:
        timeline.link(source, target, relation, root=ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho(f"linked {source} --{relation}--> {target}", fg="green")


@cli.command()
@click.option("--max-milestones", type=click.IntRange(min=0), default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def story(ctx: click.Context, max_milestones: int, as_json: bool) -> None:
    """Print a compressed project story."""
    try:
        ws = _ws(ctx)
        events = timeline.list_events(root=ctx.obj["root"])
        graph_obj = build_graph(ws)
        story_obj = build_story(
            events, project_name=ws.read_project_name(), graph=graph_obj,
            max_milestones=max_milestones,
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(story_obj.to_dict(), indent=2, ensure_ascii=False))
    else:
        click.echo(story_obj.to_text())


@cli.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def explain(ctx: click.Context, path: str, as_json: bool) -> None:
    """Explain why a file exists (created/modified/refactored)."""
    try:
        g = build_graph(_ws(ctx))
        result = explain_file_lineage(g, path)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(to_json_dict(result), indent=2, ensure_ascii=False))
        return

    click.echo(f"# {result['file']}")
    if result["created_in"] is not None:
        click.echo(f"created in:  event {result['created_in']}")
    if result["modified_in"]:
        click.echo(f"modified in: {', '.join(str(n) for n in result['modified_in'])}")
    if result["reason"]:
        click.echo("")
        click.echo("reason:")
        click.echo(f"  {result['reason']}")
    if not result["events"]:
        click.echo("(no events touched this file)")


@cli.command("rebuild-indices")
@click.pass_context
def rebuild_indices_cmd(ctx: click.Context) -> None:
    """Recompute the secondary search indices from the canonical event files."""
    try:
        rebuild_indices(_ws(ctx))
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho("indices rebuilt", fg="green")


# --- git integration -------------------------------------------------------------


@cli.command("install-git-hook")
@click.option("--strict", is_flag=True,
              help="Refuse to log commits without a 'Reason:' line.")
@click.option("--ai-command", default=None,
              help='Fill a missing Reason with an external model, e.g. "claude -p".')
@click.pass_context
def install_git_hook_cmd(ctx: click.Context, strict: bool, ai_command: str | None) -> None:
    """Install the NWT post-commit hook into this repository."""
    from nwt import githook

    try:
        path = githook.install_hook(ctx.obj["root"], strict=strict, ai_command=ai_command)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho(f"installed post-commit hook at {path}", fg="green")
    click.echo("every commit will now be logged automatically; see docs/git-hook.md")


@cli.command("git-hook-status")
@click.pass_context
def git_hook_status_cmd(ctx: click.Context) -> None:
    """Show whether the NWT post-commit hook is installed and its flags."""
    from nwt import githook

    try:
        status = githook.hook_status(ctx.obj["root"])
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    if status["hook_installed"]:
        click.secho("post-commit hook: installed", fg="green")
        if status["strict"]:
            click.echo("  strict: yes")
        if status["ai_command"]:
            click.echo(f"  ai-command: {status['ai_command']}")
    else:
        click.echo("post-commit hook: not installed (run `nwt install-git-hook`)")
    click.echo(
        "workspace: initialized" if status["workspace_initialized"]
        else "workspace: missing (run `nwt init`)"
    )
    if status["latest_event"]:
        ev = status["latest_event"]
        click.echo(f"latest event: [{ev['id']}] {ev['task']}")


@cli.command("log-commit")
@click.option("--strict", is_flag=True,
              help="Fail instead of logging a commit without a 'Reason:' line.")
@click.option("--ai-command", default=None,
              help='Fill a missing Reason with an external model, e.g. "claude -p".')
@click.pass_context
def log_commit_cmd(ctx: click.Context, strict: bool, ai_command: str | None) -> None:
    """Log the latest commit as a timeline event (used by the git hook)."""
    from nwt import githook

    try:
        ev = githook.log_commit(ctx.obj["root"], strict=strict, ai_command=ai_command)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    if ev is None:
        click.echo("commit already logged; nothing to do")
        return
    click.secho(f"nwt: logged [{ev.short_id()}] {ev.task}", fg="green")


# --- helpers -----------------------------------------------------------------


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p] or None


if __name__ == "__main__":  # pragma: no cover
    cli()
