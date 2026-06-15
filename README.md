# NeuroWeave Timeline (NWT)

> Process memory for AI agents and humans.
> NWT remembers how a project became what it is — not just what it is now.

Most tools remember **results**. NWT remembers **evolution**.

```
Traditional Memory:  User → Context → Summary → Memory
Timeline Memory:     User → Action  → Timeline Event → Evolution Graph
```

Every meaningful action in your project — a decision, a refactor, a file creation, a bug fix —
becomes a node in a durable timeline. The links between nodes form an **Evolution Graph**
that explains *why* the project looks the way it does today.

---

## What you can ask NWT

- *Why does this file exist?* → `nwt explain activation.py`
- *Why was this architecture chosen?* → `nwt search "architecture decision"`
- *What happened three months ago?* → `nwt history --since 2026-03-01`
- *What decisions led to the current design?* → `nwt story`
- *Show me the evolution graph* → `nwt graph`

Agents reach the same answers over MCP:

- `create_event`
- `search_history`
- `get_project_story`
- `explain_file`

---

## Quick start

```bash
pip install -e .

cd your-project
nwt init
nwt log "Initial scaffold" --reason "Started NWT MVP" --tags setup,mvp
nwt log "Add activation engine" --files activation.py --tags memory
nwt link 1 2 --relation extends

nwt history
nwt show 2
nwt graph
```

Storage is plain JSON under `.nwt/`. No database. No embeddings. No vendor lock-in.

---

## Why standalone?

NWT is intentionally independent. Timeline memory is a general-purpose primitive
useful to writers, researchers, game designers, and humans who keep journals —
not just to AI cognition systems. See [`docs/standalone.md`](docs/standalone.md).

Other systems may call NWT. NWT does not call them.

---

## Status

**v0.1 MVP.** Implements Phases 1–6 of the spec.

| Phase | Scope                                      | Status |
|------:|--------------------------------------------|:------:|
| 1     | Core timeline engine                       |   ✅   |
| 2     | Project evolution graph                    |   ✅   |
| 3     | CLI                                        |   ✅   |
| 4     | MCP server                                 |   ✅   |
| 5     | Deterministic evolution summaries          |   ✅   |
| 6     | Text-tree visualization (web UI later)     |   ✅   |

See [`docs/roadmap.md`](docs/roadmap.md) for what comes next.

---

## License

MIT.
