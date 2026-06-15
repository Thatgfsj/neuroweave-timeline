"""Click-based CLI for NWT.

Command surface (matches the spec)::

    nwt init
    nwt log TASK [--summary TEXT] [--reason TEXT] [--files f1,f2]
                 [--tags t1,t2] [--parent ID] [--timestamp ISO]
    nwt history [--limit N] [--offset N] [--reverse]
    nwt show ID
    nwt search QUERY
    nwt search-file PATH
    nwt search-tag TAG
    nwt graph [--max N]
    nwt link SOURCE TARGET --relation RELATION
    nwt story [--max-milestones N]
    nwt explain PATH
    nwt rebuild-indices

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
from nwt.graph.builder import build_graph
from nwt.graph.lineage import explain_file
from nwt.graph.visualize import render_tree
from nwt.storage.layout import init_workspace
from nwt.storage.writer import rebuild_indices
from nwt.timeline import engine as timeline
from nwt.timeline.summary import build_story


def _err(msg: str) -> None:
    click.secho(f"error: {msg}", fg="red", err=True)


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


# --- commands ----------------------------------------------------------------


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


@cli.command("log")
@click.argument("task")
@click.option("--summary", default=None, help="One-sentence description of the change.")
@click.option("--reason", default=None, help="Why this change was made.")
@click.option("--files", default=None, help="Comma-separated list of files touched.")
@click.option("--tags", default=None, help="Comma-separated list of tags.")
@click.option("--parent", default=None, help="Parent event id (linear chain).")
@click.option("--timestamp", default=None, help="Override timestamp (ISO 8601).")
@click.pass_context
def log_cmd(
    ctx: click.Context,
    task: str,
    summary: str | None,
    reason: str | None,
    files: str | None,
    tags: str | None,
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
            timestamp=timestamp,
            root=ctx.obj["root"],
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho(f"logged [{ev.short_id()}] {ev.task}", fg="green")


@cli.command()
@click.option("--limit", type=int, default=None, help="Maximum number of events to show.")
@click.option("--offset", type=int, default=0, help="Skip the first N events.")
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
        reason = f"\n      reason: {ev.reason}" if ev.reason else ""
        files = f"\n      files:  {', '.join(ev.files)}" if ev.files else ""
        click.echo(
            f"  [{ev.short_id()}] {_short_date(ev.timestamp)}  {ev.task}{tag_str}{reason}{files}"
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
@click.option("--limit", type=int, default=None)
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
@click.option("--max", "max_per_chain", type=int, default=200, show_default=True,
              help="Maximum nodes per linear branch.")
@click.pass_context
def graph(ctx: click.Context, max_per_chain: int) -> None:
    """Render the Evolution Graph as a text tree."""
    try:
        from nwt.storage.layout import open_workspace

        ws = open_workspace(ctx.obj["root"])
        g = build_graph(ws)
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
@click.option("--max-milestones", type=int, default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def story(ctx: click.Context, max_milestones: int, as_json: bool) -> None:
    """Print a compressed project story (Phase 5)."""
    try:
        from nwt.storage.layout import open_workspace

        ws = open_workspace(ctx.obj["root"])
        events = timeline.list_events(root=ctx.obj["root"])
        graph_obj = build_graph(ws)
        name = _read_project_name(ws)
        story_obj = build_story(
            events, project_name=name, graph=graph_obj, max_milestones=max_milestones
        )
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(_story_to_json(story_obj), indent=2, ensure_ascii=False))
    else:
        click.echo(story_obj.to_text())


@cli.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def explain(ctx: click.Context, path: str, as_json: bool) -> None:
    """Explain why a file exists (created/modified/refactored)."""
    try:
        from nwt.storage.layout import open_workspace

        ws = open_workspace(ctx.obj["root"])
        g = build_graph(ws)
        result = explain_file(g, path)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(_explain_to_json(result), indent=2, ensure_ascii=False))
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
        from nwt.storage.layout import open_workspace

        ws = open_workspace(ctx.obj["root"])
        rebuild_indices(ws)
    except NWTError as e:
        _err(str(e))
        sys.exit(1)
    click.secho("indices rebuilt", fg="green")


# --- helpers -----------------------------------------------------------------


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p] or None


def _short_date(iso: str) -> str:
    return iso[:10] if iso else ""


def _read_project_name(ws) -> str | None:
    try:
        meta = json.loads(ws.metadata_file.read_text(encoding="utf-8"))
        name = meta.get("project_name")
        return name if isinstance(name, str) else None
    except (OSError, json.JSONDecodeError):
        return None


def _story_to_json(story) -> dict:
    return {
        "project_name": story.project_name,
        "first_event": story.first_event.to_dict() if story.first_event else None,
        "last_event": story.last_event.to_dict() if story.last_event else None,
        "event_count": story.event_count,
        "spine_file": story.spine_file,
        "milestones": [ev.to_dict() for ev in story.milestones],
        "decisions": [ev.to_dict() for ev in story.decisions],
    }


def _explain_to_json(result: dict) -> dict:
    return {
        "file": result["file"],
        "created_in": result["created_in"],
        "modified_in": result["modified_in"],
        "reason": result["reason"],
        "events": [ev.to_dict() for ev in result["events"]],
    }


if __name__ == "__main__":  # pragma: no cover
    cli()
