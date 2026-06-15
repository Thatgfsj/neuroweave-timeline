# Walkthrough: a tiny memory engine

This is the story the seeded demo project tells. You can produce the same
output by running `seed.py` and then `nwt history` / `nwt story`.

## 1. Project scaffolded

The very first event. Set up the package layout and the CLI. Tagged as
a `milestone` because it represents a fresh start.

## 2. Add memory engine

Built the in-memory graph store. Tagged as a `milestone` — this is the
core of the system.

## 3. Add activation spreading

Retrieval was slow, so we added an activation-spreading walk. This
extends the memory engine (`extends` edge from event 2).

## 4. Add decay mechanism

Stale activations should fade. Added a per-step decay factor. Marked
as fixing a flaw in the previous design (`fixes` edge from 4 → 5).

## 5. Vectorize activation

Profiling showed the loop was the hot path. Replaced it with numpy
batched scoring.

---

## Try it

```bash
$ nwt history
  [    1] 2026-06-15  Project scaffolded  [setup, milestone]
  [    2] 2026-06-15  Add memory engine  [core, milestone]
  [    3] 2026-06-15  Add activation spreading  [memory, optimization]
  [    4] 2026-06-15  Add decay mechanism  [memory]
  [    5] 2026-06-15  Vectorize activation  [refactor, performance]

$ nwt graph
○    1  Project scaffolded
│
○    2  Add memory engine
│
○    3  Add activation spreading
│
○    4  Add decay mechanism
│
○    5  Vectorize activation
│
├─ extends → [3] Add activation spreading
├─ fixes   → [5] Vectorize activation

$ nwt story
# memory-engine-demo — evolution summary

span: 2026-06-15 → 2026-06-15  (5 events)

milestones:
  - 1  Project scaffolded  — Kickoff the MVP
  - 2  Add memory engine  — Need a place to put things
  - 3  Add activation spreading  — Retrieval was sequential and slow
  - 4  Add decay mechanism  — Stale nodes should fade
  - 5  Vectorize activation  — Loop was the hot path in profiling

spine file: activation.py

decisions (events with stated reasons):
  - [1] Project scaffolded: Kickoff the MVP
  - [2] Add memory engine: Need a place to put things
  - [3] Add activation spreading: Retrieval was sequential and slow
  - [4] Add decay mechanism: Stale nodes should fade
  - [5] Vectorize activation: Loop was the hot path in profiling

$ nwt explain activation.py
# activation.py
created in:  event 3
modified in: 4, 5
reason:
  Retrieval was sequential and slow
```

Notice how the chain of events explains not just *what* the file does,
but *why* it looks the way it does — and the same answers are available
to any AI agent via the MCP tools.
