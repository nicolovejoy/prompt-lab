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
- `send-review.py` — nightly email via Resend; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `generate-report.py` — bi-monthly markdown report; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- **Data & access model: see `docs/data-and-access.md`** — the single coherent description of the three storage tiers (raw/private, processed/private, public), how public vs private is differentiated, the two-tier cloud auth, and how secrets grant access. Read it first when reasoning about what's stored where or who can see it.
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages. No read-time allowlist: it serves whatever rows exist in `public_session_summaries` / `public_weekly_rollups`, which are safe-by-construction (written only by the reviewed, git-committed draft-to-artifact flow — `scripts/draft_public_refresh.py` → human review → `scripts/publish_public_draft.py`, plus the original `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or raw sync). The allowlist (`docs/public-allowlist.txt`) is an 8-key **write-time publish gate**, not a read gate — `publish_public_draft.py` refuses to publish an off-list project, and `check_public_allowlist.py` audits published rows against it. Current keys: `bakerylouise, ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase, songscribe` (`am-i-an-ai` dropped 2026-07-21 when the site removed lojong and its rows were unpublished). The table `project` column is the consumer's historyKey, NOT the display slug. The invariant to preserve is "never write un-scrubbed text into the public_* tables." Curation of *which* projects appear publicly is the consumer's job — the `selected-projects` MDX manifest (`content/projects/*.mdx`) is the single source of truth for the public site. Unknown project → empty `200`. **Read-time counts projection (2026-07-21):** for a project with `project_metadata.public_counts=1`, the endpoint additionally overlays counts-only weekly rows projected from the private `weekly_rollups` (numeric columns only — no prose can leak) on weeks lacking a published prose row. Opt in via `scripts/seed_public_counts.py`.
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

**Garm: HARDEN-THEN-FREEZE — Nico's decision 2026-08-27, don't re-litigate
the unwind question.** He seriously considered unwinding Garm ecosystem-wide
(triggered by the grant-seeding lockout gap) and chose: keep it, harden the
two operational risks, then freeze the rollout until real demand. Posted to
`~/src/.handoff/garm-prompt-lab.md` 2026-08-27. What that means here:

- **Frozen indefinitely:** `GARM_GATING` stays **off**; `READER_EMAILS`
  remains the live gate. Grant seeding (Pierre → `prompt-lab.prntd`, the
  brother) is DEFERRED, no longer blocking anything. Task 9 smoke test
  deferred with it. No new consumers, no admin UI (build-plan #8), and the
  2026-08-23 dashboard-panel offers (per-person access lookup, usage panel,
  `GARM_REPORTING_KEY` handover) are deferred with thanks. Revisit trigger:
  a real second user who needs actual access management, not "might someday."
- **Harden asks, garm-side, pending in the handoff channel:** (1) answer +
  document where the admin key lives — narrowed for them 2026-08-27:
  1Password `dev-secrets` has no `garm-admin-key` item, only a bare `garm`
  item it might be a field on (titles checked from here; the classifier
  correctly blocked opening the item); (2) free-tier Neon is a mismatch for
  fail-closed auth (this month's 100% CU-quota near-miss) — either Nico
  upgrades the plan or garm proposes a softer failure posture (longer
  consumer grant caches).
- PR #54 stays merged/deployed (it's inert with gating off — 97 lines of
  helpers built kill-switch-first, so gating-off IS the unwound behavior for
  free). Decisions from 2026-08-22 stand unchanged for whenever the freeze
  lifts: namespaced dot slugs, reader = ≥1 `prompt-lab.*` grant, admin-only
  `#/health`/`#/visitors`/uptime, 10-min revocation, admin bypass. "Reverse
  lookup" (who has access to project X) remains ruled out — blast radius.

**Resend: STAYING ON PRO — Nico's decision 2026-09-07, consolidation
CANCELLED. Don't re-litigate.** The paid→free plan was built on a wrong
count: the account had **11 domains, not ~37**, and `musicforge.org` — which
Nico wants as its own sending domain ("my most popular app") — was never on
Resend at all, so free's 3-domain cap would have needed a fourth slot on day
one. $20/mo Pro is the cheapest paid tier (Free is $0 / 3 domains / 100
emails a day; Pro is 10 domains, no daily cap, 50k/month account-wide).

Applied 2026-09-07: four dead domains deleted by hand (`free-vite.com`,
`send.anomatom.com`, `soiree.pianohouseproject.org`, `send.notemaxxing.net` —
the last confirmed dead by notemaxxing's own "daily-send shutdown" commit and
zero sends since Aug 15). Seven remain, three under Pro's ten, with room for
`musicforge.org`. Nothing moves: `prompt-labs.org` keeps sending the health
email (`HEALTH_FROM_EMAIL` default at `web/api/health_report.py:897`); the
review email stays on `reviews@mail.pianohouseproject.org` where it landed
2026-09-06, because moving it back buys nothing.

Two facts worth keeping from the cancelled plan, both verified against the
API: a return-path `send.` subdomain does NOT consume a domain slot (it is a
record inside the parent's entry); and the key is account-wide, so any
consumer can send from any verified domain with no DNS work. The
"subdomains are separate slots" finding is also true — `span.` and `mail.`
`pianohouseproject.org` are two entries — it just no longer matters.

musicforge verifies `musicforge.org` itself. The one trap, flagged to them:
that domain carries Nico's iCloud mail, so its SPF must be **extended**
(`include:icloud.com` plus Resend's include), never replaced. Cancellation
notes went to byside, span, ibuild4you, selected-projects and nudge the same
day; the 2026-09-03 cloud-drafted plan branch is deleted.

Heads-up notes posted 2026-09-06 to byside, span, ibuild4you, selected-projects
and a new `nudge-prompt-lab.md` channel. Still open: Nico's final mothball list.

**The nightly pipeline's wake/DNS failure was found and fixed 2026-09-06** —
narrative in `docs/history.md`, the generalizable trap in Traps below.

**Two consequences to know, neither a bug:**

- **Escalation is one day late for a single dead night.** The morning after, the
  record still cannot have been pushed, and the newest remote row is age 1,
  which passes. The red email arrives the following morning with the catch-up.
  Two consecutive dead nights escalate on time via the age rule — which is what
  the 2 -> 1 change is actually for, so do not "simplify" it back.
- **A bad night stays red for up to 7 days and there is no acknowledgement
  path.** Re-running that date manually adds a row, it does not clear the old
  one. Loud-for-a-week was chosen deliberately over silent-forever.

The three follow-ups deferred from this fix (cover the `_apply_recent_bad`
note-append branch, pin `NIGHTLY_RUN_WINDOW_DAYS == 7`, null-host guard on
backfilled rows) all landed 2026-09-07.

**`docs/nightly-pipeline-plan.md`: steps 1, 2, 3 and 5 are DONE (2026-08-29,
narrative in `docs/history.md`).**
Step 4 remains mostly absorbed (report catch-up done; reader catch-up
otherwise still optional) and unbuilt beyond that.

**Still outstanding: step 2's sleeping-host test**, and it needs a real
overnight rather than a healthy awake host (an awake, online laptop passes it
either way, which is exactly why it needs staging). With the machine
deliberately asleep across 02:30, confirm one wake produces one run in the
correct order and Turso's newest `review_snapshots` date equals the run date.
Note the network gate now sits in front of this, so a sleeping-host run should
show a `--- network: resolved after Ns ---` line rather than a stage dying on
`gaierror`; that line is itself the evidence the gate is earning its place.

Also still unverified until it happens: the health-email changes are
Vercel-side code reading Turso, so the first real morning email carrying a
`nightly_runs` row is their acceptance test — **and it does not run until the
merge is pushed and deployed.**

**mini-rescue curation — open, unhurried.** `~/src/mini-rescue/` holds 13
rescued repos; walk them at leisure, merge-or-discard, delete each folder as
judged (the dir emptying is the progress meter). Settled 2026-08-17, don't
revisit: freevite IS invitekit under its old name, left to rest (its last
commit lives only in that local copy — remote is archived, deliberately not
pushed); roll-your-own (GitLab, no auth) and skitrack-ntzb-poc (third-party
remote) also deliberately unpushed. Two loose ends from the rescue: the
agent installed git-lfs globally (Homebrew) to get rock-art-fab pushed, and
musicforge's lilypond submodule edits went to the shared
`neonscribe/lilypond-lead-sheets` repo on a rescue branch. Also still to
delete: the dead-token copy in `~/mini-staging/home/zshrc.mini`.

**garm hit the same Neon-CU bug as byside — found 2026-08-18, fixed same day
by the garm side.** Neon alerted that `neon-bole-tree` (garm's DB, project
`steep-glitter-55844373`) used 100% of its 100 CU-hour monthly quota with
12+ days left before reset — confirmed by the math (0.25 CU × 1,453,008
active-seconds ÷ 3600 = 100.9 CU-hours, exact match). Same root cause as
byside below: `scripts/uptimerobot.py` deep-polled
`garm.prompt-labs.org/api/health?db=1` every 5 minutes, never letting Neon's
free-tier autosuspend kick in. Filed to `~/src/.handoff/garm-prompt-lab.md`;
commit `59ea622` ("garm's health check stops paying to keep Neon awake")
landed same day. Since consumers fail closed on a garm outage, this wasn't
just a cost problem — worth confirming next month's CU number actually drops
like byside's did, same as the open byside check below.

**One small follow-up from 2026-08-14, not urgent.**

*byside's Neon bill.* The deep health poll was consuming 80 of byside's 100
monthly CU-hours (Neon free tier autosuspends after 5 min idle; we polled at
5 min, so it never slept). Monitor is shallow now and applied live — **check
the September CU number to confirm the drop**, since nothing alarms on it. The
transferable rule, filed in `scripts/uptimerobot.py`: deep coverage over an
autosuspending DB needs an interval **longer than the suspend window**, not a
deeper URL, because polling at the suspend interval makes the check circular —
it keeps the database warm and then reports that the warm database answers.
Notified byside; their route comment still calls the deep check "cheap enough
to poll every 5 minutes", which is true of the function and false of the
compute.

**Per-Pi service inventory — promoted to `docs/pi-inventory.md` 2026-09-07.**
What runs on phrpi and homeassistant.local, their two addresses each, and the
traps that go with them. prompt-lab owns that document; read it before touching
either box.

Closet move DONE 2026-08-13 — both Pis wired, both deliberately dual-homed,
all four interfaces DHCP-reserved. What's left, none of it prompt-lab's code
and all of it filed in `~/src/.handoff` (new channels
`home-assistant-prompt-lab.md` + `phrpi-lights-prompt-lab.md`):
- **Laptop SSH key into HA's add-on.** The highest-leverage one: today's HA
  work ran on screenshots and inference while phrpi got measured in seconds.
  Everything else about that box stays guesswork until this lands.
- **Repoint hardcoded `192.168.5.34`** → `homeassistant.local` in
  phrpi-lights and the home-assistant repo.
- **`cloudflared`'s token out of argv** on phrpi (owner unclear — the
  container's compose dir wasn't traced; not filed anywhere yet).

**Copy review (#49) — batches 2–4 remain.** Batch 1 closed 2026-08-05 (narrative
in `docs/history.md`). The review runs page by page at a computer, 3-5 items at a
time. Nico answers by number and often stops mid-batch, so **track which items
were actually answered, not which batch was sent** — the first pass through this
lost two items by recording the batch as finished. Left to do: batch 2 (Activity +
the day page), batch 3 (Costs, Visitors, Todos), batch 4 (Health, About, project
pages). One open question the batch-1 rework raised, still unsettled: with Ask
gone from the primary row, `More` guards a single destination plus your identity,
so a plain `About` button in the primary row may be simpler than the panel.

**Follow-ups the 2026-08-05 project-name cleanup surfaced (narrative in
`docs/history.md`), all unconfirmed and needing Nico's memory of
which directory he was actually in** — the names alone aren't evidence:
`koma_art`/`koma-launch` look like the same underscore/dash pair fixed
elsewhere; `freevite` (167 prompts, dormant) may be `invitekit` under an older
directory name, since invitekit deploys to `freevite.vercel.app`; and `spike`
(4 prompts) has the same shape as the hidden artifacts.

**`ACTIVE · N` counts hidden projects.** `activeCount` is `activeList.length`
with no `private` filter (`web/index.html:1165-1167`), and it also feeds the
`active projects` KPI tile (`:1191`), so the home screen read `37` when 16 were
shown and 21 were hidden junk. Chips honor the toggle; the counts don't. The fix
is one filter, but the semantics are a real choice: excluding private is
obviously right while `private` holds only artifacts, and wrong the day a
genuine project is marked private. Alternative is `37 · 16 shown`. Undecided.

Open, from the 2026-08-02 uptime/health thread and the issue backlog:
- **`#/health` has never been visually verified** — both themes were checked by
  computed contrast, not by eye. https://prompt-labs.org/#/health Also unseen:
  **the nav below 640px** — the hamburger path. The 2026-08-05 verification was
  done at a computer, so it covered the wide layout only, and the phone markup is
  a separate CSS branch. (`#/about` and the More panel are verified.) **This sandbox
  cannot render the app at all** — `index.html` pulls Preact from `esm.sh` at
  runtime and the network policy blocks it, so every frontend change here is
  verified by `node --check` over the extracted module plus class-usage greps, and
  needs your eyes before it is real. Don't mistake "tests pass" for "it looks right."
- **Beacon fan-out: `prntd` + `musicforge`** never got the snippet (dirty trees at
  fan-out time). `page_views` has zero rows ever for either. musicforge is Vite
  (`frontend/src/main.tsx`), a different injection than the Next.js root layouts.
- **Public rollups:** only ibuild4you `2026-05-18` remains unpublished, and that is a
  deliberate skip (cost forensics + internal ops; nothing left after scrubbing). It
  reappears in every future draft by design.
- **#48 residual:** the "8am" cron is `0 15 * * *`, which is 8am Pacific in summer
  and **7am in winter** — Vercel crons are UTC-only, so this is a choice to make
  (accept the winter hour, or split the schedule), not a bug to fix.
- Open issues: **#14** design tokens (own session), **#27** Garm rollout, **#43**
  sign-ins panel (trigger-gated: fires the day a second reader joins
  `READER_EMAILS`), **#9** beacon fan-out, **#34** health leftovers, **#45** the
  freshness convention, **#50** preload + locally cache per-day aggregates (the
  day page fetches cold and feels sluggish on a phone), **#49** copy review across every dashboard page (filed
  2026-08-02 at Nico's ask — he wants to read it at a computer, not a phone),
  **#51** unmapped costs, **#52** exclude test-agent traffic from `page_views`
  (both filed 2026-08-08 off Nico's backlog list; same list also settled: Ask's
  per-user history is parked with Ask itself, and the selected-projects commit
  counts wait on *their* repo wiring `lib/history.ts`).
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

### Traps that cost real time

- **`workflow/bin/_gc_project.sh` is the ONE project-resolution implementation
  for `gc-read.sh`/`gc-write.sh`** (landed 2026-09-07; both used to take
  `basename $PWD`, so from an agent worktree `current-session`/`today-counts`
  silently read empty and `/handoff` wrote that emptiness into a summary). It
  mirrors `log-prompt.sh`: `--git-common-dir` (never `--show-toplevel`), only
  git exit 128 buckets to `scratch`, never an empty name. A drift-guard test
  greps both scripts for the `source`. **The mini still has the old copies** —
  next time anyone is on it, copy all three files into `~/.claude/bin/`.

- **`workflow/bin/*` and `workflow/commands/*` run from installed copies under
  `~/.claude/`, not from the repo.** A fix committed to the repo is not live
  until copied over (per machine!). Bit hard 2026-08-10: the Monday week-bug
  fix landed in `workflow/bin/gc-read.sh` while the installed copy kept the
  buggy SQL, and `/handoff`'s rollup check invented two phantom missing weeks
  from Monday-dated summaries. After fixing anything under `workflow/`,
  diff-sweep: `for f in workflow/bin/* ; do diff -q "$f" ~/.claude/bin/$(basename "$f"); done`
  (and the same for commands) — on BOTH machines.

- **`tail -r` is BSD-only; CI is Linux.** `log-prompt.sh` reversed the
  transcript with `tail -r`, which works on the Macs it actually runs on and
  silently produces nothing everywhere else — so `prompts.context` was empty on
  any Linux host and nobody knew, because no test asserted on the column until
  2026-08-14. The hook now detects (`tail -r /dev/null` → else `tac`). The
  general lesson: a macOS-only shell idiom in `workflow/` is a latent bug the
  moment the code touches a Pi (phrpi is Debian) or CI, and it fails by
  producing empty output rather than an error.
- **A Vercel-origin service behind Cloudflare bot protection fails ~95%, not
  100%, and the partial failure impersonates a rate limit.** Diagnosed on SPAN
  2026-08-21. Vercel egresses from a rotating pool of AWS IPs; Bot Fight Mode
  scores each independently, so a check occasionally draws an unchallenged IP,
  succeeds once, then fails again on the next draw. That produced UP windows of
  exactly one check interval separated by multi-hour DOWN runs, with gaps
  regular enough (three consecutive at 2:07:4x to the second) that both agents
  on the incident independently reached for "refilling budget / rate limit."
  It was IP roulette. Cloudflare's firewall-events export settles it in
  seconds — read `ruleId`/`source`/`action`, don't infer the control from the
  failure pattern.
- **Two sampling traps from the same incident, both of which produced confident
  wrong answers.** A probe of 10 requests at 3s intervals spans 30 seconds and
  cannot distinguish "blocked 100%" from "~5% pass rate spread over hours" — at
  p=0.05, 10/10 failures is the *expected* result ~60% of the time. And
  UptimeRobot's v2 log caps at **25 entries** regardless of `logs_limit`, while
  Cloudflare's firewall-events export caps at **500** — so neither bounds an
  onset time, and the oldest visible entry is a cap artifact, not a start.
  Before accepting any peer's "we tested it, it isn't that", ask what sampling
  window produced it.
- **A failure whose own cause also blocks its reporting path erases its own
  evidence.** The nightly wake/DNS deaths (2026-09-06) could not push their own run
  records, so the grader never received the row and the email stayed green. No care
  in the grader helps: fix it on the reading side — grade a WINDOW, not the newest row.
- **A scheduler is not a dependency mechanism.** launchd coalesces missed
  `StartCalendarInterval`s onto one wake, so agents scheduled 45 minutes apart start
  simultaneously after a closed-lid night. Ordering belongs in `nightly_pipeline.py`,
  never in the plist times.
- **Never enforce a timeout on wall-clock time on a host that sleeps.** `time.time()`
  counts sleep; the monotonic clock httpx uses for its read timeout does not. The
  "3h19m API call" of 2026-08-20 was a healthy 136s run stretched across a sleeping
  Mac — a wall-clock deadline would have aborted a good run every night.
- **`source <file> && python …` in a plist silently runs nothing** when the file is
  absent. That `&&` short-circuit killed the bi-monthly report twice (four months
  once, then again on the mini). Every reader calls `load_env()` itself, so the
  `source` was always redundant — invoke python directly through `run-nightly.sh`.
- **SQLite's `weekday N` means next-or-SAME day.** `date(<d>,'weekday 1','-7 days')`
  returns the *previous* Monday when `<d>` is already a Monday, which filed every
  Monday under the wrong week. The correct bucket is `date(<d>,'weekday 0','-6 days')`.
  A `clocks:` test greps `'weekday 1'` out of all four homes of this expression.
- **Turso's `daily_summaries.prompt_version` is perpetually NULL by design** —
  `merge_summary_parts()` in `sync_to_turso.py` omits it deliberately (local
  provenance, no cloud reader needs it). Not a broken sync leg; don't "fix" it.
- **`review_snapshots` records composition, not delivery.** A failed send still writes
  the row, and the #45 heartbeat structurally cannot see a last-step delivery failure
  because the artifact is upstream of it.
- **`scripts/uptimerobot.py --apply` always exits 1** — the 4 HEARTBEAT creates fail
  every run (3× 403 paid-plan, 1× 400 `gracePeriod > 86400`). Cosmetic, but it trains
  you to ignore the exit code; read the output, not the status.
- **`/api/private_history` has no allowlist of its own** — it accepts any project and
  is gated solely by `SERVICE_HISTORY_KEY`. Don't go looking for one; the 8-key
  allowlist is the *public* tier's write gate.
- **Load-shedding is not available on our side.** The `deep` flag in
  `web/api/health_report.py` is *descriptive* — it mirrors `?db=1` in the URL, and
  `_check_target()` issues the request either way. Reduction comes from editing the
  URL, never from flipping the flag.
- **When two sources disagree about *when*, suspect a display timezone** before
  suspecting either party's reading. UptimeRobot's account display was UTC-10, and an
  authoritative-sounding wrong timestamp cost two rounds of cross-agent confusion.
- **Restart Home Assistant before believing its Network-adapter panel.** HA builds the
  adapter list at startup, so the panel reads *stale, not wrong* — it showed `wlan0`
  only for days after the ethernet cable went in.
- **A UI list is evidence about the UI, not about every credential in the system.**
  HA's token card listing one long-lived token was read as "there is only one"; the
  authoritative test is whether the consumer still authenticates.
- **Prompt counts step up once on 2026-08-14** and the step is real. Before that date
  a write-time filter dropped every prompt under 20 characters; after it, nothing is
  dropped. `CAPTURE_FIX_DAY` + the `.heatmap-note` caption say so on the chart, and
  backfill is impossible — the dropped prompts were never stored.
- **Any overlay positions against the layout viewport**, so a `position:fixed` sheet
  slides off-screen under pinch-zoom exactly like an absolutely-positioned panel. On a
  phone, prefer a real route over a modal.
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

~243 tests across 7 files as of 2026-08-04 (162 in `test_web_api.py`, plus alias-layer
22, cost-pipeline 22, public-draft 21, session-identity 9, heartbeat 7, and
`test_imports.py`, which is an import smoke script with no test cases).
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
- **The nightly jobs run on the LAPTOP and nowhere else, and there is exactly one
  sender** (2026-08-20). Never load the readers on two machines or Nico gets two
  emails a night. The mini runs nothing for prompt-lab: it sleeps through the night
  and its raw DB is frozen at the 2026-08-12 snapshot.
- **DB ownership is federated — Option B, 2026-08-10.** Raw prompts stay machine-local
  by invariant; each machine synthesizes its own and pushes processed rows to Turso,
  which is the merge point. `daily_summaries` clobber is solved by the per-machine
  parts table; `weekly_rollups` still has the same shape, deferred until it bites.
- **Prompt ratings are abandoned (2026-08-14).** `utility`/`tags`/`notes`/`outcome`
  and `idx_prompts_utility` exist in the live DB, 0 rows have ever been rated, and no
  code has ever written them. The columns stay (harmless); don't revive the aspiration
  without a new idea — a one-word in-the-moment marker, or deriving utility from outcome.
- **Ask is mothballed, not deleted.** `web/api/ask.py` and the modal are untouched and
  reachable from `#/about` and the `/` shortcut. Deleting it would not even drop the
  `ANTHROPIC_API_KEY` dependency, which the Todos classifier holds.
- **Any future account split must *move* `~/.claude/prompt-history.db`, never copy
  it** — a second copy of every raw prompt is a privacy regression.
- **Machine-voice convention:** any AI-authored text renders italic + muted with a
  `↳ from claude` marker.

<!-- SHARED-CONVENTIONS:BEGIN v=e5fb79b2ef4d — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->
## Shared conventions

<!-- These are Nico's cross-repo output rules. They're materialized into each repo's
CLAUDE.md so every agent (local, cloud, third-party) sees them as plain text. Source
of truth: prompt-lab/workflow/claude-md-shared.md — edit there and re-sync, never here. -->

- **Clickable URLs.** When pointing at any web destination (dashboard, repo, PR, deploy, settings, docs, localhost), print the full bare URL — `https://example.com` or `http://localhost:8080` — on its own, never just the page's name and never a markdown `[label](url)` link. Nico's terminal auto-linkifies raw `https://` text, so a bare URL is one-click and stays copyable.

- **Number your questions.** Any time you ask Nico more than one question, present them as a numbered list (1., 2., 3.) so he can answer by number with no ambiguity. A single standalone question needs no number.

- **Self-contained smoke-test instructions.** When you ask Nico to manually test or verify an app or website, assume zero carried-over context — he should never scroll back or recall a URL/path/credential from earlier. Always include: the exact URL (full `https://…` or `http://localhost:…`, restated even if mentioned above), the precise steps in order, and what a pass vs. fail looks like. Repetition here is a feature, not clutter.

- **UTC at rest, Pacific on display.** Timestamps are stored in UTC, always. A *calendar day* shown to a human is `America/Los_Angeles` — Nico's day, and the clock the work actually happened on. The two rules that follow are the ones that get broken: never form a date bucket with `new Date(…).toISOString().slice(0,10)` (that is UTC, so every chart axis and "today" silently rolls over at 5pm Pacific — it put a phantom tomorrow bar on the Prompt Lab dashboard), and never bucket UTC-stamped rows with a bare `date(col)` in SQL. Use `Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' })` in JS and an explicit zone in SQL/Python. Storage in local time is also wrong — it can't be migrated across a DST boundary without loss.

- **No marker before a copy-paste command block.** Nico's terminal renders markdown bullets (`-`, `*`, `•`) as `●`, which breaks paste into zsh. The line directly above a fenced command block must be a plain-text label ending in a colon — never a bullet, dash, asterisk, or number. For loud copy targets, lead the label with `📋` + bold `COPY THE BELOW`, then a colon, then the block.
<!-- SHARED-CONVENTIONS:END -->
