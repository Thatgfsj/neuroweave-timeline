# Roadmap

## v0.1 (2026-06-15) — MVP

* Phase 1: Core timeline engine (create, get, list, search)
* Phase 2: Project evolution graph (typed relations, lineage)
* Phase 3: CLI (`init`, `log`, `history`, `show`, `search`, `graph`, `link`, `story`, `explain`, `rebuild-indices`)
* Phase 4: MCP server (`create_event`, `search_history`, `get_project_story`, `explain_file`)
* Phase 5: Deterministic evolution summaries (milestone selection + project story)
* Phase 6: Text-tree visualization (web UI later)

Out of scope for v0.1, by design: vector database, embeddings, RAG,
knowledge-graph reasoning, LLM planning, autonomous agents, NWC
integration.

## v0.2 (2026-09-20) — Git integration & auto-grow (this release)

* Git hook integration: `nwt install-git-hook` logs every commit
  automatically (see `docs/git-hook.md`)
* `--strict` mode and `--ai-command` for hook-supplied reasons
* Automatic event chaining: plain `nwt log` calls form one linear
  history; `--parent none` starts a branch
* Event `importance` field (low / normal / high / milestone), factored
  into milestone selection and grouped in `nwt story`
* `nwt diff FROM TO` — changes between two events
* `nwt compact` — merge small consecutive same-tag events (with
  `.nwt/snapshots/` backup and full id remapping)
* Cross-process id allocation lock and counter self-healing

## v0.3 — Snapshots & deeper git linkage

* `nwt snapshot` records the full state of tracked files at a moment
* `nwt restore <event-id>` reconstructs the workspace at that point
* Snapshots live under `.nwt/snapshots/` (compact backups already land there)
* Auto-link events to commit SHAs surfaced in `nwt log` / `nwt show`
* `nwt rewind` rewinds a branch to a previous event's state

## v0.4 — Multi-agent collaboration

* A small embedded database (SQLite) as a write-ahead cache so
  concurrent agents don't fight over the JSON files
* Per-author identity on each event (`author` field)
* Conflict resolution: same event, two agents, take both, mark one as
  the winner, the other as `supersedes`

(The cross-process id lock shipped early, in v0.2.)

## v0.5 — NWC integration (only if NWT earns it)

NWT is intentionally independent. If a real user base accumulates
and the demand is clear, NWC can become a *consumer* of NWT — calling
its MCP tools to remember process history, with NWC providing
cognitive memory on top.

Not before. Adoption of the simpler thing first.

## v0.6+

* Web UI for the timeline + graph
* Interactive filters
* Time travel
* Export to static site

## Non-goals

We will resist:

* A hosted cloud version in v0.x
* Telemetry of any kind
* Anything that requires trusting NWT with credentials

NWT is a plain-text tool for plain-text work. The day it stops being
that is the day it should be replaced.
