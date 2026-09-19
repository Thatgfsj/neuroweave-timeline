# Changelog

All notable changes to NWT are documented in this file. Versions follow
[Semantic Versioning](https://semver.org/). The first release is v0.1.0.

## [0.2.0] — 2026-09-20 — auto-grow & hardening

### Added

* **Git hook integration** (`nwt.githook`)
  * `nwt install-git-hook` writes a managed post-commit hook; every
    commit becomes an event (subject → task/summary, `Reason:` body line
    → reason, changed paths → files, SHA → `meta`)
  * `--strict` refuses to log commits without a `Reason:` line
  * `--ai-command "claude -p"` lets an external model fill a missing reason
  * `nwt git-hook-status` reports install state and flags
  * `nwt log-commit` for manual/idempotent logging; see `docs/git-hook.md`
* **Automatic event chaining**: `nwt log` appends after the latest event
  by default; `--parent none` starts an explicit branch
* **Event importance** (`low` / `normal` / `high` / `milestone`) —
  factored into milestone scoring, grouped in `nwt story` output
* **`nwt diff FROM TO`** — files added/removed/in-both between two
  events, plus the events in range
* **`nwt compact`** — merge small consecutive same-tag events
  (`--time-window`, `--min-group`, `--dry-run`)
* Cross-process lock around the id counter (fcntl / msvcrt); the write
  path also self-heals a counter that fell behind the timeline

### Fixed

* **`compact` no longer corrupts the store** — it used to delete from a
  nonexistent directory, leaving every old event file behind while
  renumbering the survivors; the rewrite now backs up to
  `.nwt/snapshots/`, remaps parents/relations/indices, and resets the
  counter
* **MCP `explain_file` crashed on every call** — the tool shadowed the
  lineage helper of the same name and recursed into itself
* **`nwt diff` with reversed ids** raised an uncaught IndexError in the
  CLI; it is now a clean validation error
* File paths are normalized to POSIX form on save, so `src\foo.py` and
  `src/foo.py` index under one key
* A corrupt `indices/*.json` file is rebuilt automatically instead of
  crashing the write path

### Changed

* `nwt storage`: index handling consolidated into `nwt.storage.indices.IndexStore`
* `story` / `explain` JSON payloads are built by the model layer and
  shared verbatim by the CLI and MCP surfaces
* Milestone scoring computes descendant counts in one O(V+E) pass
  (integer bitsets, reverse topological order) instead of a BFS per event

## [0.1.0] — 2026-06-15 — MVP

First public release. Implements all six phases of the MVP spec.

### Added

* **Core timeline engine** (`nwt.core`, `nwt.timeline.engine`)
  * `create_event`, `get_event`, `list_events`, `search`
  * `search_by_file`, `search_by_tag` (with secondary index for speed)
  * Zero-padded 6-digit event ids; parents are validated and canonicalized
* **Project evolution graph** (`nwt.graph`)
  * `EvolutionGraph` with `children`, `parents`, `ancestors`, `descendants`, `linear_chain`, `roots`
  * Typed edges: `follows` (implicit via `parent`), `caused_by`, `fixes`, `replaces`, `extends`
  * `explain_file` — trace a file's history (created in, modified in, reason)
  * ASCII tree visualization with sibling/typed-edge forks
* **Storage** (`nwt.storage`)
  * Plain JSON under `.nwt/` — no database
  * Atomic writes via temp-file + `os.replace`
  * Derived indices (`files.json`, `tags.json`) with `nwt rebuild-indices`
* **CLI** (`nwt.cli`)
  * `nwt init`, `nwt log`, `nwt history`, `nwt show`, `nwt search`,
    `nwt search-file`, `nwt search-tag`, `nwt graph`, `nwt link`,
    `nwt story`, `nwt explain`, `nwt rebuild-indices`
  * `--json` flags for machine-readable output on `story` and `explain`
  * Global `--root` flag pointing at the project root
* **MCP server** (`nwt.mcp.server`)
  * `create_event`, `search_history`, `get_project_story`, `explain_file`
  * Stdio transport; workspace from `$NWT_ROOT` or cwd
* **Evolution summaries** (`nwt.timeline.summary`)
  * Deterministic milestone selection (no LLM)
  * Structured `ProjectStory` with project name, milestones, spine file, decisions
  * Pre-rendered `text` field ready for LLM context
* **Tests** — 40 tests covering core, storage, engine, graph, CLI, summaries
* **Examples** — `examples/demo_project/seed.py` + walkthrough
* **Docs** — `architecture`, `event_model`, `mcp`, `roadmap`, `standalone`

### Deliberately NOT in v0.1

* Vector database / embeddings / RAG
* Knowledge-graph reasoning
* LLM planning / autonomous agents
* NWC integration (NWT ships independent — see `docs/standalone.md`)
