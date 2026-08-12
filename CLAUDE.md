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

**The nightly review email says "no new work" on days full of work — TWO BUGS
FOUND 2026-08-12, NEITHER FIXED.** Nico reported it; both were reproduced from
stored artifacts and the job log, not inferred.

*Bug A, the window.* `send-review.py:168-175` fires at **2:30am** and asks for
**today**: `get_daily_summaries(since=today_str)` where `today_str` is the
current date — at 2:30am that is structurally always empty, since a day's
summary is written at the *end* of that day. The `daily_sessions` fallback
(`get_raw_sessions(since_days=1)`) then fails two further ways: it filters
`summary IS NOT NULL`, so a session counts only once it has been `/handoff`ed,
and it selects on `started_at`, so a long session is invisible to the day it
actually worked (raconte ran 2026-08-10 16:03 → 2026-08-11 22:51 UTC — 31
hours — and never appears in an Aug 11 "today"). On 2026-08-12 both inputs were
empty and the email said "No coding sessions were logged in the last 24 hours"
on a day with 25 prompts across 4 projects. Same shape on 2026-08-05. Fix:
"Today" must mean **yesterday's completed lab-day**, and sessions must be
selected by **overlap** with that day, not by `started_at` in a rolling UTC
window.

*Bug B, delivery — the sixty-nights failure verbatim, in a new place.*
`send-review.log` holds **33 Resend 403s**: `The send.prompt-labs.org domain is
not verified`. The job composes the review, writes it to `review_snapshots`,
logs `Send FAILED — persisting the review anyway`, and exits 0. So the artifact
table fills up nightly while nothing is delivered — and **the #45 freshness
heartbeat structurally cannot catch this, because the artifact is the thing
that still gets written.** That is a real hole in the countermeasure, not just
a bug: alarming on the artifact only works when the artifact is downstream of
the step that fails. Fix the domain at https://resend.com/domains or move
`FROM` to a verified sender, then decide whether a failed send should still
write the snapshot — right now the row records *composition*, not *delivery*,
and nothing distinguishes them.

**Both halves confirmed by the mini 2026-08-12, and one guess was wrong.**
Right: the mail Nico reads comes from the mini — its `send-review.log` shows an
unbroken run of `Sent (id: …)` through this morning, so the 403 is laptop-only.
Wrong: I guessed the mini's DB was stale and that "no new work" was a true
statement about the wrong machine. **It is not stale** — the mini holds 11,240
prompts (still accruing, max `2026-08-12 00:35`) and 983 daily summaries
spanning `2026-01-25 → 2026-08-11`. So the received email is **Bug A, plainly**:
the window is wrong on a machine with the data. A possible second contributor,
worth checking when fixing: `get_raw_sessions` reads the *local* `sessions`
table, and Nico's sessions now start on the laptop, so the mini's Today section
may be starved of session rows independently of the clock.

The 403's cause is a one-line divergence: the laptop's `.env.local` (dated
**Jun 6**, an old copy) has `REVIEW_FROM_EMAIL=reviews@send.prompt-labs.org` —
the unverified *subdomain* — while the mini uses `reviews@prompt-labs.org`, the
verified root. **Do not simply fix the laptop's FROM.** The mini is the settled
owner of the reader jobs and both machines currently have `com.promptlab.review`
loaded, so repairing the laptop's sender turns one broken nightly email into two
delivered ones. The real decision is whether the laptop's review plist should be
unloaded — with the exception that the mini will be down at least one night
during the headless rebuild, which is exactly when a working laptop sender is
wanted. Also still unexplained: **no `review_snapshots` rows at all for Aug 10
and Aug 11** on the laptop.

**The trajectory heatmap's month labels are on a different scale than the grid
— DIAGNOSED 2026-08-12, NOT FIXED.** The data is fine; only the axis lies.
`.heatmap-labels` (`web/index.html:298`) is `justify-content: space-between`,
spreading 13 month labels across the **container's full width** (~1050px),
while `.heatmap` (`:290`) is 53 fixed columns of 8px + 2px gap = **530px**,
left-aligned and never stretched. The grid's right edge (today) therefore lands
at ~50% of the label row — the 7th of 13 labels, **Feb**. Six months of
continuous work read as "dead since March." The smoking gun: `:1586` computes
`monthLabels.push({ idx: weeks.length, … })` and `:1600` renders
`<span>${m.label}</span>`, throwing `idx` away — alignment was never
implemented. Second defect, same cause: the label row sits *outside* the
`overflow-x:auto` container, so on a phone it doesn't scroll with the grid.

Agreed fix (Nico approved 2026-08-12, and **keep the coloring on prompt
count**): wrap both rows in one scroll container with a `width:max-content`
inner div, and give the label row the **same flex geometry as the grid** — one
8px slot per week column, `gap:2px`, labelled slots carrying absolutely-
positioned text plus a dot at the true column centre, the convention `DateAxis`
(`:1936`) already established for the other six charts. Alignment becomes
structural rather than a magic 10px pitch constant. Verification is the usual
constraint: this sandbox cannot render the app, so `node --check` plus eyes on
prod.

**Prompt ratings: the mechanism exists and has never once been used.** The
`prompts` table carries `utility`, `tags`, `notes`, `outcome`, `/handoff` is
supposed to offer rating, and `/readup` surfaces utility-4+ prompts from past
sessions. **0 of 1046 prompts on the laptop are rated.** So the whole
high-utility-prompt loop is dead code paths over an empty column. Nico wants to
mark the prompts that turned out to be good ones — he raised it 2026-08-12 —
and the lesson from the zero is that **retrospective batch-rating at handoff
time does not work**, because by then you cannot remember which prompt was the
good one. Anything built here has to capture in the moment. Not designed; needs
its own session.

Worth checking while there: today-counts read **1 prompt for prompt-lab** on a
day with at least six user turns in this repo, and mid-turn interjections were
absent from the `prompts` table minutes after being sent. Possibly a lag,
possibly `log-prompt.sh` only sees turn-initial prompts. Unverified, but it
would mean the raw tier undercounts, which poisons everything downstream.

**UptimeRobot alerted nobody for six weeks — FOUND AND FIXED 2026-08-09.**
`scripts/uptimerobot.py` declared *what* to watch and never *who to tell*, so
every monitor it created carried an empty `assignedAlertContacts`. **7 of 8
notified nobody**; only garm had one, because garm's monitor was made by hand
in the UI before the script existed. Caught because musicforge asked whether
anything fired during their 2026-08-09 Fly outage: the monitor detected it
exactly as designed (DOWN 17:35:14 PDT → UP 17:45:51, 637s, cause 333333) and
sent no mail. The repo's recurring shape in a new place — the sensor worked,
the output went nowhere, and eight green monitors read as health.

Fixed: contacts declared by **email, not id** (the id is account state, the
address is the intent; resolved against `/alert-contacts` at run time, a
missing address is fatal), reconciled as a **union** so a hand-added contact
survives, all 7 backfilled live, and `list` now prints
`alerts=** NOBODY **` — the state was invisible because nothing rendered it.
Two bugs fell out: the documented **10 req/min free-tier limit was never
respected**, so the first `--apply` patched 2 of 7 and 429'd on the rest,
reporting five real changes as failures (now 6.5s pacing + one 429 backoff).

Still open from that thread: **musicforge asked for the Fly backend as its own
uptime line, and it cannot be done with the current monitor** — the deep check
reaches Fly *through* the Vercel rewrite, so a Vercel outage and a Fly outage
render identically. Needs the direct Fly hostname and a decision on whether the
frontend line stays deep; both asked in the handoff channel, nothing built.
**Delivery verified end-to-end 2026-08-09**, not merely sent: a throwaway
monitor pointed at a real 404 went DOWN (incident `cause 404` at 02:00:09Z)
and the mail landed in Nico's inbox. Two deliberate choices worth keeping if
this is ever repeated — **test on a disposable monitor, never by flipping a
real one to a failing URL**, because that writes a fake outage into that
service's true uptime ratio and the archive is never backfilled; and pick the
404 target carefully, since `https://prompt-labs.org/api/<anything>` returns
**200** from the SPA catch-all (bug #40, re-confirmed live) and would have
produced a false UP. `garm.prompt-labs.org` returns a real 404. And the 4
HEARTBEAT creates still fail on every `--apply` (3× 403 paid-plan, 1× 400
`gracePeriod must not be greater than 86400` — a real declaration bug in the
bi-monthly report's 5-day grace, harmless only because the plan blocks it
first), so `--apply` always exits 1. Cosmetic, but it trains you to ignore the
exit code.

**Mini → headless (closet) migration — switch (TP-Link TL-SG116, unmanaged)
arrives Mon 2026-08-11.** **Settled 2026-08-09: the current laptop IS the new
MacBook Pro and the new primary — no third machine is coming**, so this is one
migration to absorb, not two. Design was started as a brainstorm and **parked
mid-questioning**; nothing is decided beyond that. Full audit 2026-08-08 lives
in memory `project_mini_headless.md` — **on the mini, and memory does not sync
between machines**, so it is unreadable from the laptop; re-read it there or
redo the audit. **Both boot blockers cleared 2026-08-10 on the mini:**
Remote Login is ON (port 22 verified listening) and FileVault is OFF.
Still pending: enable auto-login (System Settings → Users & Groups, greyed out
until FileVault reported Off) and the proof — one reboot with the display
attached that lands on the desktop with no password and answers
`ssh nico@<mini>` from the laptop. Before the move: DHCP-reserve en0 MAC
`d0:11:e5:b5:74:41`. All six custom LaunchAgents (4× promptlab nightly,
rockart backup, SPAN bath detector) stay on the mini — note they're **user**
agents, so they need a logged-in session. mDNS must survive the move (bath
detector → `phrpi.local`, Time Machine → Time Capsule); the unmanaged switch
keeps one subnet, so it does.

Added to the list 2026-08-10, deliberately scoped small: **disconnect Dropbox
from the mini and delete local files it doesn't need** — but only after
confirming each has a copy in iCloud/Dropbox (Nico believes everything
important is in one of those, possibly a third place; verifying that fully is
its own project, not this one). The mini also ends up wired to both Raspberry
Pis (one runs Home Assistant) — parked thought: that adjacency may help
developing the Pi tools later.

**Calling off the wipe — PROPOSED 2026-08-12, NOT DECIDED. Nico is on the
fence.** He raised it, asked whether I agreed, I did, and I then wrote it up as
settled and relayed it to the mini-decommission agent as a decision. That was my
error, not his position — recorded here because the same mistake is easy to
repeat: *agreeing with an idea is not the same as the idea being chosen.* The
proposal is to relocate the mini rather than rebuild it — it would move to the
closet with its disk, its DB, its `.env.local` and all six LaunchAgents intact
and running. The argument for it, which stands on its own merits either way: the
machine is going from attended to unattended, and a wipe
maximizes the number of unverified restore steps exactly when the feedback loop
gets longest — an un-reinstalled plist or a missing env var on a headless box in
a closet is invisible for days, which is this repo's entire failure catalogue.
Change one variable, location, not two. What survives from the wipe prep is the
part that was always independently worth doing: the `.env.local` scp to the
laptop (the laptop's copy is a stale Jun 6 fork), the DB snapshots (now backups
rather than prerequisites), and auto-login + FileVault-off + Remote Login with a
reboot-with-display proof — those are relocation requirements, not wipe ones.
State over there, as of the end of 2026-08-12: `WIPE-CHECKLIST.md` is the
authoritative file, carrying today's completed items and an explicit
"OPEN QUESTION — Nico on the fence" banner; the no-wipe path lives beside it as
untracked `DRAFT-move-to-closet.md` headed "PROPOSAL ONLY / NOT DECIDED".
Nothing committed there. Both paths sit in front of him and **neither filename
asserts a decision** — which is the right resting state for a question this
open, and worth copying the next time two agents get ahead of a call that isn't
theirs.

**The counterargument, and it is the strong one — raised by the
mini-decommission agent 2026-08-12.** "The wipe doesn't buy anything" is wrong:
**the wipe bought privacy, not reliability.** What the no-wipe path leaves in a
closet, unattended and indefinitely, is a logged-in personal Apple ID with iCloud
tokens, 66G of Messages history including `chat.db`, the login keychain with
saved passwords and certs, the photo library, a Dropbox mirror and browser
profiles. Unattended cuts both ways: it lengthens the feedback loop for breakage
*and* it means nobody notices physical access. The threat model is "someone with
hands on a box inside Nico's house," which he may well discount — but it should
be discounted **explicitly**, not assumed away by a framing that only counted
reliability. Their proposed middle path: relocate now, wipe never, then a
separate headless *thinning* pass over SSH — sign out what isn't needed, delete
the libraries already verified redundant (Messages-in-iCloud on, Mail all-IMAP,
photos merged and exported). That preserves the one-variable-at-a-time property
and is the shape to beat.

One cost of that path specific to this repo, worth knowing before anyone likes
it too much: their further idea of running the jobs from a *separate local
account* would relocate or duplicate `~/.claude/prompt-history.db`, which is the
raw private tier — a second copy of every raw prompt is a privacy regression in
the opposite direction. Any account split has to move that DB, not copy it.

**What runs where — PROPOSED 2026-08-12, NOT DECIDED.** Not "nightly jobs go to the
mini." The split is **where the data is** vs **where the uptime is**:
- *Local-data jobs* run on **every** machine, over its own DB, because raw
  prompts are machine-local by invariant and never leave. That is
  `com.promptlab.synthesizer`, plus the turso-sync leg. The laptop keeps its
  copy; this is not duplication, it's the federation working.
- *Reader/output jobs* run on the **mini only**, because the laptop being closed
  must mean off. That is `com.promptlab.review`, `com.promptlab.report`,
  `com.promptlab.api-costs`. **The laptop currently has all three loaded and they
  must be unloaded** — otherwise repairing the laptop's Resend FROM produces two
  review emails a night. Not yet done; Nico's call to trigger.
- Vercel crons (the 8am health email) are cloud-side and location-independent —
  out of scope for any of this, don't move them.

**DB ownership: DECIDED 2026-08-10 — Option B, federated.** Raw stays
machine-local per the invariant; each machine synthesizes its own prompts and
pushes processed rows to Turso; the merge happens there; the always-on mini
keeps the reader jobs (review email, report, cost pull) because the laptop
being off must mean off. Nico ruled out running nightly work on the laptop
explicitly. The build-out this implies, none of it done yet:
- Laptop gets its own `com.promptlab.synthesizer` + turso-sync LaunchAgents
  (its `/handoff` already covers most days inline).
- `send-review.py:174-176` reads `get_raw_sessions()` — raw-tier, local-only —
  so the mini's review email misses laptop session detail. Refactor it to
  processed tables only, read via `GROUND_CONTROL_STORE=turso` (the Turso
  store backend already implements the ABC). **2026-08-12 raises the priority
  and the scope:** this is not merely "misses detail" — it is why the email
  reads "no new work" on busy days, and the same two lines carry a second,
  independent window bug (see the review-email entry at the top of Open). Both
  get fixed together, and note that the four promptlab plists are currently
  **loaded on the laptop too**, so until federation is deliberate rather than
  accidental, two machines are composing nightly reviews from two different
  DBs.
- `daily_summaries` is `UNIQUE(project, date)` + `INSERT OR REPLACE`
  (`store/sqlite_store.py:328`): two machines touching one project the same
  day = last sync clobbers the other's summary in Turso. Needs merge-on-upsert
  or a machine column in the key before the federation is honest.

**The week-grouping SQL filed every Monday under the previous week —
EXPRESSION FIXED 2026-08-08; DATA REPAIR APPLIED 2026-08-10.** The 207
audited-bad rollups (23 folded Mondays + 184 frozen partial rows) were deleted
(backup: `~/.claude/prompt-history.db.bak-20260809`) and regenerated from the
intact daily summaries by the fixed synthesizer, then full-synced to Turso —
regenerated rows overwrite stale cloud copies via same-key upserts. Verify
anytime with `scripts/regroup_weekly_rollups.py` (dry-run). The trap,
keep it: SQLite's `weekday N` means next-or-**SAME** day, so
`date(<d>,'weekday 1','-7 days')` returned the *previous* Monday when `<d>`
was already a Monday. The correct bucket is `date(<d>,'weekday 0','-6 days')`
— next-or-same **Sunday**, minus 6 — verified for all seven weekdays. Fixed at
all four homes (`store/sqlite_store.py`, `store/turso_store.py`,
`web/api/private_history.py` `WEEK_EXPR`, `workflow/bin/gc-read.sh`); a
`clocks:` test now runs the expression for a full Mon–Sun week and greps
`'weekday 1'` out of all four files.

The second bug was broader than gc-read.sh: its completed-weeks filter
`date < date('now','weekday 1')` resolved to NEXT Monday on Tue–Sun (fixed to
`'weekday 0','-6 days'`), but the stores' `get_weeks_without_rollups` had **no
completed-week guard at all** (`date < today`), so the synthesizer wrote
mid-week rollups constantly and the never-revisit join froze them. Both stores
now cut at the current week's Monday.

Stored damage — audited read-only by `scripts/regroup_weekly_rollups.py`
(dry-run by default, `--apply` fixes only unambiguous non-Monday week keys;
Turso via `GROUND_CONTROL_STORE=turso`, and it mirrors local anyway):
**0 mis-keyed rows** (the buggy expression still emitted Mondays), so nothing
mechanical to apply. What it found instead, all needing human judgment because
rollup prose can't be regenerated mechanically: 23 rollups with the next
Monday folded into their prose/counts (14 of those Mondays also counted in
their own week = double-counted); 21 Monday-only weeks with summaries but no
rollup (the fixed pipeline will now generate these on its own); and 182
project-weeks whose frozen rollup is missing later-in-week summaries — the
in-progress-week admission was systemic, not an edge case. The script prints
the exact DELETE for the frozen set if regenerate-over-existing-prose is ever
wanted.

**Copy review (#49) is IN PROGRESS — batch 1 of ~4 DONE 2026-08-05.**
The review runs page by page at a computer, 3-5 items at a time. Nico answers by
number and often stops mid-batch, so **track which items were actually answered,
not which batch was sent** — the first pass through this lost two items by
recording the batch as finished.

Answered and settled: the primary nav labels passed. The More panel failed
("a bit incoherent") and was rebuilt in `5b53f01` — labeled `BUILT` stamp
leading instead of a bare timestamp trailing, theme promoted to the primary row
as an icon, Log out last, close-on-outside-click. All five smoke-test items on
the rework then passed live on prod in both themes.

The two items the first pass dropped — the KPI tile labels (do they state what
is counted and over what window, consistently?) and the "Today, so far" banner
— were reviewed 2026-08-05 and **both passed**, so batch 1 is closed.

**Ask is mothballed, not deleted** — it was the only *action* in a panel of
destinations and settings and went unused; `web/api/ask.py` and the modal are
untouched, reachable from `#/about` and the `/` shortcut. Deleting it would not
even drop the `ANTHROPIC_API_KEY` dependency, which the Todos classifier holds.

One open question the rework raised, still unsettled: with Ask gone, `More`
guards a single destination plus your identity, so a plain `About` button in the
primary row may be simpler than the panel. Then batch 2 (Activity + the day
page), batch 3 (Costs, Visitors, Todos), batch 4 (Health, About, project pages).

*Note: no usage data exists for Ask and none can be recovered — its history is
`localStorage`-only and its spend is indistinguishable from the Todos
classifier's, since both draw on the same key.*

**The 80-name project list — CLEANED UP 2026-08-05.** Most names weren't
projects. **Root cause, now fixed:** `log-prompt.sh` derived the project from
the cwd *basename*, so every directory ever worked in minted one — `web`, `src`,
`public`, `utils`, `mockups` are subdirectories of real repos. It now resolves
the cwd to its **repo** via `git rev-parse --git-common-dir` (not
`--show-toplevel`: a linked worktree's toplevel is the worktree, which is how
two `agent-<hash>` projects appeared; the common dir is always the main repo).

Three deliberate properties of that hook change:
- **Only exit code 128 ("not a git repository") buckets to `scratch`.** Any
  other git failure falls back to the old basename behavior. This is not
  paranoia — the Xcode license prompt broke every git call on the laptop earlier
  that same day, and a broken git must never silently relabel real project work.
- `scratch` is pre-hidden, so the one bucket never surfaces in the picker.
- Three cases are pinned in `test_session_identity.py` (#10): subdirectory →
  repo, non-repo → `scratch`, worktree → main repo. The fixture had to become a
  real `git init` repo, since a bare directory now takes the scratch path.

Cleanup applied: **8 aliases** folded duplicates into their canonical project
(`recountly`→`raconte` — one project, the web app became a native iOS app,
`docs/history.md:39`; `skitrack` + `skitrack-ntzb-poc`→`person-tracking`;
`bakerylouise_v1` + `bakerylouise-v1`→`bakerylouise`; `audio_journal`→
`audio-journal`; `invitekit-prep`→`invitekit`; `byside-research`→`byside`).
**23 artifacts hidden** via `scripts/hide_scratch_projects.py` — sets
`private=1`, does not delete, and `--unhide <name> --apply` reverses it. Real
but dormant projects (`mars-rover-example`, `roll-your-own`, `djembe`, …) were
left alone; that's what the Dormant section is for.

**Follow-ups the cleanup surfaced, all unconfirmed and needing Nico's memory of
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

**Don't reach for a read-time exclusion list** — read-time allowlists were tried
twice in this repo and deleted both times for drifting; `private` on the row is
the equivalent that can't drift. Two gotchas hit while doing this: `alias.py`
takes two arguments and **zsh does not word-split unquoted variables**, so a
`for pair in "a b"` loop silently wrote the whole pair into the alias column;
and a full `sync_to_turso.py` runs past 120s, so the alias rows were written
straight to Turso (safe — `project_aliases` is upsert-only, unlike
`project_metadata`, which is cloud-direct and must never gain a sync leg).

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
- **`/api/private_history` Tier 1 — SHIPPED 2026-08-02**, deployed and verified live
  end-to-end (auth'd smoke test passed). `SERVICE_HISTORY_KEY` in Vercel Production,
  value at `op://dev-secrets/prompt-lab-service-history-key/password`. Ball is in
  selected-projects' court to wire `lib/history.ts`. Tier 2 (narrative behind Garm)
  remains unbuilt by agreement. historyKey settled as `bakerylouise` (alias from
  `bakerylouise-v1`). **This endpoint has no allowlist of its own** — it accepts any
  project and is gated solely by the service key, so don't go looking for one. The
  8-key allowlist is the *public* tier's write gate (see the `public_history` bullet
  above); `bakerylouise` and `songscribe` were added to it alongside this work.
- **Public rollups:** only ibuild4you `2026-05-18` remains unpublished, and that is a
  deliberate skip (cost forensics + internal ops; nothing left after scrubbing). It
  reappears in every future draft by design.
- **#48 time localization — POLICY SET AND INSTANCES FIXED 2026-08-02.** The policy,
  now in the shared-conventions block so every repo carries it: **timestamps are UTC
  at rest, calendar days are `America/Los_Angeles` on display.** Storage in local
  time was rejected — it cannot be migrated across a DST boundary without loss — and
  UTC-on-display was rejected because it makes Nico's day roll over at 5pm.

  What was actually wrong was subtler than the issue described: the raw tier is
  **UTC**, not local, because SQLite's `datetime('now')` is UTC. So three clocks
  disagreed — UTC raw rows, Pacific summary writers, UTC frontend axes — and the
  dashboard drew an `Aug 3` column at 5:30pm on Aug 2 with 13 real prompts in it.

  Fixed: `web/day_helper.py` (`lab_today`/`lab_days_ago`/`lab_window`, in
  `includeFiles`, `tzdata` declared in `web/requirements.txt` — unpinned, but present
  so a missing tzdb can't silently degrade the lambda to UTC); `labDay`/`labDayOf`/`labStamp` in `web/index.html`
  replacing all 14 `toISOString().slice(0,10)` axis builders plus the Ask-history
  stamp; lab-day windows in `activity_timeline`, `overview`, `uptime_overview`; the
  heartbeat freshness grader and the uptime-archive date key in `health_report`; 8
  `date(<ts>)` → `date(<ts>, 'localtime')` bucketings in `store/sqlite_store.py`; and
  `today-counts` in `workflow/bin/gc-read.sh`, which now reads 14/4/5 for an evening
  that used to read 0/0/0. **`daily_summaries.date` deliberately did NOT get
  `'localtime'`** — it is already a calendar day, and shifting it would be the same
  bug pointed the other way. Four existing tests derived their own expectations in
  UTC and so passed by day and failed by night; they now go through `lab_today()`.
  Four `clocks:` drift guards were added — two are greps over the source, because
  the failure is invisible to a test that computes its own date.

  Still open on #48: the "8am" cron is `0 15 * * *`, which is 8am Pacific in summer
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

**Mobile pass, 2026-08-02.** Four things, all from the same phone session:
`DateAxis` replaced six copy-pasted axes (tick count from measured width, labels
absolutely positioned inside a clipped box, plus a dot under each labelled
column so the label maps to a bar without counting); the home chart's tap now
navigates to a real `#/day/<date>` page rather than opening a panel that lands
off-screen when pinch-zoomed — **any overlay positions against the layout
viewport, so a "fixed" sheet fails under zoom exactly like the panel did**, which
is why this is a route and not a modal; `/api/day` backs it so a cold-opened link
to any date works; the nav collapses behind one button below 640px (both markups
always render, CSS picks — no viewport state in JS to desync on rotate); and 7d
joined the window toggles. Home offers 7|30 only, because it reads `overview`,
which is capped at 30 days and stays lean on purpose.

Round two, same evening, all three from one phone screenshot. **The wide nav and
the hamburger both rendered at once** because `display:contents` was set INLINE on
the wrapper — an inline style outranks every selector, so the media query could
never hide it. Moved to CSS. **Every chart now navigates to the day page** and all
four below-chart panels are gone; `/api/day` grew spend/visitors/uptime sections
so nothing was lost with them. **Today's column is drawn as a dashed outline and
the day page carries a "Today, so far" banner** — counts come from
`daily_summaries`, written at `/handoff` time, so a live session isn't in them and
a short solid bar read as "a quiet day" instead of "not tallied yet." That is this
repo's recurring failure shape rendered as a chart.

Round three: the nav is two tiers. PRIMARY is the five views; everything else —
Ask (an action, not a destination), About, theme, email, log out, build stamp —
sits behind **More**, because mixing them put "Log out" the same distance from a
thumb as "Costs". One declaration renders both navs. The header's built/synced
sub-line is gone; that detail lives on the new `#/about` page and as a terse
stamp at the foot of the More panel. **Not yet verified by eye** — shipped after
Nico signed off for the night.

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

- **`workflow/bin/*` and `workflow/commands/*` run from installed copies under
  `~/.claude/`, not from the repo.** A fix committed to the repo is not live
  until copied over (per machine!). Bit hard 2026-08-10: the Monday week-bug
  fix landed in `workflow/bin/gc-read.sh` while the installed copy kept the
  buggy SQL, and `/handoff`'s rollup check invented two phantom missing weeks
  from Monday-dated summaries. After fixing anything under `workflow/`,
  diff-sweep: `for f in workflow/bin/* ; do diff -q "$f" ~/.claude/bin/$(basename "$f"); done`
  (and the same for commands) — on BOTH machines.

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
