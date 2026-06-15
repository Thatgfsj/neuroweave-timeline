# Contributing to NWT

Thanks for your interest. NWT is intentionally small. Most PRs can
land in under an hour of review.

## Quick rules

1. **No secrets in commits.** Tokens, passwords, private URLs, or
   real user data must never appear in a commit, issue, or PR. If you
   accidentally paste one, rewrite the history before requesting
   review.
2. **Tests pass locally.** `pip install -e ".[dev]" && pytest -q`
   must stay green.
3. **Public APIs stay small.** The CLI surface, MCP tool names, and
   the on-disk JSON shape are part of the contract. Anything that
   changes them needs a `CHANGELOG.md` entry and a heads-up in the PR.
4. **No new top-level dependencies** without discussion. The MVP runs
   on `click` and `mcp` and we'd like to keep it that way.

## Local workflow

```bash
git clone https://github.com/Thatgfsj/neuroweave-timeline
cd neuroweave-timeline
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pip install -e ".[dev]"

# run the test suite
pytest -q

# end-to-end CLI smoke test
nwt init
nwt log "..." --reason "..."
nwt history
nwt graph
```

## Code layout

```
nwt/
├── core/        # TimelineEvent, Relation, ids
├── storage/     # .nwt/ layout, atomic writes, indices
├── timeline/    # public engine + summary
├── graph/       # Evolution Graph + lineage + visualize
├── cli/         # Click command surface
└── mcp/         # FastMCP server
```

CLI and MCP are *thin* — they parse input, call the engine, and
render output. The engine goes through `storage/`, which is the only
place that touches the filesystem.

## How to add a new event relation

1. Add the value to `Relation` in `nwt/core/relations.py`.
2. Update the docstring in `nwt/graph/builder.py` if the meaning is
   non-obvious.
3. Add a test in `tests/test_graph.py`.
4. Add a row to the "Relation" table in `docs/event_model.md`.

## How to add a new CLI command

1. Add a `@cli.command()` in `nwt/cli/main.py`.
2. Wire it through the engine in `nwt/timeline/engine.py` if needed.
3. Add a test in `tests/test_cli.py` that runs the command as a
   subprocess.
4. Mention it in `CHANGELOG.md` under the next version.

## Releasing

The maintainer handles releases via `git tag -a vX.Y.Z` and
`gh release create`. Releases trigger nothing automatically; the CI
workflow is the only thing watching tags.

## Security

Found a vulnerability? Please email the maintainer privately rather
than opening a public issue. (Once the repo has a public contact
address, link it here.)
