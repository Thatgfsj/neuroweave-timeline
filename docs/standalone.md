# Why NWT is intentionally independent

> *Don't make NWT a subproject of NWC. Make it a thing that NWC may
> eventually call.*

This is a strategic choice, not a technical one. The reasoning:

## Timeline memory is more general than cognitive memory

The question *"why does this file exist?"* isn't special to AI agents.
It comes up constantly for:

* **Engineers** — "who added this cache and why?"
* **Researchers** — "what was the chain of experiments that led to
  this conclusion?"
* **Writers** — "how did this chapter evolve from the first draft?"
* **Game designers** — "when did we decide the antagonist's
  motivation?"
* **People keeping a journal** — "what was I thinking three months
  ago?"

Cognitive memory (NWC's domain) is a special case. Timeline memory is
the general primitive. Building the general primitive first means
**more users, more feedback, fewer assumptions**.

## Independence is a survival strategy

Subprojects inherit their parent's constraints, dependencies, and
release cadence. A small standalone tool can:

* ship when it's ready
* take on dependencies its parent wouldn't tolerate
* be replaced, forked, or absorbed without drama
* be useful to people who don't care about the parent project

NWT ships a single `pip install` and a `.nwt/` directory. That is the
cheapest possible adoption cost.

## A two-track path

```
NeuroWeave Timeline (NWT)
    ↓
proves useful on its own
    ↓
accumulates users
    ↓
becomes a stable ecosystem
    ↓
NWC (NeuroWeave Cortex / cognitive memory) calls NWT
```

This is the **opposite** of the usual "build the platform first,
hope the use case appears" pattern. We start with the use case.

If NWT is never picked up by NWC, that's fine — it was a useful tool
in its own right. If NWC is never built, also fine — NWT is
independent.

## When NWC *does* call NWT, what does that look like?

Concretely, the integration we have in mind is:

* NWC's MCP tools include `nwt.search_history`, `nwt.get_project_story`,
  `nwt.explain_file` — so NWC agents get process memory for free.
* NWT events become a layer that NWC's cognitive memory can index on
  top of (without modifying NWT).
* The two projects share a transport (MCP) and a data shape (events as
  JSON), and nothing else.

There is no plan for NWT to call NWC. NWT does not need to know that
NWC exists. That asymmetry is what keeps NWT small.

## A line in the sand

If a future contributor proposes to make NWT a subpackage of NWC, the
answer is no. If a future contributor proposes to make NWT depend on
NWC, the answer is no. If a future contributor proposes to rename NWT
to make the lineage clear, the answer is *probably* no, but we can
talk about it.

The whole point is that NWT stands or falls on its own merit.
