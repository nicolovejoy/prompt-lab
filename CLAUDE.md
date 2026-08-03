# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
.venv/bin/python mobile/serve.py  # local mobile PWA → localhost:8080
```

The Flask local dashboard (`dashboard/`) was retired 2026-05-28 — it had gone ~3 months stale and none of the cost-tracking work landed there. The cloud dashboard (`web/`) is the single canonical UI. `todos.py` is kept as the shared scanner but is currently unwired (its only consumer was the local dashboard); rewire it into `web/` when todos return to the UI.

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
- `send-review.py` — nightly email via Resend, saves to review_snapshots
- `generate-report.py` — bi-monthly markdown report, saves to review_snapshots
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- **Data & access model: see `docs/data-and-access.md`** — the single coherent description of the three storage tiers (raw/private, processed/private, public), how public vs private is differentiated, the two-tier cloud auth, and how secrets grant access. Read it first when reasoning about what's stored where or who can see it.
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages. No read-time allowlist: it serves whatever rows exist in `public_session_summaries` / `public_weekly_rollups`, which are safe-by-construction (written only by the reviewed, git-committed draft-to-artifact flow — `scripts/draft_public_refresh.py` → human review → `scripts/publish_public_draft.py`, plus the original `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or raw sync). Allowlist is now the 6-key set (`ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase`) — `am-i-an-ai` dropped 2026-07-21 (site removed lojong, rows unpublished); the table `project` column is the consumer's historyKey, NOT the display slug. The invariant to preserve is "never write un-scrubbed text into the public_* tables." Curation of *which* projects appear publicly is the consumer's job — the `selected-projects` MDX manifest (`content/projects/*.mdx`) is the single source of truth for the public site. Unknown project → empty `200`. **Read-time counts projection (2026-07-21):** for a project with `project_metadata.public_counts=1`, the endpoint additionally overlays counts-only weekly rows projected from the private `weekly_rollups` (numeric columns only — no prose can leak) on weeks lacking a published prose row. Opt in via `scripts/seed_public_counts.py`.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with peer repos (selected-projects, prntd) via an append-only shared log living in the **standalone private git repo `nicolovejoy/handoff`**, cloned to `~/src/.handoff` (synced across mini + laptop). One file per pairing, each with a `repos: [a, b]` front-matter manifest. The SessionStart hook auto-injects the matching file's `## Active` section after a time-boxed best-effort pull, so you see pending notes without reading the file manually.

**Writing a cross-repo note** — never hand-edit + manually `git push`; use the wrapper so the pull-rebase/commit/push is atomic and conflicts surface loudly:

```
~/.claude/bin/handoff.sh append <file> "### YYYY-MM-DD <from> → <to>: <subject>

<body>"
```

It inserts the entry at the **top** of `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome (a normal Edit), then `~/.claude/bin/handoff.sh sync`. Exit codes: 0 ok · 3 conflict (kept local, resolve in `~/src/.handoff`) · 4 offline (kept local, re-run `sync` later). Design + 26/26 pressure test: `docs/handoff-repo-plan.md`, `workflow/handoff-sim/`.

## Next Steps

Shipped work is in git and in the code. What follows is only what isn't:
open work, traps that cost real time, and decisions not worth re-litigating.
The full chronological log lives in `docs/history.md`.

### Open

**The uptime archive wrote on 2026-08-01 and not on 2026-08-02 — DIAGNOSED
2026-08-02.** `uptime_daily` held 9 rows for Aug 1 and none for Aug 2. **The Aug 2
health email arrived**, which settles it: the cron fired, and the pull failed
silently in production. Not cron-dead.

The mechanism, and it is the interesting part: `_archive_uptime`
(`web/api/health_report.py:322`) returns `0` on every failure path — unset key, pull
exception, per-row write failure — logs to stdout and lets the email send. The row
count goes into `uptime_rows` in the **JSON response**, which only the cron's HTTP
caller ever sees, and **Vercel log retention is ~1 hour**. So a totally failed pull
is indistinguishable from a good one in the inbox. Aug 1 wrote 9 rows and nothing
deployed between the two days, so the key was live and this was transient —
plausibly the 8-second `FETCH_TIMEOUT` on the v2 call.

**Fixed 2026-08-02:** the row count now lands in the email body — `9 monitors
archived` normally, a loud red `uptime archive: 0 rows written` when the pull
failed (`_compose` takes `uptime_rows`; dry runs pass None and show nothing).
Same-morning and thresholdless. The `uptime archive` heartbeat from `b179cc1`
remains the backstop for "cron alive, pull broken" at a 2-day threshold.

- **Phase 3 of the uptime plan — COMPLETE 2026-08-02.** musicforge, bakerylouise and
  prntd all shipped `/api/health` and every monitor is repointed off its homepage
  (musicforge's lives only on `www.musicforge.org` — the `.app` domain 404s the path;
  bakerylouise skips the deep Sanity variant on purpose, ISR-cached; prntd is deep
  `?db=1`). raconte is settled: no backend ever, slot closed, the recountly.org
  monitor stays until they post teardown notice.
- **Phase 5 — COMPLETE 2026-08-02.** `TARGETS` now carries all 8 HTTP monitors, and
  a test pins `TARGETS` ⊆ `HTTP_MONITORS` (subset, not equality — paging may
  legitimately cover more than the daily email). Two things fell out of the growth:
  the deep parser knew only `db`/`howl` and rendered ibuild4you, byside and
  pianohouse note-less, since those return the convention's other shape, a
  `checks[]` array — it now summarizes `n/m checks ok` and names only the failures;
  and the poll fans out over a thread pool (`_check_targets`), because sequential
  polling is ~8s at eight targets and `#/health` pays it on every load. 1.6s
  measured. Four older tests that pinned the literal 2-target set now derive from
  `TARGETS`.
- **garm #7 denial-count line** in the health email (`GARM_REPORTING_KEY` shipped on
  garm's side; the garm handoff channel will post the shape).
- **`#/health` has never been visually verified** — both themes were checked by
  computed contrast, not by eye. https://prompt-labs.org/#/health
- **Beacon fan-out: `prntd` + `musicforge`** never got the snippet (dirty trees at
  fan-out time). `page_views` has zero rows ever for either. musicforge is Vite
  (`frontend/src/main.tsx`), a different injection than the Next.js root layouts.
- **`/api/private_history` Tier 1 — SHIPPED 2026-08-02**, deployed and verified live
  end-to-end (auth'd smoke test passed). `SERVICE_HISTORY_KEY` in Vercel Production,
  value at `op://dev-secrets/prompt-lab-service-history-key/password`. Ball is in
  selected-projects' court to wire `lib/history.ts`. Tier 2 (narrative behind Garm)
  remains unbuilt by agreement. historyKey settled as `bakerylouise` (alias from
  `bakerylouise-v1`); allowlist is 8 keys (`bakerylouise`, `songscribe` added).
- **Public rollups:** only ibuild4you `2026-05-18` remains unpublished, and that is a
  deliberate skip (cost forensics + internal ops; nothing left after scrubbing). It
  reappears in every future draft by design.
- **#48 time localization, soup to nuts** (filed 2026-08-02, slated for a Fable
  session). UTC, naive-local and Pacific are mixed across the pipeline with nothing
  declaring which clock owns a value: the synthesizer and review email write dates in
  mini-local Pacific, `health_report.py` grades their freshness in UTC, and the "8am"
  cron is `0 15 * * *` — 8am Pacific in summer, **7am in winter**. Decide the policy
  before fixing instances. The handoff commit-capture instance is patched
  (`--since="<started_at>Z"` in `workflow/commands/handoff.md`, 2026-08-02), and two
  more landed on the issue the same evening: `today-counts` reads 0 prompts/sessions
  after 5pm PDT, and `prompts` (local-naive) vs `sessions` (UTC-naive) disagree on
  which clock their timestamps are on.
- Open issues: **#14** design tokens (own session), **#27** Garm rollout, **#43**
  sign-ins panel (trigger-gated: fires the day a second reader joins
  `READER_EMAILS`), **#9** beacon fan-out, **#34** health leftovers, **#45** the
  freshness convention.
- Deferred deliberately: UptimeRobot paid plan / real `HEARTBEAT` monitors.

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

Three rules that fall out of it, each earned:
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

Known hole, don't mistake it for closed: the `uptime archive` heartbeat is written and
graded by the *same* request, so it catches "cron alive, pull broken" and cannot catch
"cron dead." That case degrades to "no email arrived," the weakest signal in the
system. Closing it needs a check on infrastructure that fails independently of
Vercel's scheduler; UptimeRobot's `HEARTBEAT` type is paid-only, which is what sent
#45 down the artifact route in the first place.

### Invariants — the things that must not be broken

- **Turso holds no `prompts`, `sessions`, or `commits` tables at all.** Raw prompt
  text, commit messages, hostnames and local paths are physically unreachable from
  `web/`. That is the strongest guarantee in the system. Preserve it by never adding a
  sync leg — not by filtering at read time. Read-time allowlists were tried twice and
  deleted both times for drifting.
- **Cloud-direct tables have no leg in `sync_to_turso.py` and must never gain one:**
  `page_views`, `health_email_state`, `project_metadata`, `issue_categories`,
  `uptime_daily`. That absence is what makes drift structurally impossible.
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

### Traps that cost real time

- **Turso returns `SUM()`/`COUNT()` aggregates as JSON strings.** An explicit `int()`
  coalesce is load-bearing — without it chart math concatenates instead of adding.
- **UptimeRobot v2's `custom_uptime_ratio` is a string** (`"100.000-99.980-99.990"`,
  1d-7d-30d). Split and float, or every downstream average is text.
- **The SPA catch-all serves `index.html` with a 200 for unknown paths.** A health
  target pointed at a nonexistent path becomes a permanent false UP. Health targets
  must also be unauthenticated — the first health email false-DOWNed prompt-labs.org
  by polling auth-gated `/api/info`.
- **`vercel env add` takes no value argument** — it opens an interactive prompt and
  reads one line from stdin, so the trailing newline is the *submit*. Never pipe
  through `tr -d '\n'` (it blocks forever, writes nothing, exits without error) and
  never wrap it in a `for` loop (the first prompt seizes the TTY). Always verify with
  `vercel env ls`: a good write reads seconds old.
- **`op inject` substitutes `op://` references inside `#` comments** — a commented
  reference is still live, and one unresolvable ref aborts the whole file. And
  `op inject -i .env.tpl -o .env.local` is **not** a working workflow here: the
  template is the union of local + cloud secrets, so regenerating locally tries to
  materialize cloud-only values. Append single variables instead.
- **The public-draft path regex only matches `/Users/…`.** Tilde paths (`~/src/…`)
  sail straight through — a human-only catch.
- **Reading `/api/public_history`: the envelope key is `rollups`, not
  `weekly_rollups`.** A probe using the wrong key reports 0 rows on a healthy endpoint.
- **A missing site in `#/visitors` is a hole, not a zero.** recountly showed zero rows
  for weeks because the beacon had never once fired, not because there was no traffic.
- **prntd's domain is `.org`, not `.com`.** pianohouse must be monitored at **www**,
  not the apex — the apex 307s, and a monitor leaning on redirect-following is one
  setting away from a false DOWN.
- **Vercel log retention is ~1 hour.** Post-hoc forensics on a daily cron is not
  available.
- **CI ruff is pinned to `0.15.22` — don't unpin.** An unpinned `pip install ruff`
  grabbed a new release and produced 339 new-rule errors on a docs-only push. Local
  ruff passing while CI fails on a docs commit = version drift; check the pin first.
- **`deploy` has `needs: test`**, so a starved or failing test run shows as *skipped*,
  not failed, and no prod deploy goes out silently.
- **Three Vercel diagnostics that produce false conclusions — don't reuse them:**
  `gh api repos/:owner/:repo/hooks` is no evidence about Vercel linkage (Vercel
  connects via a GitHub App, which creates no repo-level webhooks — check `link` on
  `GET /v9/projects/<id>`); grepping served HTML for `_vercel/insights` false-negatives
  on any current site (`@vercel/analytics` 2.x uses a randomized anti-adblock path);
  and `githubCommitSha`/`githubCommitRef` on a deployment do **not** imply a git
  trigger (the CLI stamps local checkout metadata onto manual deploys). The real tell
  for "never linked" is zero preview deployments across the project's whole history.

### Testing

Tests are standalone runners, **not pytest** — `python -m pytest` fails at collection.
Run each directly:

```bash
for f in scripts/test_*.py; do .venv/bin/python "$f"; done
```

222 tests as of 2026-08-02 (150 in `test_web_api.py`, plus alias-layer 22,
cost-pipeline 22, public-draft 21, heartbeat 7, imports, session-identity).
`_health_mod(up=, hb=, ur=)` stubs the health endpoint; its Turso stub dispatches on
the SQL because the pause lookup, the freshness lookups and the uptime upsert share
`turso_query` and must not be conflated — pause fails open, freshness fails loud, and
the archive write must be separately observable.

### Settled — don't re-litigate

- **UptimeRobot is the sensor AND the pager; prompt-lab samples nothing and pages for
  nothing.** 5-min polling on independent infra, free tier, 3-month retention. Ratified
  in garm's 2026-07-29 handoff: prompt-lab shares the Vercel+Turso+Resend stack, so a
  watcher built on it would die with the watched. No Pi, no launchd sampler.
  API facts, probed live (the published docs are thin and partly wrong): **v3
  provisions but has no history endpoints** (`/logs`, `/response-times`, `/uptimes` all
  404); **v2 legacy is the only source of history** and works on free; `HEARTBEAT` type
  needs a paid plan (403 `009-005` at every interval and grace value); free tier is 50
  monitors, 5-min interval, 10 req/min, 3-month retention.
- **OAuth is hand-rolled in Python, zero new deps.** Because this is a confidential
  client doing its own server-side code exchange, the `id_token` arrives from Google
  over TLS — no JWT signature verification, no JWKS fetch, no crypto dependency.
  Rejected: Next.js conversion, mixed Node+Python runtime, third-party auth. Spec in
  `docs/phase2-oauth-plan.md` — read it before touching auth. `verify_token` requires
  both `role` and `email` **keys** (key-presence, not truthiness) — that subtlety is
  load-bearing.
- **No display names in the sign-ins panel.** With two accounts the beacon role already
  identifies the person, and a name would cost the log's anonymity. #43 tracks the
  trigger: when a second reader joins, the fix is a stable **opaque per-user id** (HMAC
  of email under a server salt, like `visitor_hash`) — never an email or a name.
- **First-party beacon over Vercel Analytics.** Drains are Pro-only and Hobby Analytics
  has no read API, so it could never feed a unified dashboard. The beacon is also
  hosting-neutral and writes cloud-direct.
- **The public tier's curation is the consumer's job** — the `selected-projects` MDX
  manifest is the single source of truth for which projects appear publicly.
  `docs/public-allowlist.txt` mirrors it and gates *writes*, not reads.
- **The public-draft division of labour:** the machine refuses to publish on anything
  regex-able (absolute paths, emails, credential tokens, internal DB hosts, unedited
  blockquotes, prose <15 words, prose ≥75% similar to the private source). The human
  owns the four things regexes structurally cannot see: **named people/orgs,
  identifiability-by-description, unreleased plans stated as fact, and commercially or
  personally sensitive detail.**
- **`private` on `project_metadata` is cosmetic only** — a hide-toggle, not the
  public-data gate, and it does not gate any API. `public_counts` is the real gate.
- **Machine-voice convention:** any AI-authored text renders italic + muted with a
  `↳ from claude` marker.

<!-- SHARED-CONVENTIONS:BEGIN v=d5e16e653242 — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->
## Shared conventions

<!-- These are Nico's cross-repo output rules. They're materialized into each repo's
CLAUDE.md so every agent (local, cloud, third-party) sees them as plain text. Source
of truth: prompt-lab/workflow/claude-md-shared.md — edit there and re-sync, never here. -->

- **Clickable URLs.** When pointing at any web destination (dashboard, repo, PR, deploy, settings, docs, localhost), print the full bare URL — `https://example.com` or `http://localhost:8080` — on its own, never just the page's name and never a markdown `[label](url)` link. Nico's terminal auto-linkifies raw `https://` text, so a bare URL is one-click and stays copyable.

- **Number your questions.** Any time you ask Nico more than one question, present them as a numbered list (1., 2., 3.) so he can answer by number with no ambiguity. A single standalone question needs no number.

- **Self-contained smoke-test instructions.** When you ask Nico to manually test or verify an app or website, assume zero carried-over context — he should never scroll back or recall a URL/path/credential from earlier. Always include: the exact URL (full `https://…` or `http://localhost:…`, restated even if mentioned above), the precise steps in order, and what a pass vs. fail looks like. Repetition here is a feature, not clutter.

- **No marker before a copy-paste command block.** Nico's terminal renders markdown bullets (`-`, `*`, `•`) as `●`, which breaks paste into zsh. The line directly above a fenced command block must be a plain-text label ending in a colon — never a bullet, dash, asterisk, or number. For loud copy targets, lead the label with `📋` + bold `COPY THE BELOW`, then a colon, then the block.
<!-- SHARED-CONVENTIONS:END -->
