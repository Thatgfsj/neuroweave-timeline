# Security Policy

## No secrets in the repo

NWT's `.gitignore` is set up to **refuse to track** any file that
looks like a token or key:

- `*.pem`, `*.key`, `*.p12`, `*.pfx`
- `secrets.*`, `credentials.*`
- `*id_rsa*`, `*id_ed25519*`
- GitHub/GitLab tokens: `*ghp_*`, `*gho_*`, `*ghu_*`, `*ghs_*`,
  `*ghr_*`, `*github_pat_*`, `*glpat-*`
- Any `.env*` file (except `.env.example`)

If you find a token in a commit, history, or PR, **do not** open a
public issue — see "Reporting a vulnerability" below.

## What NWT does with your data

NWT stores the following on disk inside your project's `.nwt/`
directory:

- Event files (task, summary, reason, file paths, tags, timestamps)
- Typed edges between events
- Two derived indices (`files.json`, `tags.json`) — these are
  rebuildable from the events, so deleting them is safe.

**NWT does not:**

- Phone home
- Send telemetry
- Read environment variables other than `NWT_ROOT` (used only to
  resolve the workspace)
- Write anywhere outside the project's `.nwt/`

## Reporting a vulnerability

Please report security issues privately by emailing the maintainer.
Do not open a public GitHub issue.

(Add a contact address here once a public security contact is in
place — e.g. a dedicated email or GitHub Security Advisories.)
