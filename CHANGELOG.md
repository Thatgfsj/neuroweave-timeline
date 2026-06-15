# Changelog

All notable changes to NWT are documented in this file. Versions follow
[Semantic Versioning](https://semver.org/). The first release is v0.1.0.

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
