# Cross-project bulletin

Maintained in `prompt-lab`. Cross-project conventions, recommended setups, and
tactical guidance you (or Claude) should keep in mind when working on any of
your projects. Read on-demand with `/bulletin`; a one-line digest surfaces in
`/readup` at session start.

Entries are ordered by date, newest first. When advice changes, edit the
entry — history lives in git. When advice no longer applies, delete the entry.

---

## 2026-08-17 — Worktrees: one per mutating agent, not one per feature

Scope: all projects, any time two or more agents write files in the same repo concurrently

Git operations are tree-global — `stash`, `checkout`, `reset`, and `clean` don't
know which agent authored which hunk. On 2026-08-13 in person-tracking, one
subagent ran `git stash` to A/B-compare a fix against HEAD and wiped a second
subagent's uncommitted work tree-wide. Recovered with `git stash pop`, but only
because the second agent noticed its files had reverted and said so.

**Give each file-mutating agent its own `git worktree`** whenever it might run
concurrently with another mutating agent — not per feature, per agent. Two
mechanisms already do this:

- The Agent tool's `isolation: "worktree"` option, for subagent dispatch.
- The `superpowers:using-git-worktrees` skill, for a solo session starting
  feature work that needs isolation.

Read-only agents (audits, scouts, `Explore`) are safe to share a tree — this
only applies to agents that write. If agents must share a tree anyway, tell
each explicitly not to run `stash`/`reset`/`checkout`, and check `git status`
after each returns.

---

## 2026-08-06 — Xcode: two red suites that aren't real failures

Scope: every Xcode project — raconte, MusicForge, anything using XcodeGen

Both of these present as a **failing test suite with no failing test**, which is
the worst possible disguise: the natural response is to go debug code that was
never broken. Each cost about an hour in raconte on 2026-08-05.

**1. A generated `.xcodeproj` goes stale on every checkout, not just on
`project.yml` edits.** Where the project file is gitignored and produced by
`xcodegen generate`, switching to a branch that lacks a file the current project
references fails as a bare `** TEST FAILED **` naming no test. The real error is
buried far above:

```
error: Build input files cannot be found: '…/FrameClockSink.swift'
```

It cost a whole 15-run flake experiment that reported 15/15 "failures" — every
one a stale project, measuring nothing. **Run `xcodegen generate` after every
branch switch**, and treat a failure naming no test as a build error until you've
grepped for `error:` in the log.

**2. Never pipe `xcodebuild` through `head` (or any early-closing pipe).** The
closed pipe kills xcodebuild mid-run and leaves its simulator runner wedged,
which corrupts the simulator's accessibility service. The damage then lands on
*unrelated* UI tests, as timeouts rather than assertion failures:

```
Failed to get list of active applications: Timed out while fetching attributes
'XC_kAXXCAttributeFocusedApplications'
```

**The tell is timing, not the message**: an untouched test that normally takes
41 s took 441 s in the poisoned run. If a UI suite fails and the durations look
absurd, suspect the simulator, not the diff. Recover with `xcrun simctl shutdown
all` then `erase`. Same applies after any interrupted UI run — shut the
simulators down before re-running, and let a boot finish before launching tests
(an immediate re-run after `shutdown all` fails with "Timed out trying to boot
simulator after waiting 60.00s").

Use `> file.log 2>&1` and grep the file. Never `| head`.

---

## 2026-08-02 — Dates: UTC at rest, Pacific on display

Scope: every project that stores a timestamp or draws a date axis

**Timestamps are stored in UTC. A calendar day shown to a human is
`America/Los_Angeles`.** Those are different layers and the bug is always
conflating them.

How it surfaced: the Prompt Lab dashboard drew an `Aug 3` bar at 5:30pm on
Aug 2. Not a label bug — three different clocks disagreed and nothing in the
codebase declared which one owned a value:

- the raw tables were UTC (SQLite `datetime('now')` is UTC, which is easy to
  forget), so 13 prompts typed on Aug 2 afternoon were genuinely stamped Aug 3;
- the summary writers used naive `datetime.now()` — mini-local Pacific;
- every frontend axis was built with `new Date(…).toISOString().slice(0,10)`,
  which is **UTC**.

The rules that fall out:

- **Store UTC. Never store local time.** It reads fine and cannot be migrated
  across a DST boundary without loss — there is no offset that is correct for
  a whole table.
- **`toISOString().slice(0, 10)` is not a local date.** This is the single
  most common instance: it looks like "today" and is UTC, so every chart axis,
  zero-filled date range and "is this fresh" check rolls over at 5pm Pacific in
  summer. Use `Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' })`
  — `en-CA` yields `YYYY-MM-DD`, so it drops into the same string comparisons.
- **A bare `date(col)` in SQL over UTC-stamped rows buckets in UTC.** Pass the
  zone explicitly at the grouping site.
- **Say which clock owns a value**, in a comment or a name, wherever a date
  crosses a layer boundary. Every instance of this bug was invisible because
  both sides looked like a plain `YYYY-MM-DD` string.

Cron schedules are a related trap: Vercel crons are UTC-only, so `0 15 * * *`
is 8am Pacific in summer and **7am in winter**. If a job's hour matters, say so
where it's declared.

---

## 2026-07-28 — Secrets: .env.tpl of op:// references, piped straight to the platform

Scope: all projects with deployed secrets

The pattern that worked cleanly for rock-art-fab's Fly app — make it the
default everywhere:

- **Every credential lives in 1Password `dev-secrets`, one item per credential,
  project-prefixed titles** (`rockart-google-oauth`, `rockart-resend`,
  `rockart-session-secret`). Per-project API keys (one Resend key per project),
  never shared across apps. Create items via `op item create` one-liners Claude
  drafts and Nico runs — that pins the exact title/field path to reference.
- **Self-minted secrets (service keys, session secrets) are GENERATED by
  1Password, not by hand** (added 2026-08-02): Claude hands one command, the
  value never exists in chat or clipboard —
  `op item create --category password --vault dev-secrets --title <project>-<purpose> --generate-password='letters,digits,32'`
  then pipe it to the platform:
  `op read "op://dev-secrets/<title>/password" | vercel env add NAME production --sensitive --force -y`
  — the flags are mandatory: newer CLIs ask `? Store as sensitive?` BEFORE the
  value prompt and it silently eats the piped line (cost a failed write
  2026-08-02). Stdin is the value; the trailing newline is the submit — bare
  pipe, never `tr -d '\n'`. Verify with `vercel env ls` — a good write reads
  seconds old. Never the generate-then-save-then-paste flow.
- **The repo commits only `.env.tpl`**: `KEY=op://dev-secrets/<item>/<field>`
  lines (unquoted), plus non-secret config baked in as plain values.
  `.gitignore` gets `.env`, `.env.local`, `.env.*.local`.
- **Loading is one pipe, no plaintext on disk or in scrollback** (Nico runs it;
  the block-secrets hook rightly stops Claude):
  - Fly: `op inject -i .env.tpl | fly secrets import --app <app> --stage`
  - Local dev: `op inject -i .env.tpl -o .env.local`
  - Vercel projects keep using Vercel env vars as before.
- Rotation = update the 1Password item, rerun the same pipe. The `.env.tpl` in
  git is the always-current inventory of what the app needs.

## 2026-07-19 — Spell out every ask fresh (no "commands above")

Scope: all projects

Whenever Claude asks Nico to do something manually — click session, command
sequence, open a file, test steps — that message must carry the COMPLETE
instructions: full paths, every command, every step, restated even if they
appeared earlier. Never reference "the command above" / "as before": the
scrollback fills with superseded copies and finding the current one is a
headache. Repetition beats scrolling. (Generalizes the existing smoke-test
rule to all asks; also in `~/.claude/CLAUDE.md`.)

## 2026-07-19 — Opening files: bare path on its own line, not an `open` command

Scope: all projects

iTerm lets Nico right-click a file path to open it — no copy-paste needed. So
when Claude wants him to open a file (image, PDF, report, anything non-command):

- Write a short label line ("Open this file:"), then the bare absolute path
  **alone on its own line**. Multiple files = one path per line.
- Do NOT wrap file-opening in an `open …` fenced command block — that forces a
  copy-paste for something one right-click does.
- The 📋 COPY-THE-BELOW fenced-block convention still applies to actual shell
  commands; this replaces it only for opening files.

## 2026-07-08 — Measurement minimalism (analytics/telemetry policy)

Scope: all projects

**Add a metric only when you have a question it answers, at the coarsest
granularity that answers it** — never because collection is easy. Full
rationale: `prompt-lab/docs/measurement-policy.md`. The short version:

- The beacon stays anonymous by construction (no cookies, no stable IDs,
  daily-rotating visitor hash). Anything that can follow a person across days
  crosses the GDPR/ePrivacy consent line and buys a banner + compliance story
  on every site at once. Don't.
- Several sites have single-digit users Nico knows by name (by-side.net ≈ one
  attorney under an NDA) — fine-grained "anonymous" analytics deanonymize at
  that N. Session paths / time-on-page there = surveilling a specific person.
- Rich signal belongs on authenticated server-side surfaces with a specific
  purpose (ibuild4you `api_usage` is the model), not in client-side tracking.
- New beacon events: one named event at a time, each with an issue stating the
  question it answers (e.g. `login`, prompt-lab#10).

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
