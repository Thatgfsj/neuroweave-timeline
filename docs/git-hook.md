# Git hook integration

The single biggest reason NWT timelines end up empty is friction. The
post-commit hook removes it: every `git commit` becomes a timeline
event, with no human or agent typing required.

## Install

```bash
nwt init
nwt install-git-hook
```

That writes a small NWT-managed block into `.git/hooks/post-commit`:

```sh
#!/bin/sh
# >>> nwt post-commit hook >>>
# Installed by `nwt install-git-hook`. Remove this block to uninstall.
nwt --root "$(git rev-parse --show-toplevel)" log-commit || exit 1
# <<< nwt post-commit hook <<<
```

From now on:

```bash
git commit -m "Refactor retrieval layer" -m "Reason: lookup latency was high"
# nwt: logged [12] Refactor retrieval layer
```

Each commit is logged at most once (the full SHA is stored in the
event's `meta`), the event auto-chains onto the latest event, and
changed file paths are recorded in `files`.

## Options

### `--strict` — refuse events without a reason

```bash
nwt install-git-hook --strict
```

With `--strict`, a commit whose message has no `Reason:` line is not
logged and the hook exits non-zero, so the omission is visible right
after the commit:

```bash
git commit -m "tweak"
# error: commit ab12cd3 has no 'Reason:' line (--strict refuses to log it);
#        amend the commit or drop --strict
```

`--strict` never blocks the commit itself (post-commit hooks run after
the fact) — it refuses to write an event without a stated *why*.

### `--ai-command` — let a model fill the reason

```bash
nwt install-git-hook --ai-command "claude -p"
```

When the human didn't write a `Reason:` line, NWT pipes the commit
subject and body to the given command and uses the first line of its
output as the reason:

```bash
claude -p "Write one concise sentence explaining WHY this commit was
made. Reply with the sentence only. ..." → 'Lookup latency was high'
```

The command is invoked as `<command> <prompt>` (prompt as the final
argument). If the command fails or returns nothing, the event is still
logged — without a reason. Combine both flags freely:

```bash
nwt install-git-hook --strict --ai-command "claude -p"
```

## Check status

```bash
nwt git-hook-status
# post-commit hook: installed
#   strict: yes
#   ai-command: claude -p
# workspace: initialized
# latest event: [12] Refactor retrieval layer
```

## Manual logging & repair

The hook just calls `nwt log-commit`, so you can run it yourself —
for example to backfill a commit made before the hook was installed:

```bash
nwt log-commit                    # logs HEAD once (idempotent)
nwt log-commit --strict           # same, but refuses events without a Reason
```

## Uninstall

Delete the NWT block from `.git/hooks/post-commit` (or the whole file
if it contains nothing else):

```bash
# Linux / macOS
sed -i '/# >>> nwt post-commit hook >>>/,/# <<< nwt post-commit hook <<</d' .git/hooks/post-commit
```

Re-running `nwt install-git-hook` later re-creates the block with
default flags.

## Notes

* The hook requires the `nwt` executable on `PATH` inside hook
  contexts. If you installed NWT in a virtualenv, make sure that
  environment's `bin`/`Scripts` directory is on `PATH` when committing,
  or edit the installed hook to call `nwt` by absolute path.
* On Windows the hook is a POSIX shell script, which Git for Windows
  executes with its bundled `sh` — no extra setup needed.
* Events created by the hook carry `tags: ["commit"]` and
  `meta: {"sha": "<full sha>"}`; `nwt search "commit"` or any
  `search-file` query reaches them like any other event.
