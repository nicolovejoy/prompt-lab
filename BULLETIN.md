# Cross-project bulletin

Maintained in `prompt-lab`. Cross-project conventions, recommended setups, and
tactical guidance you (or Claude) should keep in mind when working on any of
your projects. Read on-demand with `/bulletin`; a one-line digest surfaces in
`/readup` at session start.

Entries are ordered by date, newest first. When advice changes, edit the
entry — history lives in git. When advice no longer applies, delete the entry.

---

## 2026-07-05 — Playwright browser hygiene (stray "Chrome for Testing" instances)

Scope: all projects

Playwright browsers were accumulating as orphans on Nico's machines (issue
prompt-lab#8, diagnosed in a musicforge session). Two rules for Claude:

- **Call `browser_close` when you're done** with `mcp__playwright__*` work.
  Each session that touches those tools gets its own browser; leaving it open
  is the main source of strays.
- **Don't SIGKILL `playwright test`** (double Ctrl+C, hard kills). Let runs
  exit or time out gracefully — killed runners orphan their headless browsers.

Safety net: `reap-playwright.sh` (synced via prompt-lab's install.sh) runs as
an async global SessionStart hook and kills any `ms-playwright` process whose
parent is launchd (PPID 1) — i.e. genuine orphans only. Do NOT "clean up" with
a bare `pkill -f ms-playwright`: that kills live sessions' browsers too.

## 2026-06-24 — Intentions fully removed (prompt-lab)

Scope: prompt-lab (informational for all)

"Intentions" (the synthesized per-project goal list) are **gone**, not just
frozen. Deprecated 2026-06-23 (generation off), then removed entirely on
2026-06-24 after the rows were purged — the data was noise (one project hit
180 "active") and nothing rendered it after the dashboard redesign.

Removed: the `intentions` table (dropped local; Turso copy pending a manual
`turso db shell promptlab "DROP TABLE IF EXISTS intentions;"`), all store
methods, `web/api/intentions.py`, the `synthesizer.py --intentions` flag +
`synthesize_intentions()`, the sync, the `/roadmap` + `gc-read.sh` intentions
subcommands, and the mobile PWA's IntentionsTab.

This is a rip-out, not reversible. If goal-tracking ever returns, build it
fresh — the old completion/abandon logic never fired.

## 2026-06-06 — Cloud (remote) agent sessions

Scope: all projects

Claude Code on the web runs in an ephemeral container, not your laptop/mini.
Consequences:

- **Branch namespace.** Cloud agents work on `cloud/<feature>` branches off
  `main` and open a PR. Local sessions must NOT commit to a `cloud/*` branch
  while its agent is active — that's how histories diverge and pushes collide.
  `/readup`'s `git fetch` + `git status -sb` surfaces any divergence at the
  next local session start.
- **No local telemetry.** Cloud sessions have no `~/.claude/prompt-history.db`,
  no installed slash commands, no venv, no Turso creds. So `/readup` and
  `/handoff` don't run there, and cloud work is currently INVISIBLE to
  prompt-lab's dashboard. Known gap — accepted for now; revisit if cloud
  usage grows enough to matter.
- **Handoff recipe.** To dispatch work: push the plan + any done tasks to a
  `cloud/<feature>` branch, then tell the cloud agent to execute it
  autonomously, commit per task, and open a PR when lint+test+build are green.
  Visual smoke stays with you on the Vercel preview.

---

## 2026-05-13 — Browser automation scope (Playwright MCP)

Scope: all projects

Playwright MCP is installed at user scope. Use it for ad-hoc UI verification
— not as a substitute for the test suite.

Permissions by target:
- **localhost** (any port): full access. Navigate, click, type, fill forms,
  screenshot, read DOM.
- **Vercel preview URLs** (`*.vercel.app` and branch deploys): full access.
  Treat them as ephemeral.
- **Production** (the canonical custom domain for the project): READ-ONLY by
  default. Navigate and screenshot are fine. Do NOT click, type, submit forms,
  or otherwise mutate state without explicit per-action approval from Nico.
  When in doubt about whether a URL is production, ask before clicking.

Reproducing a bug on production? Capture via screenshot + DOM read, then
reproduce on localhost or a preview deploy.

---

## 2026-05-13 — Per-project Anthropic workspaces

Scope: all projects that use the Anthropic SDK

Each project should have its own Anthropic workspace + API key, not a shared
key. Reasons: independent cost visibility, independent revocation, and blast
radius containment if a key leaks (see notemaxxing 2026-04 incident, ~$54).

All five active projects (notemaxxing, prntd, musicforge, prompt-lab,
ibuild4you) are on their own workspaces as of 2026-05-17. When wiring a new
project: keep the key in 1Password, load via `.env.tpl` pattern, never
commit. See `prompt-lab/claude_api.py` for the env-loading convention and
`prompt-lab/docs/cost-tracking.md` for how the workspace ID flows into the
Admin API cost pipeline.
