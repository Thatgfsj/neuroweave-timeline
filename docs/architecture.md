# Architecture

## Goals

NWT v0.1 has one job: **make project history queryable, durable, and
agent-accessible.** We do this with a small, boring stack on purpose.

## On-disk layout

Inside the project that runs `nwt init`:

```
.nwt/
├── metadata.json      # project name, schema version, created_at
├── .counter.json      # next event id
├── timeline/          # one JSON file per event
│   ├── 000001.json
│   ├── 000002.json
│   └── ...
├── relations/         # one JSON file per source event
│   ├── 000002.json    # edges leaving event 2
│   └── ...
├── snapshots/         # reserved for v0.2
└── indices/           # derived data; safe to delete
    ├── files.json
    └── tags.json
```

Everything is JSON. No SQLite, no vector store, no daemon. The whole
workspace is `grep`-friendly and git-diff-friendly.

### Why plain JSON?

* **Trivial to inspect** — `cat .nwt/timeline/000001.json` works.
* **Trivial to back up** — copy the directory.
* **Trivial to reason about** — no migrations, no schema evolution
  surprises. We version the format in `metadata.json` and that's it.
* **Trivially editable** — a human can hand-craft an event for an
  offline action.

The tradeoff: scanning all events is O(N) per query. We mitigate that
with the small `indices/` directory, which is derived data and can be
deleted at any time (`nwt rebuild-indices` rebuilds it from the
canonical timeline).

## Module layout

```
nwt/
├── core/        # pure data: TimelineEvent, Relation, id generation
├── storage/     # .nwt/ filesystem layout, atomic writes, indices
├── timeline/    # public engine: create_event, get_event, list_events, search
├── graph/       # Evolution Graph over events + relations; lineage helpers
└── cli/, mcp/   # the two user surfaces
```

The two surfaces (CLI, MCP) are thin: they parse input, call the
engine, and render output. The engine never reads or writes files
directly — it goes through `storage/`, which is the only place that
knows about `os.replace` and tmp files.

## The Evolution Graph

The graph is a directed multigraph over events. Two kinds of edges:

1. **Implicit follows** — the `parent` field on each event becomes a
   `follows` edge from parent → child. This is the linear narrative
   spine.
2. **Typed edges** — `caused_by`, `fixes`, `replaces`, `extends`,
   recorded explicitly via `nwt link` (CLI) or via the storage writer
   (programmatic).

The graph lives in memory after a single `build_graph(ws)` call. For
realistic projects (thousands of events) it fits comfortably in a few
megabytes, and graph operations stay sub-millisecond.

## Why no database in MVP?

Three reasons, in order of importance:

1. **Adoption friction.** A standalone tool that ships with its own
   daemon loses to one that ships as a `pip install`.
2. **Portability.** A `.nwt/` directory travels with the project. You
   can `tar` it, commit it, copy it between machines. A database
   cannot.
3. **Verifiability.** When something goes wrong, you can read every
   file with `cat`. There's no hidden state.

We may revisit this in v0.4 (multi-agent collaboration history) when
concurrent writers become the norm. The on-disk JSON will be the
*source of truth* even then; a database would be a cache, not the
store.

## Concurrency model

The MVP assumes one writer at a time (a human, a single agent, or a
serialized CI job). Atomic file writes make the storage crash-safe:
readers either see the old file or the new one, never a half-written
one. Cross-process safety is provided by the OS's atomic rename.

The `next_id` allocator uses a thread lock plus an atomic counter
file, so two writers in the same process can't collide, and two
processes writing the counter will see one of them "win" the rename —
the loser will reload and try again on the next call. This is good
enough for the MVP; stronger guarantees wait for v0.2.
