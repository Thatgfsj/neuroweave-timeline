# Event Model

Every action in your project — a decision, a refactor, a file creation,
a bug fix — becomes a **Timeline Event**. Events are the atoms of NWT.

## Schema

```json
{
  "id": "000123",
  "timestamp": "2026-06-15T10:00:00Z",
  "task": "Implement Activation Engine",
  "summary": "Added activation spreading mechanism",
  "reason": "Graph retrieval performance degraded",
  "files": ["activation.py", "retriever.py"],
  "tags": ["memory", "optimization"],
  "parent": "000122"
}
```

### Fields

| Field        | Type           | Required | Notes                                        |
|--------------|----------------|:--------:|----------------------------------------------|
| `id`         | string         |    ✅    | 6-digit zero-padded, allocated by the engine |
| `timestamp`  | ISO 8601 UTC   |    ✅    | `Z` suffix or `+00:00` both accepted         |
| `task`       | string         |    ✅    | Short imperative title                       |
| `summary`    | string         |    ✅    | What was done, in 1–2 sentences             |
| `reason`     | string         |          | **Why** it was done — encouraged             |
| `files`      | list of string |          | Project-relative paths touched               |
| `tags`       | list of string |          | Lowercased on save                           |
| `parent`     | string         |          | Id of preceding event in the linear chain    |
| `meta`       | object         |          | Escape hatch for forward-compatible fields   |

### Why `reason` matters

The `reason` field is the difference between a log and a *history*.
Tools that record only `task` and `summary` give you a list of things
that happened. Tools that also record `reason` give you a story an
agent can use to reason about the project.

When you call `nwt search "performance"` and an event has a `reason`
like *"graph retrieval performance degraded"*, that's the event that
explains why `activation.py` exists.

## Linear history: `parent`

The `parent` field is a single pointer to the previous event in a
linear chain. It produces the default narrative spine of the project:

```
event 1  →  event 2  →  event 3  →  event 4
```

You can omit `parent` to start a new branch (e.g. an experiment that
later becomes the main line, or a feature branch).

## Typed edges: `nwt link`

For richer relationships, use `nwt link`:

```bash
nwt link 12 18 --relation caused_by
nwt link 18 21 --relation fixes
nwt link 21 30 --relation replaces
nwt link 30 35 --relation extends
```

These are stored in `.nwt/relations/<source>.json` and are surfaced by
`nwt graph`, by the MCP `search_history` tool, and by `explain_file`.

| Relation     | Semantics                                          |
|--------------|----------------------------------------------------|
| `follows`    | Default linear order (also implicit via `parent`) |
| `caused_by`  | Source event was triggered by target event         |
| `fixes`      | Source event corrects a flaw in target             |
| `replaces`   | Source event supersedes target                     |
| `extends`    | Source event builds on top of target               |

## File associations

Listing the files an event touched turns NWT from a generic log into a
project-aware history. `nwt explain foo.py` walks the file index and
returns:

* the event that **created** the file
* the events that **modified** it
* the earliest `reason` (which usually explains why it was created)

## Tags

Free-form. Conventions that work well in practice:

* `milestone`, `release` — used by the milestone selector
* `setup`, `refactor`, `perf`, `bug`, `docs` — easy filters
* Anything project-specific (`activation`, `graph`, `api`, ...)

Tags are lowercased on save. There's no central registry — keep them
short and project-local.
