# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Start here

`README.md` covers setup; `docs/README.md` is the documentation index.
The canonical UI is `web/`. Former local UI/scanner source is in `archive/`.

## Deploy (cloud dashboard)

```bash
cd web && vercel --prod
```

Env vars needed in Vercel: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `AUTH_SECRET`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` (read-only PAT for the Todos page; optional `GITHUB_USER`, defaults to `nicolovejoy`)

To self-host: fork the repo, create a Turso database, set the env vars above, deploy `web/` to Vercel.

## Architecture

- `store/` — backend-agnostic KnowledgeStore ABC + SQLite (default) and Turso implementations
- `claude_api.py` — shared Claude API utilities, centralized env loading (.env, .env.local)
- `synthesizer.py` — nightly: daily summaries, weekly rollups, project snapshots
- `send-review.py` — nightly email via Resend; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `generate-report.py` — bi-monthly markdown report; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `/handoff` saves session continuity; `/handoff-full` adds immediate recaps.
- `/workflow-maintenance` handles explicit docs/memory maintenance; nightly owns backfill.
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- **Data & access model: see `docs/data-and-access.md`** — the single coherent description of the three storage tiers (raw/private, processed/private, public), how public vs private is differentiated, the two-tier cloud auth, and how secrets grant access. Read it first when reasoning about what's stored where or who can see it.
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages. No read-time allowlist: it serves whatever rows exist in `public_session_summaries` / `public_weekly_rollups`, which are safe-by-construction (written only by the reviewed, git-committed draft-to-artifact flow — `scripts/draft_public_refresh.py` → human review → `scripts/publish_public_draft.py`, plus the original `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or raw sync). The allowlist (`docs/public-allowlist.txt`) is an 8-key **write-time publish gate**, not a read gate — `publish_public_draft.py` refuses to publish an off-list project, and `check_public_allowlist.py` audits published rows against it. Current keys: `bakerylouise, ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase, songscribe` (`am-i-an-ai` dropped 2026-07-21 when the site removed lojong and its rows were unpublished). The table `project` column is the consumer's historyKey, NOT the display slug. The invariant to preserve is "never write un-scrubbed text into the public_* tables." Curation of *which* projects appear publicly is the consumer's job — the `selected-projects` MDX manifest (`content/projects/*.mdx`) is the single source of truth for the public site. Unknown project → empty `200`. **Read-time counts projection (2026-07-21):** for a project with `project_metadata.public_counts=1`, the endpoint additionally overlays counts-only weekly rows projected from the private `weekly_rollups` (numeric columns only — no prose can leak) on weeks lacking a published prose row. Opt in via `scripts/seed_public_counts.py`.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with peer repos (selected-projects, prntd) via an append-only shared log living in the **standalone private git repo `nicolovejoy/handoff`**, cloned to `~/src/.handoff` (synced across mini + laptop). One file per pairing, each with a `repos: [a, b]` front-matter manifest. The SessionStart hook auto-injects, per matching file, the dated `### ` headlines newer than 30 days plus an active-entry count (`HANDOFF_HEADLINE_DAYS` overrides the window). Bodies are not injected — `cat` the file when a headline matters. Full bodies used to be injected and reached 193 KB per session start (2026-09-13).

**Writing a cross-repo note** — never hand-edit + manually `git push`; use the wrapper so the pull-rebase/commit/push is atomic and conflicts surface loudly:

```
~/.claude/bin/handoff.sh append <file> "### YYYY-MM-DD <from> → <to>: <subject>

<body>"
```

It inserts the entry at the **top** of `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome (a normal Edit), then `~/.claude/bin/handoff.sh sync`. Exit codes: 0 ok · 3 conflict (kept local, resolve in `~/src/.handoff`) · 4 offline (kept local, re-run `sync` later) · 5 lock contention · 6 repo unwritable (a Codex sandbox without a writable root over `~/src/.handoff`, not a lock). Design + 26/26 pressure test: `docs/handoff-repo-plan.md`, `workflow/handoff-sim/`.

## Next Steps

Shipped work is in git and in the code. What follows is only what isn't:
open work, traps that cost real time, and decisions not worth re-litigating.
The full chronological log — and the narrative behind everything below, under the
`(moved 2026-09-13)` headings — lives in `docs/history.md`.

### Open

Read `docs/current-work.md` for the current backlog and deferred decisions.
For workflow work, start with `docs/codex-workflow-roadmap.md`; for operations,
use `docs/data-and-access.md` and the invariants below. Do not re-open decisions
marked settled without new evidence or Nico's instruction.

### The failure shape this repo keeps hitting

Eight incidents now share one shape: **a job keeps running while its output stops,
and the absence is recorded as "nothing" rather than "failure."** The review email
403'd for 60 nights while `review_snapshots` simply froze, reading as "the job
stopped" instead of "the job fails at its last step." The bi-monthly report was dead
4 months because its plist did `source <deleted-file> && python …` and `&&`
short-circuited. CI was red 3 days with `deploy` showing *skipped*, not failed.

Two mechanisms recur: **a fallback quietly covers the dead primary path**, and
**absence is recorded as nothing.** The countermeasure, shipped as #45: every
recurring job declares a max artifact age, checked with `max(date)` over a table that
already syncs to Turso, reported in the daily health email (`HEARTBEATS` in
`web/api/health_report.py`).

Four rules that fall out of it, each earned:
- **Alarm on the artifact, never on the job's exit status or a synthetic ping.** A
  ping is a side-channel claim that the job ran and can succeed while the artifact is
  missing — precisely how the review email looked healthy for sixty nights.
- **A failed check reports "could not check", never "fresh."** Deliberately *not* the
  fails-open pattern the pause lookup uses in the same module: a Turso outage must not
  block an email, but freshness failing open would rebuild the exact bug. An empty
  table is *stale* ("never produced"), not fresh.
- **Check the job's log before concluding anything from table rows.** The dead review
  email had 60 identical 403s in `send-review.log`. That log only exists under launchd
  — a manual run prints to the terminal instead, so the file looks empty.
- **A failure whose own cause also blocks its reporting path erases its own
  evidence.** The wake/DNS deaths couldn't push their run records, so the email
  stayed green. Fix it on the reading side: grade a WINDOW, not the newest row.

Known hole, don't mistake it for closed: the `uptime archive` heartbeat is written and
graded by the *same* request, so it catches "cron alive, pull broken" and cannot catch
"cron dead." That case degrades to "no email arrived," the weakest signal in the
system. Closing it needs a check on infrastructure that fails independently of
Vercel's scheduler; UptimeRobot's `HEARTBEAT` type is paid-only, which is what sent
#45 down the artifact route in the first place.

A second hole in the same category: `review_snapshots` records composition, not
delivery — a failed send still writes the row, so the #45 heartbeat cannot see a
last-step delivery failure.

### Invariants — the things that must not be broken

- **Turso holds no `prompts`, `sessions`, or `commits` tables at all.** Raw prompt
  text, commit messages, hostnames and local paths are physically unreachable from
  `web/`. That is the strongest guarantee in the system. Preserve it by never adding a
  sync leg — not by filtering at read time. Read-time allowlists were tried twice and
  deleted both times for drifting.
- **Cloud-direct tables have no leg in `sync_to_turso.py` and must never gain one:**
  `page_views`, `health_email_state`, `project_metadata`, `issue_categories`,
  `uptime_daily`. That absence is what makes drift structurally impossible.
- **`nightly_runs` is written locally and pushed to Turso as its own step
  AFTER the publish stage** — never inside the sync leg, or a publish failure
  eats the record of the publish failure. Catch-up is stateless (push local
  rows newer than the remote's newest `started_at`, upsert by `run_id`), so
  drift is impossible without a `run_id` meaning two things. Freshness grades
  `lab_date` — the day the run STARTED — never arrival time, or a catch-up
  push makes dead nights look live.
- **The run record never replaces an artifact heartbeat.** It is a
  self-report, the exact side-channel claim #45 forbids. `HEARTBEATS` and the
  run record are two axes and the email reads the combination.
- **An upsert never destroys paid prose.** `daily_summaries` and
  `weekly_rollups` archive the replaced row into `*_superseded` first (local
  only, never synced). Repair scripts archive before deleting.
- **Nothing automated writes the `public_*` tables.** They are written only by the
  reviewed, git-committed draft-to-artifact flow (`scripts/draft_public_refresh.py` →
  human review → `scripts/publish_public_draft.py`). Never by `/handoff`, the
  synthesizer, or raw sync. The invariant is "never write un-scrubbed text into the
  public tables."
- **The uptime archive is never backfilled.** UptimeRobot exposes rolling ratios, not
  per-day history, so a gap is missing data — render it grey, never 0%. An invented
  past would be worse than a short one.
- **Cross-repo work goes through `~/src/.handoff`, never a PR from here.** The repo
  boundary is the ownership boundary and each repo's agent owns its conventions. The
  practical tell: agents working in a sibling repo run from a cold permission slate, so
  a wall of permission prompts mid-task is the convention signalling it's being
  bypassed, not a config annoyance to route around.
- **`workflow/bin/_gc_project.sh` is the ONE project-resolution implementation** for
  `gc-read.sh`/`gc-write.sh` — never a second one. It mirrors `log-prompt.sh`:
  `--git-common-dir` (never `--show-toplevel`), only git exit 128 buckets to
  `scratch`, never an empty name.

### Traps that cost real time

- **`workflow/bin/*` and `workflow/commands/*` run from installed copies under `~/.claude/`**,
  so a committed fix is not live until copied over, per machine. Sweep:
  `for f in workflow/bin/*.sh; do diff -q "$f" ~/.claude/bin/$(basename "$f"); done`.
- **`work.zsh`'s functions are loaded once, at shell startup (`.zshrc` sources it), and stay
  in memory after that.** Reinstalling the file underneath an already-open tab does not fix
  it — that tab keeps running the stale function until it's closed and a new one opened. This
  produced the exact `-10000 AppleEvent handler failed` symptom of an already-fixed bug,
  weeks apart, purely because the terminal predated the fix (2026-09-14). Diffing installed
  vs. repo proves nothing about what a given open tab has loaded.
- **Ask what sampling window produced any "we tested it, it isn't that."** 10 requests over
  30s cannot see a 5% pass rate; UptimeRobot v2's log caps at 25 entries and Cloudflare's
  export at 500, so the oldest entry is a cap artifact, not an onset.
- **A scheduler is not a dependency mechanism.** launchd coalesces missed intervals onto one
  wake, so jobs 45 min apart start together. Ordering belongs in `nightly_pipeline.py`.
- **Never enforce a wall-clock timeout on a host that sleeps.** `time.time()` counts sleep,
  httpx's monotonic read timeout does not — the "3h19m API call" was a healthy 136s run.
- **A plist outlives whatever it points at, and launchd says nothing.**
  `source <file> && python …` runs nothing when the file is absent — it killed the
  bi-monthly report twice. A plist repointed at a scratch worktree survives that
  worktree's deletion: on 2026-09-20 the nightly fired into a directory whose only
  remaining file was the log recording its own `No such file or directory`. Every
  reader calls `load_env()`, so invoke python directly through `run-nightly.sh` — and
  never point a plist at a path you intend to delete.
- **SQLite's `weekday N` means next-or-SAME day**, so `date(<d>,'weekday 1','-7 days')` files
  every Monday under the wrong week. Correct bucket: `date(<d>,'weekday 0','-6 days')`.
- **Turso's `daily_summaries.prompt_version` is perpetually NULL by design** —
  `merge_summary_parts()` omits it (local provenance). Not a broken sync leg.
- **`/api/private_history` has no allowlist of its own** — any project, gated solely by
  `SERVICE_HISTORY_KEY`. The 8-key allowlist is the *public* tier's write gate.
- **Deep coverage over an autosuspending DB needs a poll interval longer than the
  suspend window**, not a deeper URL — else the check keeps the DB warm and reports
  that it answers. Cost garm and byside their Neon CU quota; filed in
  `scripts/uptimerobot.py`. Load-shedding is not available on our side either: `deep`
  in `web/api/health_report.py` is descriptive and `_check_target()` requests
  regardless, so reduce by editing the URL, not the flag.
- **When two sources disagree about *when*, suspect a display timezone** first. UptimeRobot's
  account display was UTC-10 and cost two rounds of cross-agent confusion.
- **Prompt counts step up once on 2026-08-14 and the step is real** — a write-time filter
  dropped every prompt under 20 chars before then. Backfill is impossible.
- **A full `sync_to_turso.py` runs past 120s** — for one upsert-only row write straight to
  Turso, and never let a sync leg touch `project_metadata`, which is cloud-direct.
- **Test UptimeRobot alerting on a throwaway monitor, never by flipping a real one to a
  failing URL** — that writes a fake outage into a permanent ratio, and the archive is never
  backfilled. Pick a target that returns a real 404 (`garm.prompt-labs.org` does):
  `https://prompt-labs.org/api/<anything>` returns **200** from the SPA catch-all.
- **Turso returns `SUM()`/`COUNT()` aggregates as JSON strings** — an explicit `int()` coalesce
  is load-bearing, or chart math concatenates.
- **UptimeRobot v2's `custom_uptime_ratio` is a string** (`"100.000-99.980-99.990"`, 1d-7d-30d)
  — split and float, or every downstream average is text.
- **The SPA catch-all serves `index.html` with a 200 for unknown paths**, so a health target on
  a nonexistent path is a permanent false UP. Targets must also be unauthenticated.
- **`vercel env add` takes no value argument** — it reads one line from stdin and the trailing
  newline is the *submit*. Never pipe through `tr -d '\n'`, never loop it; verify with
  `vercel env ls`.
- **`op inject` substitutes `op://` references inside `#` comments**, and one unresolvable ref
  aborts the file. `-o .env.local` is not a workflow here (the template unions local + cloud
  secrets) — append single variables instead.
- **`web/garm_helper.py` defaults `GARM_GATING` to `on`** — the freeze is a Vercel env var, so
  an env reset silently turns gating on and fails closed.
- **The public-draft path regex only matches `/Users/…`** — tilde paths sail through. Human
  catch only.
- **Reading `/api/public_history`: the envelope key is `rollups`, not `weekly_rollups`** — the
  wrong key reports 0 rows on a healthy endpoint.
- **Vercel log retention is ~1 hour** — post-hoc forensics on a daily cron is not available.
- **CI ruff is pinned to `0.15.22` — don't unpin.** An unpinned install produced 339 new-rule
  errors on a docs-only push; local-passing + CI-failing on docs = version drift.
- **`deploy` has `needs: test`**, so a starved or failing test run shows as *skipped*, not
  failed, and no prod deploy goes out silently.
- **Three Vercel diagnostics produce false conclusions:** repo-level webhooks (Vercel uses a
  GitHub App; check `link` on `GET /v9/projects/<id>`), grepping HTML for `_vercel/insights`
  (randomized path), `githubCommitSha` (stamped on manual deploys). Tell: zero previews ever.

### Testing

Tests are standalone runners, **not pytest** — `python -m pytest` fails at collection.
Run each directly:

```bash
for f in scripts/test_*.py; do .venv/bin/python "$f"; done
```

The standalone suites live in `scripts/test_*.py`; `.github/workflows/test.yml`
lists the CI gate. Workflow changes additionally exercise isolated session
identity, readup error states, whole-day context, and a temporary installation
roundtrip. No test should use the real history database or publish data.
`_health_mod(up=, hb=, ur=)` stubs the health endpoint; its Turso stub dispatches on
the SQL because the pause lookup, the freshness lookups and the uptime upsert share
`turso_query` and must not be conflated — pause fails open, freshness fails loud, and
the archive write must be separately observable.

### Settled — don't re-litigate

- **UptimeRobot is the sensor AND the pager; prompt-lab samples nothing and pages for
  nothing.** 5-min polling, free tier, 3-month retention — a watcher on our own
  Vercel+Turso+Resend stack would die with the watched. No Pi, no launchd sampler.
- **The health email's grading lag is deliberate — don't "simplify" it.** Escalation
  is one day late for a single dead night (the newest remote row is still age 1 the
  next morning); two dead nights escalate on time via the 2→1 age rule. And a bad
  night stays red up to 7 days with no acknowledgement path, because re-running the
  date adds a row and never clears one. Loud-for-a-week was the point.
- **OAuth is hand-rolled in Python, zero new deps** — a confidential client doing its own
  code exchange, so the `id_token` arrives over TLS and needs no JWT verification. Spec:
  `docs/phase2-oauth-plan.md`. `verify_token` requires `role` and `email`
  **keys** (key-presence, not truthiness) — that subtlety is load-bearing.
- **No display names in the sign-ins panel** — a name would cost the log's anonymity. When a
  second reader joins (#43), use a stable opaque per-user id (HMAC of email under a salt).
- **First-party beacon over Vercel Analytics** — drains are Pro-only, Hobby has no read API.
  Hosting-neutral, writes cloud-direct.
- **The public tier's curation is the consumer's job** — the `selected-projects` MDX manifest
  is the source of truth; `docs/public-allowlist.txt` mirrors it and gates *writes*.
- **The public-draft division of labour:** the machine refuses anything regex-able (paths,
  emails, tokens, DB hosts, unedited quotes, prose <15 words or ≥75% similar). The human owns
  named people/orgs, identifiability-by-description, unreleased plans, sensitive detail.
- **`private` on `project_metadata` is cosmetic only** — a hide-toggle gating no API.
  `public_counts` is the real gate.
- **The nightly jobs run on the LAPTOP and nowhere else, and there is exactly one sender**
  (2026-08-20) — two loaded readers means two emails a night. The mini runs nothing.
- **DB ownership is federated — Option B, 2026-08-10.** Raw prompts stay machine-local; each
  machine pushes processed rows to Turso, the merge point. `daily_summaries` clobber is solved
  by the per-machine parts table across MACHINES; `weekly_rollups` still isn't, deferred until
  it bites. For two agents on one machine, the new handoff source uses whole-day context
  and revision-checked saves (2026-09-14). The paired live check passed. Routine
  handoff now saves session summaries; explicit full handoff and nightly daily
  synthesis use revision-checked whole-day saves. See the validation doc for gates.
- **Prompt ratings are abandoned (2026-08-14)** — columns exist, 0 rows ever rated, no code
  ever wrote them. They stay (harmless); don't revive without a new idea.
- **Ask is mothballed, not deleted** — `web/api/ask.py` and the modal are reachable from
  `#/about`, and deleting it wouldn't even drop `ANTHROPIC_API_KEY` (Todos holds it).
- **Any future account split must *move* `~/.claude/prompt-history.db`, never copy it** — a
  second copy of every raw prompt is a privacy regression.
- **The recountly.org UptimeRobot monitor stays until raconte posts teardown notice** in the
  handoff channel — the site still answers 307; do not delete it as cruft.
- **Machine-voice convention:** AI-authored text renders italic + muted with `↳ from claude`.
- **Resend stays on Pro — 2026-09-07, consolidation CANCELLED.** The free plan rested on a
  wrong count (**11 domains, not ~37**) and `musicforge.org` was never on Resend. Return-path
  `send.` subdomains consume no slot; `span.`/`mail.` subdomains are separate entries.
  `musicforge.org`'s SPF must be **extended** (`include:icloud.com`), never replaced.
- **prompt-lab owns every repo's AGENTS.md format — 2026-09-18.** One form only: a dated
  provenance comment, "Read CLAUDE.md in this repo first", and the shared block, written by
  `workflow/bin/make-agents-md.sh`. Never a whole-file copy of CLAUDE.md. Codex Desktop's
  "import from Claude Code" wrote such copies wherever AGENTS.md was absent, with a blind
  Claude→Codex replace (`~/.claude` → `~/.Codex`); proven by second-level timestamp matches
  against `~/.codex/external_agent_session_imports.json`. Claude-side `/readup` creates an
  absent AGENTS.md and replaces an untracked importer copy (backup in
  `~/.claude/agents-md-backups/`), never commits either.
- **Codex gets one long-lived clone per repo (`~/src/<repo>-codex`), not worktrees —
  2026-09-19.** A worktree's `.git` sits outside Codex's sandbox root; a clone's doesn't.
  Main checkout adds it as remote `codex`; the clone's project name is aliased to the
  repo. Fleet guidance: `BULLETIN.md` 2026-09-19 entry.
- **Dual-agent commands (Claude Code + Codex) — 2026-09-12.** `workflow/commands/*.md` is the
  single source; `install.sh` distributes to `~/.claude/commands/` and renders
  explicit-only `~/.agents/skills/source-command-*/` skills (deprecated
  `~/.codex/prompts/` copies remain for compatibility). Codex readup falls back to the
  installed `session-context.sh`.
  Design: `docs/superpowers/specs/2026-09-12-dual-agent-commands-design.md`.

<!-- SHARED-CONVENTIONS:BEGIN v=e9c6d7e1aca0 — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->
## Shared conventions

<!-- These are Nico's cross-repo output rules. They're materialized into each repo's
CLAUDE.md and AGENTS.md so every agent (local, cloud, third-party) sees them as plain
text. Source of truth: prompt-lab/workflow/claude-md-shared.md — edit there and
re-sync, never here. -->

- **Clickable URLs.** When pointing at any web destination (dashboard, repo, PR, deploy, settings, docs, localhost), print the full bare URL — `https://example.com` or `http://localhost:8080` — on its own, never just the page's name and never a markdown `[label](url)` link. Nico's terminal auto-linkifies raw `https://` text, so a bare URL is one-click and stays copyable.

- **Number your questions.** Any time you ask Nico more than one question, present them as a numbered list (1., 2., 3.) so he can answer by number with no ambiguity. A single standalone question needs no number.

- **Self-contained smoke-test instructions.** When you ask Nico to manually test or verify an app or website, assume zero carried-over context — he should never scroll back or recall a URL/path/credential from earlier. Always include: the exact URL (full `https://…` or `http://localhost:…`, restated even if mentioned above), the precise steps in order, and what a pass vs. fail looks like. Repetition here is a feature, not clutter.

- **UTC at rest, Pacific on display.** Timestamps are stored in UTC, always. A *calendar day* shown to a human is `America/Los_Angeles` — Nico's day, and the clock the work actually happened on. The two rules that follow are the ones that get broken: never form a date bucket with `new Date(…).toISOString().slice(0,10)` (that is UTC, so every chart axis and "today" silently rolls over at 5pm Pacific — it put a phantom tomorrow bar on the Prompt Lab dashboard), and never bucket UTC-stamped rows with a bare `date(col)` in SQL. Use `Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' })` in JS and an explicit zone in SQL/Python. Storage in local time is also wrong — it can't be migrated across a DST boundary without loss.

- **No marker before a copy-paste command block.** Nico's terminal renders markdown bullets (`-`, `*`, `•`) as `●`, which breaks paste into zsh. The line directly above a fenced command block must be a plain-text label ending in a colon — never a bullet, dash, asterisk, or number. For loud copy targets, lead the label with `📋` + bold `COPY THE BELOW`, then a colon, then the block. Bracket anything Nico will paste elsewhere (a prompt for another agent, a multi-line command) with a ruler line of `================` above the label and below the closing fence. Rulers go outside the fence so they aren't copied, each with a blank line before it (a `===` line directly under text renders as a heading).

- **No bare backslash in a copy-paste command block.** A `\` is load-bearing shell syntax that renders invisibly and gets silently dropped somewhere between the markdown render, the clipboard, and zsh. `find … -exec test -e {} \; -delete` arrived in the terminal as `… {} ; -delete`, which zsh split into two commands and reported as `find: -exec: no terminating ";"` plus `command not found: -delete` (2026-09-20). Quote it instead — `';'` is exactly equivalent to `\;` and survives any copy path. For the same reason never break a command across lines with a trailing `\`: write one long line, however wide it wraps.

- **Codex branches are named `codex/<description>`.** When working in this repo via Codex CLI, always create a working branch under the `codex/` prefix (e.g. `codex/fix-flaky-test`) rather than working directly on `main` or an unprefixed branch. Claude Code has no visibility into other tools' running sessions (`ListAgents` only sees Claude sessions), so this prefix is the one signal a Claude session can check for — a local or remote `codex/*` branch means Codex has touched or is touching this repo, even though its session itself is invisible. Claude branches keep whatever naming they already use; only Codex adopts this new prefix.

- **Codex: run commands in a form a rule can match.** Codex approval rules match a command's leading tokens, so a wrapped command never matches an existing allow and every variant prompts again, then leaves a dead one-off "don't ask again" rule behind (36 of them in five days, 2026-09-23). The program is the first token: call helpers and tools directly, never through `/bin/zsh -lc "…"`, never with a `PATH=…` or other `VAR=…` prefix, never with `$(…)` in the arguments. Work only inside your clone (one long-lived `~/src/<repo>-codex`, no worktrees, no scratch clones — everything outside it escalates). Redirect output only to files inside the workspace, and keep temp files in a gitignored `tmp/` there, never `/private/tmp`. If a tool is missing from `PATH`, say so and stop; do not paper over it inline.

- **A review another agent must act on goes on the PR.** A review that another agent must act on, or that must outlive the session, is posted as a PR comment (`gh pr comment`), where the next session or agent finds it. Live, in-session reviews between Nico and the agent stay in chat. There is no devlog.md: the history DB is the one session record.
<!-- SHARED-CONVENTIONS:END -->
