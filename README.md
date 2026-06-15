# 🧠 NeuroWeave Timeline (NWT)

> **Process memory for AI agents and humans.**
> NWT remembers how a project became what it is — not just what it is now.

[![CI](https://img.shields.io/github/actions/workflow/status/Thatgfsj/neuroweave-timeline/ci.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/Thatgfsj/neuroweave-timeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-std.io-orange.svg?style=flat-square)](https://modelcontextprotocol.io)
[![Release v0.1.0](https://img.shields.io/badge/release-v0.1.0-blue.svg?style=flat-square)](https://github.com/Thatgfsj/neuroweave-timeline/releases/tag/v0.1.0)
[![GitHub stars](https://img.shields.io/github/stars/Thatgfsj/neuroweave-timeline?style=flat-square)](https://github.com/Thatgfsj/neuroweave-timeline/stargazers)

Most tools remember **results**. NWT remembers **evolution**.

```
Traditional memory:  User → Context → Summary → Memory
Timeline memory:     User → Action  → Timeline Event → Evolution Graph
```

Every meaningful action in your project — a decision, a refactor, a
file creation, a bug fix — becomes a node in a durable timeline. The
links between nodes form an **Evolution Graph** that explains *why* the
project looks the way it does today.

---

## 💬 What you can ask

| Question | One-liner |
|---|---|
| *Why does this file exist?* | `nwt explain activation.py` |
| *Why was this architecture chosen?* | `nwt search "architecture decision"` |
| *What happened three months ago?* | `nwt history` |
| *What decisions led to the current design?* | `nwt story` |
| *Show me the evolution graph* | `nwt graph` |

AI agents reach the same answers over MCP — see [MCP integration](#-mcp-integration).

---

## 🚀 30-second quick start

```bash
pip install -e .
cd your-project
nwt init
nwt log "Add activation engine" \
      --files activation.py \
      --reason "retrieval was slow"
nwt history
nwt graph
```

That's it. Storage is plain JSON under `.nwt/`. No database, no
embeddings, no vendor lock-in, no daemon.

---

## 👀 A tour of the output

### `nwt history` — what happened, in order

```
  [1] 2026-06-15  Project scaffolded  [setup, milestone]
      reason: Kickoff the MVP
      files:  pyproject.toml, README.md
  [2] 2026-06-15  Add memory engine  [core, milestone]
      reason: Need a place to put things
      files:  memory.py
  [3] 2026-06-15  Add activation spreading  [memory, optimization]
      reason: Retrieval was sequential and slow
      files:  activation.py, retriever.py
  [4] 2026-06-15  Add decay mechanism  [memory]
      reason: Stale nodes should fade
      files:  activation.py
  [5] 2026-06-15  Vectorize activation  [refactor, performance]
      reason: Loop was the hot path in profiling
      files:  activation.py
```

### `nwt graph` — the evolution as a tree

```
○    1  Project scaffolded
│
│    2  Add memory engine
      ├─ sibling  → [   4] Add decay mechanism
      └─ extends  → [   3] Add activation spreading
│
│    3  Add activation spreading
│
│    5  Vectorize activation
```

### `nwt story` — 100 events compressed to one page

```
# memory-engine-demo — evolution summary

span: 2026-06-15 → 2026-06-15  (5 events)

milestones:
  - 1  Project scaffolded          — Kickoff the MVP
  - 2  Add memory engine           — Need a place to put things
  - 3  Add activation spreading    — Retrieval was sequential and slow
  - 4  Add decay mechanism         — Stale nodes should fade
  - 5  Vectorize activation        — Loop was the hot path in profiling

spine file: activation.py

decisions (events with stated reasons):
  - [1] Project scaffolded: Kickoff the MVP
  - [2] Add memory engine: Need a place to put things
  ...
```

### `nwt explain activation.py` — why a file exists

```
# activation.py
created in:  event 3
modified in: 4, 5

reason:
  Retrieval was sequential and slow
```

---

## 🧩 How it works

NWT lives in your project as a single `.nwt/` directory:

```
your-project/
└── .nwt/
    ├── metadata.json       # project name, schema version
    ├── .counter.json       # next event id
    ├── timeline/           # one JSON file per event
    │   ├── 000001.json
    │   ├── 000002.json
    │   └── ...
    ├── relations/          # typed edges out of each source event
    ├── snapshots/          # reserved for v0.2
    └── indices/            # derived, rebuildable
        ├── files.json
        └── tags.json
```

Everything is JSON, atomically written. The whole workspace is
`grep`-friendly and `git diff`-friendly. See
[`docs/architecture.md`](docs/architecture.md) for the rationale.

---

## 🔌 MCP integration

For agent developers — NWT ships an MCP server exposing the same
answers as tools:

| Tool | Returns |
|---|---|
| [`create_event`](docs/mcp.md#create_event) | A persisted event with id and timestamp |
| [`search_history`](docs/mcp.md#search_history) | Matching events across task/summary/reason/files/tags |
| [`get_project_story`](docs/mcp.md#get_project_story) | Compressed project story (milestones, decisions, spine file) |
| [`explain_file`](docs/mcp.md#explain_file) | Created/modified-in + earliest reason for a file |

Wire it up in your MCP client:

```json
{
  "mcpServers": {
    "nwt": {
      "command": "nwt-mcp",
      "env": { "NWT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

The server picks the workspace from `$NWT_ROOT` if set, else its own
cwd. See [`docs/mcp.md`](docs/mcp.md) for the recommended agent loop:

1. **Session start:** call `get_project_story` to load context.
2. **For unfamiliar files:** call `explain_file` rather than reading cold.
3. **As work is done:** call `create_event` with a `reason` explaining *why*.
4. **When uncertain:** call `search_history` with a hypothesis from the current code.

---

## 📦 Install

```bash
# from a clone (editable)
git clone https://github.com/Thatgfsj/neuroweave-timeline
cd neuroweave-timeline
pip install -e .

# from PyPI (coming soon)
pip install neuroweave-timeline
```

Requires **Python 3.10+**. The CLI depends on `click`; the MCP server
depends on `mcp`. Both install automatically.

To install dev dependencies (pytest) and run the test suite:

```bash
pip install -e ".[dev]"
pytest -q
```

---

## 🗺️ Roadmap

v0.1 (this release) is the MVP. Phases 1–6 of the spec are done.
Highlights of what's next:

- **v0.2** — git integration; auto-link events to commits
- **v0.3** — workspace snapshots; restore a project at a past event
- **v0.4** — multi-agent collaboration history
- **v0.5** — NWC integration, *only if NWT earns it on its own*

See [`docs/roadmap.md`](docs/roadmap.md) and
[`docs/standalone.md`](docs/standalone.md) for the full story.

---

## 🤝 Contributing

Issues and PRs are welcome. The whole project is ~1,500 lines of
Python plus docs — easy to read end-to-end. Start with
[`docs/architecture.md`](docs/architecture.md) for the layout and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow.

---

## 🔒 Security

NWT stores only what you give it, on disk, in your project's `.nwt/`.
It does not phone home, does not read environment variables other
than `NWT_ROOT`, and writes nowhere else. The `.gitignore` refuses
to track tokens, keys, or `.env` files. See
[`SECURITY.md`](SECURITY.md) for the full policy.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
