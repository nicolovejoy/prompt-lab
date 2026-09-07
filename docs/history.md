# prompt-lab — history

The chronological build log, moved out of `CLAUDE.md` on 2026-08-02 so that file
could stay a working brief rather than an archive. Nothing here was edited: it is
the "Next Steps" section verbatim as it stood, newest first. Durable content —
open work, invariants, traps, settled decisions — was hoisted into CLAUDE.md and
is not repeated here; this is the narrative of how each thing came to be.

Entries are dated and reference commits, so git is the tiebreaker where this
drifts.

---

## Build log (newest first)

### The nightly pipeline failed every night the laptop had to WAKE for it (moved 2026-09-07)
**The nightly pipeline failed every night the laptop had to WAKE for it —
FOUND AND FIXED 2026-09-06, and the watchdog that should have said so was
blind by construction.** A week of real unattended runs produced the evidence
the two staged-host acceptance tests were waiting for, and one of them passed
while the other found this.

The correlation was exact. Runs that fired at 02:30:0x on an already-awake
laptop succeeded (Aug 30, Sep 5, Sep 6). Runs that fired on a scheduled wake
failed (Sep 1, 2, 3, 4), every one at `socket.gaierror: [Errno 8] nodename nor
servname provided, or not known`. launchd fires within ~5s of the wake and DNS
is not up yet. Aug 31 produced no run at all. Four of seven nights sent no
review email.

Three defects, each an instance of the failure shape at the bottom of this
file, and they hid each other:

- **`synthesizer.py` swallowed every per-item API error, still pinged its
  heartbeat, and exited 0.** So the synthesizer artifact looked FRESH on
  nights when every call had failed. `daily_summaries` shows the damage: 5-7
  projects/day normally, 1-2 on Aug 31 - Sep 3. Now a total wipeout
  (`attempted > 0 and errored == attempted`) skips the heartbeat and exits 1;
  a partial failure still pings and exits 0, because one project failing to
  summarize is not a dead night.
- **`nightly_pipeline.py` had no network gate**, so it ran the whole night
  into a dead resolver. `wait_for_network()` now polls DNS for up to 180s
  before any stage — **on the monotonic clock**, per the standing rule — and a
  night that never gets a resolver runs no stages, records a synthetic
  `StageResult("network", "failed", ...)`, and skips the Turso push that
  cannot work anyway.
- **The health email graded only the NEWEST run record** (`ORDER BY
  started_at DESC LIMIT 1`). A night that dies for lack of network cannot push
  its own record either, so it arrives days later via catch-up already older
  than a newer healthy run — and was therefore never graded at all. The
  catch-up mechanism and the grading mechanism cancelled each other out. Now a
  7-day window is graded, any bad night in it forces `ok=False` even when the
  newest run is clean, and `NIGHTLY_RUN_MAX_AGE_DAYS` dropped 2 -> 1.

**The generalizable trap, worth more than the fix: a failure whose own cause
also blocks its reporting path erases its own evidence.** No amount of care in
the grader helps, because the grader never receives the row. The fix has to be
on the reading side — grade a window, not the newest row.

**What passed:** step 3's blocked-push acceptance test, in the wild and harder
than specified — four consecutive nights could not push, and the Sep 5 run's
stateless catch-up backfilled all four. Turso holds an unbroken Aug 30 - Sep 6
sequence. Step 2's sleeping-host test is still outstanding.

### Step 3's blocked-push acceptance test PASSED in the wild (moved 2026-09-07)
**Step 3's blocked-push acceptance test PASSED in the wild 2026-09-06, harder
than it was specified.** It was never staged — Sep 1-4 failed for real, all
four could not push, and the Sep 5 run's stateless catch-up backfilled every
one. Turso holds an unbroken Aug 30 - Sep 6 `nightly_runs` sequence. The half
of that test about freshness reporting stale *during* the block did NOT pass,
and that is the wake/DNS entry above: the email stayed green throughout,
because grading only the newest row cannot see a record that has not arrived.

### Three of the five live risks WERE closed by hand on merge night (moved 2026-09-07)
**Three of the five live risks WERE closed by hand on merge night
(2026-08-29), attended rather than at 2:30.** Worth knowing they are facts,
not hopes: `migrate()` was run against **real Turso** — `nightly_runs` exists
with all ten columns and `prompt_version` landed on both summary tables, so
the `ALTER TABLE ADD COLUMN` path **does** work over the libSQL HTTP
pipeline, which was the branch's biggest unknown. `migrate()` was also run on
the real local `prompt-history.db` — all three new tables present, both
columns added, 241 daily summaries intact. And the deployed lambda imports
cleanly: `/api/health_report` returns **401, not 500**, which is the tell —
a missing `artifact_checks.py` in `web/vercel.json`'s `includeFiles` would
fail at import *before* auth ran and would have silently stopped the daily
health email. Only the two staged-host tests above remain.

The general habit that produced this, worth repeating: when a change ships
code that will first execute unattended overnight, run the irreversible-ish
part by hand while awake. It is the same action the job would take, and it
converts "we'll find out at 2:30" into a fact in about a minute.

### Next piece of work: `docs/nightly-pipeline-plan.md` — step 1 DONE (moved 2026-09-07)
**Next piece of work: `docs/nightly-pipeline-plan.md` — step 1 DONE
2026-08-29, steps 2–4 remain.** Collapses the racing nightly agents into one
ordered pipeline, because **a scheduler is not a dependency mechanism** —
launchd coalesces missed `StartCalendarInterval`s onto one wake, so two agents
scheduled 45 minutes apart start simultaneously after a closed-lid night, and
retiming `api-costs` would look like a fix and not be one. Step 1 (idempotent
remote writes) shipped and was applied live: remote `save_review_snapshot` is
now an upsert keyed `(review_type, date)`, `migrate()` dedupes-then-indexes
(self-healing, safe on every sync), and Turso went **11,848 rows → 78**,
verified stable across two consecutive syncs with today's row present.
`project_snapshots` was audited for the same shape and is clean (live UNIQUE
constraint, 0 dup pairs). Tests in
`scripts/test_review_snapshot_idempotency.py` run the store's real SQL against
in-memory sqlite.

### Step 2 DONE 2026-08-29, applied live on the laptop (moved 2026-09-07)
**Step 2 DONE 2026-08-29, applied live on the laptop.** `nightly_pipeline.py`
is the single nightly entry point: cost pull → synthesizer → review →
report-when-due → publish, wrapped by `run-nightly.sh` under one
`com.promptlab.nightly` agent at 2:30. Per-stage timeouts are MONOTONIC
(subprocess timeouts stop counting during sleep — no wall-clock deadline, per
the standing rule). A failed stage skips its dependents (a review over a
failed synthesis is the "no new work on a busy day" bug), but publish always
runs; the cost-pull heartbeat fires only after publish lands. The bi-monthly
report is now artifact-keyed — it runs when the current half-month (1st/16th
split, Pacific) has no `monthly_report` snapshot — so a closed lid on the 1st
means a late report, not a skipped one. NOTE: the Aug-16 report never ran
(laptop jobs were re-enabled the 20th), so the first pipeline night catches it
up — an extra report around 2026-08-29/30 is correct, not a bug. The four old
agents are booted out and parked in
`~/Library/LaunchAgents/disabled-promptlab-step2-20260829/`;
`workflow/run-cost-pull.sh` and the four old plists are deleted from the repo
(their coupling/no-`source` lessons live on in `nightly_pipeline.py` and the
new plist's comments). Tests: `scripts/test_nightly_pipeline.py` (11, real
subprocesses).

### Step 3 DONE 2026-08-29 (moved 2026-09-07)
**Step 3 DONE 2026-08-29** (decided: local write, pushed to Turso as its own
step — see the Invariants entry, not a synced table). `nightly_runs` brackets
every run — a `status="running"` row before the first stage, a full row
(stages, `overall_status`, `machine_host`) after — and `push_runs` runs after
publish with stateless catch-up (push local rows newer than the remote's
newest `started_at`, upsert by `run_id`). The health email's
`_check_nightly_run`/`_claims_vs_remote` cross-check the run record against
`HEARTBEATS`; a bad run escalates the subject and a malformed `stages`
payload can't 500 the email. **Step 5 DONE 2026-08-29** — `daily_summaries`
and `weekly_rollups` archive the row an upsert or repair is about to replace
into `*_superseded` (local only) before overwriting, so re-running the
synthesizer stops destroying prose that cost an API call. One asymmetry
worth knowing: `weekly_rollups.prompt_version` syncs to Turso but
`daily_summaries.prompt_version` does not — `merge_summary_parts()` in
`sync_to_turso.py` builds a fixed dict that omits it, deliberately, since the
column is local provenance and no cloud reader needs it, so Turso's
`daily_summaries.prompt_version` stays perpetually NULL. That's accepted,
not a broken sync leg.

### Public refresh backlog fully cleared 2026-08-27/28 (moved 2026-09-07)
**Public refresh backlog fully cleared 2026-08-27/28 — style guide for future
drafts now lives in Claude's memory, not here.** Nico reviewed and edited
drafts for ibuild4you, musicforge, prntd, prompt-lab (24 weeks total across
two rounds); iterated on the narrative style (terser, cut process/debugging
narrative, active voice, judge redundancy per-entry rather than by a fixed
phrase list) and had it saved as a standing memory
(`feedback_public_draft_narrative_style.md` in prompt-lab's Claude memory
dir) — apply it automatically on future `draft_public_refresh.py` passes,
don't wait to be told again. All published via `publish_public_draft.py
--apply` + synced to Turso (`a166082`, `6bd8844`). `--list` now shows 0
unpublished weeks for every project on the allowlist — nothing pending.

### Not prompt-lab's bug, just diagnosed here 2026-08-23 (moved 2026-09-07)
**Not prompt-lab's bug, just diagnosed here 2026-08-23:** the `howl@` denial
digest is Garm's own email (not ours), and a burst of ~35 denials on
ibuild4you traced to ibuild4you's own liveness probe hammering
`/gnipahellir` with a synthetic `health-probe@example.com` credential. Garm
already asked ibuild4you to kill it (`~/src/.handoff/ibuild4you-prompt-lab.md`,
2026-08-23); nothing to do here unless it recurs.

### VERIFIED 2026-08-22: the first unattended laptop run of the nightly jobs worked (moved 2026-09-07)
**VERIFIED 2026-08-22: the first unattended laptop run of the nightly jobs
worked.** `send-review.log`: started 02:30:01, generated in 138.0s, sent,
finished 02:32:22, `LastExitStatus = 0`; `pmset -g log` shows the only sleep
that hour was 02:05–02:21, before the job. The caffeinate wrapper held through
the run. The sleep fix is no longer a claim.

### SPAN outage 2026-08-21 — RESOLVED same day (moved 2026-09-07)
**SPAN outage 2026-08-21 — RESOLVED same day, not our fault, and the cause was
one toggle.** Cloudflare **Bot Fight Mode** was managed-challenging Vercel's
egress on `influx.pianohouseproject.org/api/v2/query`, so SPAN's health check
503'd and its monitor flapped ~25 times in a day. Nico disabled BFM; verified
green from both repos. Thread archived in `~/src/.handoff/span-prompt-lab.md`.
Two residuals, one already closed:
- ~~UptimeRobot's account display timezone was **UTC-10**, stamping every alert
  email ten hours behind Pacific~~ — **FIXED 2026-08-21 by Nico.** Kept because
  of what it cost: two rounds of cross-agent confusion over the incident time,
  with an authoritative-sounding wrong timestamp handed between repos. When two
  sources disagree about *when*, suspect a display timezone before suspecting
  either party's reading.
- **Load-shedding is not available on our side and never was.** The `deep` flag
  in `web/api/health_report.py` is *descriptive* — it mirrors `?db=1` in the URL
  — and `_check_target()` issues the request either way, so flipping it removes
  zero requests. byside and garm got their reduction by editing the **URL**. Do
  not offer "flip it to shallow" as a remedy again without checking whether the
  target's URL actually has a deep variant to drop.

### Decided 2026-08-20 (Nico): the nightly jobs move to the laptop (moved 2026-09-07)
**Decided 2026-08-20 (Nico): the nightly jobs move to the laptop.** He leaves
it on and plugged in, and explicitly accepted the limitation that a closed
lid means a late or missing report. Two things make this better than it
sounds: launchd re-fires a missed `StartCalendarInterval` on wake, so a
closed-lid night gets a late email rather than none; and co-locating the
readers with the capture machine closes the old "laptop synthesizes at 2:00,
mini reads Turso at 2:30" “Today”-window gap for free. The laptop sleeps too,
so the caffeinate wrapper is what makes this viable — it is not a
mini-specific hack.

### What runs where — SETTLED 2026-08-20 (moved 2026-09-07)
**What runs where — SETTLED 2026-08-20: the nightly jobs run on the LAPTOP,
and nowhere else. (2026-08-29: the four agents described below were collapsed
into the single `com.promptlab.nightly` pipeline agent — see the
nightly-pipeline entry above; the one-sender rule is unchanged.)** Nico's call, on the reasoning that he leaves the laptop on and
plugged in and accepts that a closed lid means a late or missing report. Applied
the same day: the mini's four agents are booted out and parked in
`~/Library/LaunchAgents/disabled-promptlab-20260820/` (reverse: move back +
`launchctl bootstrap gui/$UID/<plist>`), and all four are rendered and loaded on
the laptop. **There is exactly one sender — never load the readers on two
machines at once or Nico gets two emails a night.**

Why this beats the mini-only split it replaces: the mini's raw DB is frozen
(nothing is captured there), it deep-sleeps through the night so its jobs
started late and ran for hours of wall clock, and co-locating the readers with
the capture machine removes the cross-machine "Today"-window gap entirely. The
laptop sleeps too — `workflow/run-nightly.sh` is what makes this work, and
launchd re-fires a missed `StartCalendarInterval` on wake, so a closed-lid
night degrades to a late email rather than none.

The laptop's older `~/Library/LaunchAgents/disabled-readers-20260812/` is now a
stale backup of the 2026-08-12 parking; the live copies are the rendered ones in
`~/Library/LaunchAgents/`. The original split, for the record:
- *Local-data jobs* run on **every** machine, over its own DB, because raw
  prompts are machine-local by invariant and never leave. That is
  `com.promptlab.synthesizer`, plus the turso-sync leg. The laptop keeps its
  copy; this is not duplication, it's the federation working.
- *Reader/output jobs* run on the **mini only**, because the laptop being closed
  must mean off. That is `com.promptlab.review`, `com.promptlab.report`,
  `com.promptlab.api-costs`. **Done 2026-08-12 (Nico triggered it):** all three
  unloaded on the laptop and parked in
  `~/Library/LaunchAgents/disabled-readers-20260812/`; only the synthesizer
  remains loaded there. **Reversed 2026-08-20 — see above; the availability
  argument lost to the fact that the mini slept through every night anyway.**
- Vercel crons (the 8am health email) are cloud-side and location-independent —
  out of scope for any of this, don't move them.

### The nightly review's "3h19m API call" was never an API problem — the Mac was asleep (moved 2026-09-07)
**The nightly review's "3h19m API call" was never an API problem — the Mac
was asleep. SOLVED 2026-08-20; do not re-open the timeout theory.** The
earlier entry here diagnosed a read-timeout that kept resetting on trickled
data and prescribed a hard wall-clock deadline of ~10 minutes. **That fix
would have aborted a healthy run every single night.** It was never applied.
Keep the reasoning below, because the measurement trap it describes will
recur on any machine that idles.

The evidence, gathered by `pmset -g log` on the mini:
- The mini deep-sleeps every ~15 minutes with 45-second dark wakes, all
  night — **19 sleep cycles between 02:00 and 06:00**, 742 sleep/wakes since
  the Aug 13 boot, each logged `Entering Sleep state due to 'Maintenance
  Sleep':TCPKeepAlive=active`. `pmset sleep 0` is already set and does not
  prevent this on Apple silicon.
- launchd fires `StartCalendarInterval` on the next **wake**, not the
  scheduled minute. The 02:30 job actually started at **02:42:07**.
- 02:42 → the log's 06:01 mtime is **exactly the 11,942s** in the log.
  Summing the sleep intervals across that span: **~11,350s asleep, ~640s
  awake.** There was no 3h19m call. There was a normal generation (a healthy
  night is 136s) stretched across a machine powered down for 95% of the
  wall clock.
- `time.time()` counts sleep; the monotonic clock httpx uses for its read
  timeout does not. So the 300s ceiling **correctly** never fired and
  `duration_ms` **correctly** read 3h19m. Both numbers were right and they
  measure different things. `TCPKeepAlive=active` is what let the socket
  survive the sleeps, which is also the better explanation for the Night 2
  "6-hour silent hang" than a half-open socket.

Confirmed still true from the old entry: the two real bugs found 2026-08-19
(uncaught `APITimeoutError` with no retry; unbounded client timeout) did not
recur, so those fixes are genuine. And the `send-review.py` line-257
traceback **is** a fossil — it matches `86ed77d` (257 lines, Aug 14–19), not
the current 255-line file.

Fixed same day, all of it machine-agnostic and in git:
- `workflow/run-nightly.sh` — every nightly plist now runs its job through
  it. Holds `caffeinate -ims` for exactly the job's lifetime (with a utility
  argument, `-t`/`-w` are ignored and the assertion cannot orphan; no `-d`,
  so the display still sleeps), stamps start/finish times into the log, and
  rotates the log by **copy-truncate** at 256KB. Rotation must not be `mv`:
  launchd opens `StandardOutPath` before spawning, so renaming leaves the
  inherited fd on the renamed inode and the whole run lands in the archive.
- `claude_api.call_claude` logs each attempt's start timestamp and records
  both wall and monotonic elapsed; `describe_elapsed()` prints
  `"11942.4s wall / 638.0s awake — HOST SLEPT ~189min mid-call"` instead of a
  bare duration. `awake_ms` joins `duration_ms` in the returned dict. Five
  `clocks:` tests pin this, including a grep guard that both readers still
  call `describe_elapsed` — if one quietly reverts to printing bare
  `duration_ms`, the next such night is undiagnosable again.

**Do not add a wall-clock deadline.** If a deadline is ever wanted it must be
enforced on monotonic time, or it will abort healthy runs on any sleeping
host.

### Found while fixing the above: `com.promptlab.report` has been silently dead on the mini (moved 2026-09-07)
**Found while fixing the above: `com.promptlab.report` has been silently dead
on the mini since the 2026-08-13 rebuild.** Its plist ran
`source $REPO/.env && python generate-report.py 30`, and **the mini has no
`.env`** (only `.env.local`), so `source` failed, `&&` short-circuited, and
python never ran — no `generate-report.log` exists there at all. This is the
identical `&&` short-circuit that killed this same job for four months once
before. The `source` was always redundant: `generate-report.py:134` calls
`load_env()` itself, which loads `.env` *and* `.env.local` and tolerates
either being absent. The plist now invokes python directly through
`run-nightly.sh`. Next scheduled run is the 1st.

### Also found: the mini's raw prompt DB is frozen (moved 2026-09-07)
**Also found: the mini's raw prompt DB is frozen** — 11,240 prompts, last
`2026-08-12 00:35`, i.e. the restored pre-wipe snapshot, while the laptop
logs 46–198 prompts/day. Nothing is captured on the mini, so its synthesizer
runs nightly over a dead database and its sync re-pushes identical rows.
Harmless, but it means the mini's only real contribution was *being awake at
2:30am* — which it wasn't.

### For the record, 2026-08-17 in one breath (moved 2026-09-07)
For the record, 2026-08-17 in one breath: turso-readers merged to main
(direct, per Nico); py3.9 `from __future__ import annotations` fixes in
`pull_api_costs.py` + `store/__init__.py` + 2 more (repo swept — and note
the sweep ran pre-merge and missed the file the branch was about to add;
sweep AFTER merging); mini's four jobs loaded, cost-pull kickstarted clean
end-to-end, review dry-run composed laptop work from the merged store; #50
(day-page cache/prefetch) and #52 (write-time `agent` label on
`page_views`) shipped via parallel worktree agents, deployed, eye-checked
by Nico; #51 closed (laptop's `project_workspaces` was never seeded —
seeded both machines, laptop rows UPDATEd, Turso backfilled by re-pull +
full sync); Turso `_pipeline` got a 60s timeout + one retry after a full
sync hung 1.5h on a dead connection (0.36s CPU / 89min wall — true
full-sync time is 2m35s, no perf issue); repo housekeeping: 14 archived,
`react-firebase-authentication` deleted, all 13 mini-staging repos rescued
to `~/src/mini-rescue/` with pushed `mini-rescue-20260817` branches.

Turso-readers production leftovers:
1. ~~Laptop's `.env.local` needs `GROUND_CONTROL_MACHINE=laptop`~~ — **DONE
   2026-08-20, Nico appended it.** Matters now the laptop is the only machine
   running jobs, since `daily_summaries_machine` keys on it.
2. ~~Nothing syncs laptop→Turso between the 2:00am synthesizer write and the
   mini's 2:30am review read~~ — **MOOT 2026-08-20.** Both now run on the
   laptop, in sequence, over the same local DB, so there is no cross-machine
   window to miss. This resolved by co-location rather than by the
   sync-before-review-vs-retiming decision it was waiting on.

### Public data is stale again (moved 2026-09-07)
*Public data is stale again* — 9 unpublished weeks for prompt-lab, 4 prntd,
3 musicforge, 2 ibuild4you (`scripts/draft_public_refresh.py --list`). It goes
stale silently by design, and sat six weeks before a consumer noticed last
time. Drafting is cheap; the human review is the expensive part and the actual
privacy gate, so this waits for Nico to want it.

### `automation-dev` is DELETED (moved 2026-09-07)
**`automation-dev` is DELETED — Nico did it 2026-08-14, and nothing broke.**
This closes the only item that carried a live security edge. Verified by SSH
the same day, and the verification is worth reading because it overturns the
note it replaces:

- The `lights` container on phrpi still authenticates to HA — **200 from
  `GET /api/`** with its own credential, tested from inside the container so
  the value never entered a session.
- The container has been **up 28 hours without a restart**, so its environment
  cannot have changed. A still-valid token in an unrestarted container is proof
  the credential it holds was *never* `automation-dev`.
- Therefore the **2026-08-13 "correction" was itself wrong**, and the note it
  overturned was right the first time: **phrpi-lights holds its own separate
  token.** The HA UI listing one long-lived token was read as "there is only
  one"; what it actually showed is one token *of the ones created that way*.
  The lesson to keep: a UI list is evidence about the UI, not about every
  credential in the system — the authoritative test is whether the consumer
  still authenticates.
- Also corrected: the variable is **`HA_TOKEN`**, not `HASS_TOKEN` as this file
  said for two days. `HASS_TOKEN` is unset in the container. A rotation
  following the old instructions would have edited a variable nothing reads and
  "succeeded" while changing nothing.

Residual, both minor now: the plaintext copy in
`~/mini-staging/home/zshrc.mini` is a **dead** credential rather than a live
one, so it's cleanup rather than exposure — still delete it. And the mini's old
consumers (`deploy.py`, `tools/matter_diag.py`, `dashboard/ha_client.py`,
tests, `phrpi-lights/.env.tpl`) now reference a revoked token; they'll need the
new one whenever the HA deploy path is re-provisioned.

Separately, the token card was nearly mistaken for the **Refresh tokens**
card above it — those are login sessions (browser, iOS app), and deleting
one revokes a session, not an API token. Known consumers of the dead token (mini pre-erase grep): the
home-assistant repo (`deploy.py`, `tools/matter_diag.py`,
`dashboard/ha_client.py`, tests), `phrpi-lights/.env.tpl`, and the mini's
`.zshrc`. Separately, the mini was the HA *deploy machine* — the laptop
clone lacks `.secrets` and its ssh key isn't in the HA SSH add-on;
re-provisioning is queued in the home-assistant repo (coordinate there,
not with the decommission notes).

- ~~Rotate `automation-dev`~~ — **DONE 2026-08-14, deleted by Nico.** lights
  verified still authenticating (200) afterwards; it holds its own token.
  Only cleanup left: delete the now-dead plaintext copy in
  `~/mini-staging/home/zshrc.mini`.

### The nightly review email says "no new work" on days full of work — BOTH BUGS FIXED (moved 2026-09-07)
**The nightly review email says "no new work" on days full of work — BOTH BUGS
FIXED 2026-08-12.** Full diagnosis in `docs/history.md` / git history
(`877ea15`, `c332ac9`); what happened and what remains:

*Bug A, the window — FIXED in code, 2026-08-12; window logic survived the
2026-08-14 Turso refactor below, raw-session selection did not.* The job
fires at 2:30am and asked for **today**, structurally empty at that hour, so
`review_windows()` in `send-review.py` makes "Today" mean **yesterday's
completed lab-day** (Pacific) — that part is unchanged today. What's gone:
`send-review.py` no longer selects raw sessions at all (Task 2 of the Turso
refactor removed the read entirely; it composes from `daily_summaries`/
`weekly_rollups` instead — see the "Turso refactor DONE" line below). The
overlap-by-time-range logic that originally fixed raconte's 31-hour session
(`get_raw_sessions(overlap_utc=…)` + `day_helper.lab_day_bounds_utc`,
DST-correct) still exists and is still tested, but only at the store layer
(`scripts/test_send_review.py`, 7 tests) — nothing above it calls it anymore.

*Bug B, delivery — RESOLVED by unloading, not by repairing the sender.* The
laptop's 33 Resend 403s came from its stale Jun 6 `.env.local` using the
unverified `send.` subdomain. Per Nico's call 2026-08-12: the laptop's three
reader plists (`review`, `report`, `api-costs`) are **unloaded and parked in
`~/Library/LaunchAgents/disabled-readers-20260812/`** (reverse: move back +
`launchctl bootstrap gui/$UID/<plist>`), and the mini's current `.env.local`
was scp'd over (laptop's old copy at `.env.local.bak-20260812`). The mini is
now the only sender, which was the proposed split — accepted cost: nights the
mini is down (e.g. wipe day) get no review email. Still open, low priority:
a failed send still writes `review_snapshots` (the row records *composition*,
not *delivery* — nothing distinguishes them), and the #45 heartbeat
structurally can't see a last-step delivery failure because the artifact is
upstream of it. Also never explained: the laptop wrote no `review_snapshots`
rows for Aug 10-11 despite its job running — academic now the readers are
unloaded, but if it recurs on the mini, dig.

### Turso refactor DONE 2026-08-14 (moved 2026-09-07)
**Turso refactor DONE 2026-08-14** (tracked in the DB-ownership bullet below):
`send-review.py` no longer reads its **local** `sessions` table, so laptop
session detail reaches the Today section. `generate-report.py` was covered by
the same change.

### The trajectory heatmap's month labels were on a different scale than the grid (moved 2026-09-07)
**The trajectory heatmap's month labels were on a different scale than the grid
— FIXED 2026-08-14** (diagnosed 2026-08-12; Nico re-reported it from a
musicforge screenshot, which is what got it built). The data was always fine;
only the axis lied. `.heatmap-labels` was `justify-content: space-between`,
spreading 13 month labels across the **container's full width** (~1050px),
while `.heatmap` was 53 fixed columns of 8px + 2px gap = **530px**, left-aligned
and never stretched. The grid's right edge (today) therefore landed at ~50% of
the label row — the 7th of 13 labels, **Feb**. Six months of continuous work
read as "dead since March." The smoking gun: the renderer computed
`monthLabels.push({ idx: weeks.length, … })` and then rendered
`<span>${m.label}</span>`, throwing `idx` away — alignment was never
implemented. Second defect, same cause: the label row sat *outside* the
`overflow-x:auto` container, so on a phone it didn't scroll with the grid.

Fixed as agreed, and **the coloring stays on prompt count**: both rows now live
inside one `.heatmap-scroll` container wrapping a `.heatmap-track`
(`width:max-content`), and the label row carries the **same flex geometry as
the grid** — one 8px `.heatmap-labelslot` per week column, `gap:2px`, labelled
slots holding absolutely-positioned text plus a dot at the true column centre,
the convention `DateAxis` already established for the other six charts. `idx`
is finally read (`labelAt[i]`). Alignment is now **structural**: a label is
positioned by occupying its own week's slot, so there is no pitch constant to
keep in sync. `.heatmap-track` carries 16px of horizontal padding so the first
and last labels, which overhang their 8px slots, aren't clipped — applied to
both rows at once, so it can't pull them out of register.

`ActivityHeatmap` has exactly one call site (the project page), so this covers
every project at once. Verified by `node --check` over the extracted module
plus a class-defined/class-used sweep, then **confirmed by eye on prod
2026-08-14** (musicforge): month labels sit over their own columns in both
directions, dots line up, and the six months that read as "dead since March"
now read as the continuous work they were. Note that the sandbox cannot render
the app, so the eye check is not optional here.

### Prompt ratings: ABANDONED 2026-08-14 (moved 2026-09-07)
**Prompt ratings: ABANDONED 2026-08-14, don't revive it without a new idea.**
The live `prompts` table carries `utility`, `tags`, `notes`, `outcome` and an
`idx_prompts_utility` index; **0 of 1318 rows have ever been rated**, and the
columns are not even declared in `store/` (they exist only in the live DB and
in two test fixtures). Correcting the record: earlier notes claimed `/handoff`
offers rating and `/readup` surfaces utility-4+ prompts — **neither has ever
existed**. `grep -rn "utility" workflow/` returns exactly one hit, a comment in
`log-prompt.sh`. So this was never dead code over an empty column; it was an
empty column with no code at all, and the same claim is in the *global*
`~/.claude/CLAUDE.md` (lines 22, 27-29) describing `/prompts` and rating flows
that don't exist. The columns stay (harmless, indexed); the aspiration is
dropped. If it ever returns, the two ideas worth starting from are a one-word
in-the-moment marker (a `/good` command stamping the previous prompt — slash
commands are already filtered out of the table, so it can't pollute its own
data) or deriving utility from outcome rather than asking a human at all.

### The raw tier undercounted prompts by design — FIXED 2026-08-14 (moved 2026-09-07)
**The raw tier undercounted prompts by design — FIXED 2026-08-14.** The old
guess (that `log-prompt.sh` only sees turn-initial prompts) was **wrong**: it
runs on `UserPromptSubmit`, which fires per submitted message, mid-turn
interjections included. The real cause was a write-time filter,
`[ ${#PROMPT} -lt 20 ] && exit 0`. Every prompt under 20 characters was
silently dropped — "yes", "go ahead", "ship it". The fingerprint was exact:
`min(length(prompt))` over the whole table was **20**, with **zero** rows
below. That is a filter, not a distribution.

The damage was never the missing rows, it was the **shape** of the loss: a day
spent steering is mostly short prompts and rendered as a quiet day, while a day
spent writing specs rendered as busy. `daily_summaries.prompt_count` feeds the
trajectory heatmap and the KPI tiles, so the charts presented a filtered signal
as an activity record — the repo's signature failure again. It is also what
made "1 prompt for prompt-lab" on a six-turn day look like a lag.

Now: **store everything, label it, select at read time.** `prompts.kind` is
written by the hook from `scripts/prompt_kind.py` — the single implementation,
shared with `scripts/backfill_prompt_kind.py` so live rules and backfill rules
can't drift. Five kinds: `approval`, `correction`, `question`, `command` (a
bare `/slash` invocation), `spec` (everything else). **No rule consults
length**, pinned by a test that pads a prompt and asserts the label doesn't
move. A label is recomputable; a discarded row is not — that asymmetry is the
whole design, so misclassification is cheap and `--all --apply` relabels
everything.

Backfill applied to all 1353 existing rows: 81% spec, 17% question, 2%
correction, and — the diagnosis confirming itself — **0 approvals**, because
approvals were exactly what the filter had been deleting.

Three things fell out of the same change:
- **`prompts.context` now holds the whole last assistant message, trailing 2000
  chars** (was `head -1 | head -c 500` — the first *line*, averaging 124 chars,
  usually a lead-in rather than the proposal). Paired with `kind='approval'`
  this is what answers "what did I actually say yes to?". `base64` in the jq
  pipeline is load-bearing: `tail -r` makes the first *record* the most recent,
  but a message spans lines, so encoding each to one line makes "first record"
  and "first line" agree again.
- **A failed insert is no longer silent.** It used to go to `/dev/null`; it now
  appends to `~/.claude/hooks/log-prompt-errors.log`. The hook also ALTERs
  `prompts` defensively, because the table predates `store/`'s migrate path
  (the retired Flask dashboard created it) and bash never calls `migrate()` —
  without that, a DB lacking `kind` would fail *every* insert silently.
- `printf` replaced `echo` when escaping, since a prompt can now legitimately
  be exactly `-n` or `-e`.

**The discontinuity is annotated, not smoothed.** Counts before 2026-08-14 are
filtered and counts after are not, so every prompt-count series steps up once
on that date. `CAPTURE_FIX_DAY` + a `.heatmap-note` caption say so on the
chart. Backfill is impossible — the dropped prompts were never stored.
Deployed and confirmed on prod 2026-08-14.

The step won't actually be visible until enough post-cutover days accumulate,
so if a future session finds prompt counts jumping around mid-August and starts
hunting a bug, this is the answer. That is what the caption is for.

### DB ownership: DECIDED 2026-08-10 — Option B, federated (moved 2026-09-07)
**DB ownership: DECIDED 2026-08-10 — Option B, federated.** Raw stays
machine-local per the invariant; each machine synthesizes its own prompts and
pushes processed rows to Turso; the merge happens there; the always-on mini
keeps the reader jobs (review email, report, cost pull) because the laptop
being off must mean off. Nico ruled out running nightly work on the laptop
explicitly. The build-out this implies:
- Laptop gets its own `com.promptlab.synthesizer` + turso-sync LaunchAgents
  (its `/handoff` already covers most days inline).
- **FIXED 2026-08-14**: `send-review.py` and `generate-report.py` both used to
  read `get_raw_sessions()` — raw-tier, local-only, so the mini's review email
  missed laptop session detail and read "no new work" on busy days. Both now
  call `get_store("turso")` directly and read only
  `daily_summaries`/`weekly_rollups`, so the env-var-ordering trap
  (`store/turso_store.py:736` raises `NotImplementedError` on every raw
  method, e.g. `get_raw_sessions`) no longer applies. Residual risk, not a
  current state (see the what-runs-where entry above — only the synthesizer
  is loaded on the laptop today): if the laptop's readers are ever
  re-enabled without the mini also carrying this refactor, two machines
  would again compose nightly reviews from two different DBs.
- `daily_summaries` clobber — **FIXED 2026-08-14**: per-machine parts table
  (`daily_summaries_machine`) + deterministic merge at sync time
  (`merge_summary_parts`/`sync_daily_summaries` in `sync_to_turso.py`);
  `weekly_rollups` still has the same clobber shape, deferred until it bites;
  machine labels come from `GROUND_CONTROL_MACHINE` in each `.env.local` (not
  yet set on any real machine — that's a follow-up, not done by this commit).

### The week-grouping SQL filed every Monday under the previous week (moved 2026-09-07)
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

### musicforge Fly uptime line — BUILT 2026-08-29 (note added 2026-09-07)
`musicforge-fly` → `https://musicforge.fly.dev/api/health?db=1` went live 2026-08-29 as a deep+deep pair with the existing www line, so a Fly outage and a Vercel outage no longer render identically — that closes the ask left open at the foot of the entry below.

### UptimeRobot alerted nobody for six weeks — FOUND AND FIXED 2026-08-09 (moved 2026-09-07)
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

### Mini → headless (closet) migration (moved 2026-09-07)
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

### The wipe HAPPENED 2026-08-13 (moved 2026-09-07)
**The wipe HAPPENED 2026-08-13 — the mini is being re-purposed, and
RECONSTITUTING prompt-lab's services on the new mini is part of the plan**
(Nico's direction, same day: the wipe plan isn't done until the services are
back). The **mini-decommission agent/repo owns the checklist**; prompt-lab
owns its reconstitution spec, sent to them 2026-08-13: clone repo + venv →
copy staged `.env.local` → **MOVE** (not copy, then delete staging) the
frozen `prompt-history.db` back → restore the 39 memory dirs (478 files;
"44" in earlier notes counted project dirs without memory) → install
`workflow/` from the **fresh clone, never from pre-wipe backups** (repo
copies carry fixes the mini never had) → restore + bootstrap the 4 plists
(check hardcoded paths first) → verify **by artifact** after first overnight
(email arrives + `review_snapshots` row + heartbeats green). Sequencing
deliberately requested: land the `send-review.py` → Turso refactor *before*
the review plist is bootstrapped, so the reconstituted mini's first email
already sees both machines' work. **The full implementation plan is
`docs/turso-readers-plan.md`** — 5 TDD tasks for an Opus session: explicit
store backend, both readers onto processed tables, gate release, plus the
same-day clobber fix via a per-machine parts table (Nico's "simple is
better" call 2026-08-13 after weighing and rejecting mini-as-central-DB;
capture stays local-first, Turso stays the merge point). Execute AFTER the
mini reset, per Nico. **Until reconstitution, prompt-lab is
laptop-only** and the readers run nowhere (see the what-runs-where entry
below). Everything the mini held is staged on the laptop under
`~/mini-staging/`: the final `prompt-history.db` (frozen 2026-08-13 07:20,
11,240 prompts, taken after the LaunchAgents were unloaded and drift-checked),
all 39 claude-memory dirs (478 files), plists, job logs, zshrc/ssh config, SPAN env
files, and a 13-repo sweep of dirty/unpushed working trees (`repo-sweep/` —
sorting those is open curation work, worst case notemaxxing with 24 unpushed
commits). The relocate-don't-wipe debate is preserved in git
(`77dd316`/`d50c14b`/`55488f0`). Worth keeping from it: any future account split must *move* `~/.claude/prompt-history.db`,
never copy it — a second copy of every raw prompt is a privacy regression.
And the process lesson stands: *agreeing with an idea is not the same as the
idea being chosen* — this entry records a decision only because Nico stated
one.

### Copy review (#49) — batch 1 of ~4 DONE 2026-08-05 (moved 2026-09-07)
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

### The 80-name project list — CLEANED UP 2026-08-05 (moved 2026-09-07)
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

### Don't reach for a read-time exclusion list (moved 2026-09-07)
**Don't reach for a read-time exclusion list** — read-time allowlists were tried
twice in this repo and deleted both times for drifting; `private` on the row is
the equivalent that can't drift. Two gotchas hit while doing this: `alias.py`
takes two arguments and **zsh does not word-split unquoted variables**, so a
`for pair in "a b"` loop silently wrote the whole pair into the alias column;
and a full `sync_to_turso.py` runs past 120s, so the alias rows were written
straight to Turso (safe — `project_aliases` is upsert-only, unlike
`project_metadata`, which is cloud-direct and must never gain a sync leg).

### The uptime archive wrote on 2026-08-01 and not on 2026-08-02 — DIAGNOSED 2026-08-02 (moved 2026-09-07)
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

### Phase 3 of the uptime plan — COMPLETE 2026-08-02 (moved 2026-09-07)
- **Phase 3 of the uptime plan — COMPLETE 2026-08-02.** musicforge, bakerylouise and
  prntd all shipped `/api/health` and every monitor is repointed off its homepage
  (musicforge's lives only on `www.musicforge.org` — the `.app` domain 404s the path;
  bakerylouise skips the deep Sanity variant on purpose, ISR-cached; prntd is deep
  `?db=1`). raconte is settled: no backend ever, slot closed, the recountly.org
  monitor stays until they post teardown notice.

### Phase 5 — COMPLETE 2026-08-02 (moved 2026-09-07)
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

### `/api/private_history` Tier 1 — SHIPPED 2026-08-02 (moved 2026-09-07)
- **`/api/private_history` Tier 1 — SHIPPED 2026-08-02**, deployed and verified live
  end-to-end (auth'd smoke test passed). `SERVICE_HISTORY_KEY` in Vercel Production,
  value at `op://dev-secrets/prompt-lab-service-history-key/password`. Ball is in
  selected-projects' court to wire `lib/history.ts`. Tier 2 (narrative behind Garm)
  remains unbuilt by agreement. historyKey settled as `bakerylouise` (alias from
  `bakerylouise-v1`). **This endpoint has no allowlist of its own** — it accepts any
  project and is gated solely by the service key, so don't go looking for one. The
  8-key allowlist is the *public* tier's write gate (see the `public_history` bullet
  above); `bakerylouise` and `songscribe` were added to it alongside this work.

### #48 time localization — POLICY SET AND INSTANCES FIXED 2026-08-02 (moved 2026-09-07)
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


### Mobile pass, 2026-08-02 (moved 2026-09-07)
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

### Cross-repo work goes through `~/src/.handoff` — NOT a PR from here (corrected 2026-07-31)
This session dispatched sub-agents straight into `byside` and `selected-projects` to write their `/api/health` endpoints, because `docs/plan-2026-08-01-uptime-dashboard.md` phrased Phase 3 as "one small PR per repo, one sub-agent each." That was the wrong call and the plan's phrasing is the trap — **the repo boundary is the ownership boundary**, and each repo's agent owns its own conventions. Nico: *"put an action in the .handoff place for them to do the work, listen for their response. is that not clearly our way?"*
- **The practical tell, worth recognising early:** agents working in a sibling repo run from a cold permission slate — there is no `additionalDirectories` in `~/.claude/settings.json`, and that repo's own `settings.local.json` only loads in a session started there. A wall of permission prompts mid-task is the convention signalling it's being bypassed, not a config annoyance to route around.
- Both notes were posted, then archived with an honest outcome: Nico merged the PRs himself before either repo's agent replied, so the review the notes asked for never happened. The routes are theirs to change freely.
- Saved as memory `feedback-cross-repo-via-handoff`. **Remaining Phase 3 (musicforge, prntd) went out as handoff asks, not PRs** — the correct shape, for reference.

### ⚠️ OPEN 2026-08-02 — the uptime archive wrote on Aug 1 and NOT on Aug 2. Unresolved.
Verified two days after shipping: `uptime_daily` holds **9 rows dated 2026-08-01** (one per monitor — the pull works end to end) and **nothing for 2026-08-02**, checked at 20:20 UTC against a cron due at 15:00 UTC. Also confirmed healthy the same check: the bi-monthly report fired on the 1st (that 4-month-dead job is genuinely fixed), the review email ran, the synthesizer is current.
- **Ruled out, don't re-derive:** the production pull was reproduced locally against the same key — 9 monitors, ratios parsed correctly. `health_email_state` is empty, so emails are not paused (and the pull runs ahead of the pause check anyway). Nothing was deployed between the two days.
- **Could not determine:** whether the Aug 2 cron fired. **Vercel log retention is ~1 hour**, so by the time anyone looks, the 8am cron is long gone from the logs. That limit is itself worth remembering — post-hoc log forensics on this cron is not available, which is precisely why the artifact check has to carry the weight.
- **The one question that decides it is in Nico's inbox: did the health email arrive that morning?** Yes → cron ran, pull failed in prod only. No → cron never fired.
- **The gap this session created, and the proposed fix:** five jobs have freshness checks; the uptime archive has none. Adding `uptime_daily` to `HEARTBEATS` (2-day max age, ~10 lines + a test) would have surfaced this the same morning instead of by accident two days later. **Be honest about its limit:** it catches *cron alive, pull broken* — plausibly the current state — but **cannot catch *cron dead***, because the same cron writes the row and sends the report. That case degrades to "no email arrived," the weakest signal in the system and the one that hid the review email for sixty nights. Closing it properly needs a check outside the cron, and UptimeRobot's `HEARTBEAT` type is paid-only — which is what pushed us to artifact freshness originally. Known hole; don't let the heartbeat's addition be mistaken for closing it.

### Uptime dashboard phases 1+2 SHIPPED + DEPLOYED 2026-07-31 (#46 `842cafd`, #47 `96ace9d`)
Executed `docs/plan-2026-08-01-uptime-dashboard.md` the same evening it was written. 134 tests, ruff clean, both merges deployed green; `/api/uptime_overview` live and 401s anonymously. `uptime_daily` created on Turso (0 rows — **first write is the 8am cron**, and an empty archive after that means the pull failed silently: check the log, not the table).
- **The pull runs AHEAD of the pause check.** Pausing the health *email* for a week must not punch a week-long hole in the archive — independent artifacts. Test-pinned.
- **An unreadable archive returns `unavailable: true`, never an empty result.** Zero rows is the normal day-one state; letting a Turso failure render as "nothing collected yet" would rebuild the exact #45 bug. Same reasoning as the freshness checks failing loud while the pause lookup fails open.
- **`uptime_daily` is cloud-direct — no local copy, no leg in `sync_to_turso.py`.** Same class as `page_views`. Never teach the sync about it.
- **v2 `custom_uptime_ratio` is a STRING** (`"100.000-99.980-99.990"`, 1d-7d-30d) — split and float, or every downstream average is text. Third instance of this trap class after Turso's aggregates.
- **Frontend:** the per-day strip is statuspage grammar (fixed-height tick colored by bucket), deliberately NOT height-encoded bars — 99.9% and 100% are indistinguishable by height and that's the difference that matters; height encoding went to the response-time trend. A day with no row is grey, **never 0%** — the archive is never backfilled, so a gap is missing data, not downtime.
- **Not visually verified.** Both themes were checked by computed contrast, not by eye (screenshots were denied). Worth one glance at `#/health`.
- **Monitors repointed** (`1742464`): byside → `https://by-side.net/api/health?db=1`, pianohouse → `https://www.pianohouseproject.org/api/health?db=1`. **www, not the apex** — the apex 307s, and a monitor leaning on redirect-following is one setting away from a false DOWN. Both endpoints prod-probed before the repoint, per bug #40.
- **Open:** Phase 3's remaining repos (musicforge + prntd asked via handoff, awaiting reply; **bakerylouise-v1 has no handoff channel** — needs one created or a session in that repo), Phase 5 grow `TARGETS` + the test asserting it agrees with `HTTP_MONITORS`.
- **Phase 4 is CANCELLED — recountly is dead (2026-07-31).** It has become **Raconte**, a native iOS app (`~/src/raconte`, active; recountly's last commit 2026-07-29 is the pivot note). Un-gating its 401'd `/api/health` is dead work. `recountly.org` still answers (307) and still has a declared monitor in `scripts/uptimerobot.py` — **that monitor will start false-alarming the moment the deployment goes away**; drop it from `HTTP_MONITORS` and delete it in the UptimeRobot UI once the site actually comes down. An iOS app has no URL to poll, so Raconte does not inherit recountly's slot in the health convention.

### Public rollup backlog effectively CLEARED 2026-07-31 — 43 of 44 weeks published
selected-projects (4 weeks) and ibuild4you (6) published, synced, and verified live on `/api/public_history`; drift check clean. Only ibuild4you 2026-05-18 remains, and that is the deliberate skip (cost forensics + internal ops, nothing left after scrubbing) — it will reappear in every future draft by design.
- **Reading the envelope: the key is `rollups`, not `weekly_rollups`.** A probe using the wrong key reports 0 rows on a perfectly healthy endpoint.

### #45 SHIPPED 2026-07-31 — the health email now checks artifact freshness, not exit status (`1987440`, `e3a2f2c`)
`TARGETS` answers "is this URL up" and can never answer "did the nightly job run" — the failure class that's bitten us six times. `HEARTBEATS` in `web/api/health_report.py` declares five artifacts + a max age each, checked with `max(date)` over tables that **already sync to Turso**: review email/`review_snapshots` 2d, synthesizer/`daily_summaries` 2d, weekly rollups 10d, cost pull/`api_costs` 3d (Anthropic reports a day late — 2 would alarm on a healthy pipeline), bi-monthly report 20d. Rendered on `#/health` beside the target cards. 117 tests.
- **Deliberately NOT a synthetic ping.** A ping is a side-channel claim that the job ran and can succeed while the artifact is missing — precisely how the review email looked healthy for 60 nights. `max(date)` is the output itself. Still satisfies "outside the job": launchd on mini writes through the sync, Vercel reads. Prefer the real artifact wherever one exists; `heartbeat.py` (wired into all four jobs, **dormant**) is the fallback for a job with no queryable output.
- **Thresholds are DAYS, not hours** — every artifact is date-granular, so hours implies precision that isn't there. `2` for a nightly = one missed night quiet, two a breach. That is #45's stated bar (night two, not night sixty).
- **A failed check reports "could not check", never "fresh"** — explicitly NOT the fails-open pattern the pause lookup uses in the same module. Pause failing open is right (a Turso outage shouldn't block an email); freshness failing open would rebuild the exact bug. Test-pinned, along with "empty table = never produced", which is stale, not fresh.
- **It caught a real 4-month outage on its first live run.** `com.promptlab.report` had produced nothing since 2026-04-01: its plist ran `source <dotenv> && python …`, that file was deleted months ago, `source` failed, `&&` short-circuited, Python never ran — six silent failures and `reports/` just stopped growing. Fixed to invoke the venv python directly (`generate-report.py` calls `load_env()` itself, so the source was redundant AND fatal); verified by running it through launchd — 197s, `reports/2026-07-31-review-30d.md`, snapshot row written, check now reads fresh. **Next natural run is the 1st — confirm it fired.**
- **UptimeRobot is the sensor AND pager; prompt-lab samples nothing.** 5-min polling on independent infra, free tier, 3-month retention, so no Pi and no new launchd sampler is needed — settled after Nico offered both. Monitor set now declared in git: `scripts/uptimerobot.py` (dry-run default, `list`/`sync [--apply]`, never deletes). Added the missing **prntd** monitor (domain is **`.org`**, not `.com`) and repointed **ibuild4you** off its homepage to `/api/health`. 9 monitors, all green.
- **API facts, probed live — the docs are thin and partly wrong.** v3 (`Bearer`) provisions but has **no history endpoints** (`/logs`, `/response-times`, `/uptimes` all 404; `lastDayUptimes` is empty). **v2 legacy is the only source of history** and works on free: `custom_uptime_ratios=1-7-30` returns a **string** `"100.000-100.000-100.000"` to split+float, plus `response_times` and `logs`. Free = 50 monitors, 5-min, **10 req/min**, 3-month retention. **`HEARTBEAT` type needs a paid plan** (403 `009-005` at every interval/grace) — the free-tier comparison table says otherwise and is wrong; that's what sent this down the artifact route.
- **`op inject -i .env.tpl -o .env.local` is NOT a working workflow here and shouldn't be restored** — the template is the union of local + cloud secrets, so regenerating locally tries to materialize cloud-only values. Append single variables instead. Two traps found the hard way: `op inject` substitutes `op://` refs **inside `#` comments** (a commented reference is still live, and one unresolvable ref aborts the whole file), and `.env.tpl`'s `GITHUB_TOKEN` pointed at a long-renamed item — now `op://dev-secrets/PromptLabs GitHub Personal Access Token 2/token`. Local `.env.local` legitimately holds only the 8 pipeline vars; the other 9 are Vercel-side and were never missing.
- **Next: `docs/plan-2026-08-01-uptime-dashboard.md`** — phases 1+2 (uptime archive + `#/health` dashboard) are parallel-safe with a JSON contract fixed in the doc; phase 3 is five independent `/api/health` PRs.

### Build plan 2026-07-30 — ALL FOUR PHASES SHIPPED in one session 2026-07-29
`docs/plan-2026-07-30-build.md` executed end to end with parallel sub-agents (TDD, one PR per phase, Nico merged as they landed). 106 tests, ruff clean.
- **Phase 1 — `#/health` page (#36, `3a1382a`).** Live-poll page reusing `health_report.py` (no new function). To let readers see it, `?dry=1` opened to ANY authenticated role; send path stays cron/admin and an authenticated **reader asking for a send gets 403, not 401** — deliberate, "logged in but may not trigger this." Auth decision moved AHEAD of the target polling so anonymous callers can't make us do the work.
- **Phase 2 — #31 tile drill-downs + `#/activity` (#37, `60112ed`). #31 CLOSED.** Affordance diagnosis: the spend tile's `href` was never broken; its only cue was an inline `onMouseEnter` setting a hardcoded `#3a3a3a` — hover-only (dead on touch) and near-invisible in light theme. Now a persistent `↗` on navigating tiles, rotating `▾` on the toggle tile. New `GET /api/activity_timeline?days=` over `daily_summaries`, alias-folded, all three metrics per row so the metric switch is client-side. **Deliberately its own endpoint — never fold this into `/api/overview`, whose payload is SWR-cached for the home paint.** `active projects` expands inline (ratified over a `#/projects` page); private projects collapse to a `+N private` chip.
- **Phase 3 — #10 anonymous login events (PR #39, OPEN, `Closes #10`).** `callback.py` writes a beacon `login` row, `path=/login/<role>`, role checked against an allowlist so the email in scope at that call site cannot reach the row. Transport is a shared **`web/beacon_helper.py`** (added to `vercel.json` `includeFiles`) — NOT a self-HTTP POST to `/api/beacon`. `record_login` never raises; a metrics write must never cost a sign-in. **The plan's claim that logins surface in `#/visitors` "for free" was wrong** — `visitor_overview.py` filters `event='pageview'` on all four queries. That filter STAYS (logins can't inflate view counts); a separate `logins` block + Sign-ins panel carries the read path.
- **Phase 4 — #28 session merge (#38, `3c68d05`) — EXECUTED, #28 CLOSED.** `scripts/merge_cutover_sessions.py`, dry-run default. Ratified as-built: all 5 pairs merged, `started_at` back-dated to true conversation start, shells deleted after carrying NULL metadata. sessions 807→802, prompts 10710→10710, commits 2316→2316, no orphans, fk clean, re-run a no-op. Snapshot `~/.claude/prompt-history-backup-20260729T203101.db`. Local-only — Turso holds no `sessions`/`prompts`/`commits` tables.
- **The load-bearing idea, reusable:** the merge script's candidate rule is not a time-gap heuristic. It requires **identity proof** — the earliest entry in the bound row's Claude transcript (`~/.claude/projects/*/<id>.jsonl`) within 5 min of the unbound row's `started_at`, two independent recordings of the same conversation start. It earned it: `719 → 731` passes every time test with a 5m21s gap but is refused at −3117s skew. Left alone, out of scope: row 734 (`frontend`) shares a `claude_session_id` with 730 (`musicforge`) from a `musicforge/frontend` cwd; six 0-prompt unbound twins on 2026-07-21.
- **Recurring gotcha, now hit twice:** Turso returns `SUM()`/`COUNT()` aggregates as JSON **strings**. An explicit `int()` coalesce is load-bearing, not decorative — without it chart math concatenates instead of adding. Test-pinned in both new endpoints.
- **Next:** grow `TARGETS`. Done 2026-07-30: #39 merged + sign-in smoke test PASSED (role-only row in Sign-ins panel); first health email arrived on schedule but reported a **false DOWN** — see the health entry below.

### Public rollup backlog: 33 of 44 weeks PUBLISHED 2026-07-30 — the draft-to-artifact flow got its first real workout
The flow shipped 2026-07-19 had never actually been used end to end. It works. Published: **showcase (1), prntd (8), musicforge (10), prompt-lab (14)** — all live on `/api/public_history` through `week_of 2026-07-27`, drift check clean, synced. **Still drafted-but-unpublished: selected-projects (4) and ibuild4you (6 of 7)** — files are committed (`11ee9af`), only the `--apply` is owed.
- **The division of labour that made 44 weeks tractable:** the machine owns everything regex-able and *refuses to publish* on any of it — absolute `/Users/…` paths, emails, credential tokens, internal DB hosts, any line still starting with `>`, prose <15 words, prose ≥75% similar to the private source, project not on the allowlist. What's left for the human is the four things regexes structurally cannot see: **named people/orgs, identifiability-by-description, unreleased plans stated as fact, and commercially or personally sensitive detail.** Four questions per block, same four every time. That framing is what turned "review 44 weeks" from vibes into a checklist.
- **Real leaks the private text contained**, each caught only by the semantic pass: `Matt/BySide` (a person AND a client company in one phrase, ibuild4you 2026-06-15); `Eric` in three musicforge weeks; `Nico` in prntd + prompt-lab weeks; dollar figures (`$49.70`, `$19.43`, `$1,000/day`, `$9.40`); prntd's unreleased fee structure (`$1 ops fee`, `$5 org floor`).
- **Gap worth knowing: the path regex only matches `/Users/…`.** prompt-lab's 2026-04-27 private text carried `~/src/pianohouse`, which sails straight through. Tilde paths are a human-only catch.
- **Deliberately skipped: ibuild4you 2026-05-18.** Its substance is cost forensics plus an internal unstick-script — nearly all money figures and internal ops, 0 commits. A public version would be padding. It reappears in every future draft until published; that's the designed behaviour, not a bug.
- Where the cost story was the point, the shape survived without the number (the cents-vs-dollars misread became "roughly a hundred times what it actually was").

### The nightly review email was never off — it 403'd for 60 nights. FIXED 2026-07-30 (#44 merged, `0683d62`)
Nico asked "can I restart my weekly review emails, or why did we stop?" **Nothing had been stopped.** `com.promptlab.review` ran every night at 2:30am on mini, generated the review (real Sonnet spend, ~20k tokens/night), and was rejected by Resend: `REVIEW_FROM_EMAIL` was `reviews@send.prompt-labs.org`, a **subdomain never verified**. The apex `prompt-labs.org` *is* verified — which is exactly why the health email works from `health@prompt-labs.org`. Broke 2026-06-01, two days after the anomatom.com → prompt-labs.org migration; last good send 2026-05-31. Fixed by dropping `send.` from the address (`.env.tpl:11` + Nico's `.env.local`), verified with a real send.
- **Why it hid for two months, and the lesson:** `send_email()` called `sys.exit(1)` on the 403 — one line *before* `save_review_snapshot()`. So `review_snapshots` froze at 2026-05-31 and every signal read as **"the job stopped running"** rather than **"the job is failing at its last step."** The misleading artifact was the *absence* of rows. Now: returns `None`, snapshot persists either way, non-zero exit moved to the end so launchd still records it.
- **`--test-send`** exercises Resend alone with no Claude call. Verifying a from-address or key change went from a 4-minute Sonnet run to one second. Reach for it before ever running the bare command to test config.
- **Diagnostic that worked:** the log (`send-review.log`, launchd-only — a manual run prints to the terminal instead, so it looks empty) had 60 identical 403s. Check the job's *log* before concluding from *table rows* that a job isn't running.
- **#45 filed — ecosystem convention: alarm on artifact freshness, not job exit status.** Five incidents in one week shared this shape (this one; the health email's false DOWN; CI red 3 days with `deploy` showing *skipped* not failed; rock-art-fab's server tests silently skipping on missing deps; prntd's migration 0006 no-op'ing on prod; raconte's live finalize never running behind a fallback). Two mechanisms recur: **a fallback quietly covers the dead primary path**, and **absence is recorded as "nothing" rather than "failure."** Proposal: every recurring job declares a max artifact age; the daily health email (already in the inbox, already the ecosystem reporter) reports breaches. Bar for success — would it have caught this on night two? A `max(date)` on `review_snapshots` would have.
- Cadence unchanged by request: one nightly job, Saturday switches to a weekly tone (`send-review.py`, `is_weekly = today.weekday() == 5`). There is no separate weekly job.

### Header polish + login-flags fix SHIPPED 2026-07-30 (#41 `4eb0152`, #42 `92f6cd4`)
Both merged and live; Nico's 6-step smoke passed 6/6 (header layout, nav row, logout→buttonless check, re-login).
- **#41:** built/synced line directly under "Prompt Lab" at 0.61rem mono, green when today (Pacific) else grey, nav buttons together on their own row. Plus the real bug — after logout the Login screen was buttonless until reload, because the 401 body's `google_login`/`password_login` flags were fetched only in the mount effect. A shared `probeAuth()` now runs on **mount, logout, and mid-session expiry** (`web/index.html:795/808/863`); any path landing on the Login screen must go through it.
- **#42:** the signed-in email sat at nav-button scale, reading as a control. Own `.header-user` class at 0.61rem/0.65 opacity — identity, not navigation.
- **Deliberately NOT done: display names (nico/elijah).** With two accounts the beacon role already identifies the person — `/login/admin` is Nico, `/login/reader` is Elijah — so a name buys nothing the role doesn't already say, and costs the sign-in log's anonymity (#10 writes role only, allowlisted, so the in-scope email can't reach the row). **#43 filed for the trigger:** the day a second reader joins `READER_EMAILS`, role stops identifying anyone and the panel silently becomes uninformative. Fix then is a stable **opaque per-user id** (HMAC of email under a server salt, like `visitor_hash`) — never an email or a display name.

### First health email: false DOWN found + fixed 2026-07-30 (#40 merged); PR #41 MERGED 2026-07-30
The 8am email arrived on schedule but reported prompt-labs.org DOWN (401): `TARGETS` polled auth-gated `/api/info`, doomed to 401 anonymously. The site was fine. Fix (#40, `db71c63`, live-verified `{ok:true, db:true}`): new public `web/api/health.py` per `docs/health-convention.md` — shallow `{ok:true}`, deep `?db=1` 503s when Turso is unreachable — and `TARGETS` repointed at the deep URL. **Not just a URL swap:** the SPA catch-all serves `index.html` 200 for unknown paths, so pointing at a nonexistent path would have flipped to a permanent false UP; regression test pins the target. Nico upgraded the UptimeRobot prompt-labs.org monitor to the deep URL same day. Tomorrow's email should read 2/2 up with `db ok`.
PR #41 merged 2026-07-30 (`4eb0152`) — see the header entry above.

### System health reporting — first slice SHIPPED + LIVE 2026-07-29 (#34, PR #35 `683bcec`)
Accepted garm's 2026-07-29 handoff proposal: prompt-lab owns ecosystem health **reporting**; immediate alerting stays on independent infra. Split matters because Garm consumers now fail closed (Garm outage = ecosystem lockout) and prompt-lab shares the Vercel+Turso+Resend stack — watcher would die with watched.
- **Live:** `GET /api/health_report` + Vercel cron `0 15 * * *` (~8am Pacific, first send 2026-07-30). Polls `TARGETS` (garm deep health `?db=1` with db/howl-staleness detail + prompt-labs.org), emails via Resend. Footer: HMAC pause-for-a-week link (state in Turso `health_email_state`, cloud-direct no-sync like page_views; pause check **fails open** so Turso-down never blocks the report), copy-pasteable tune-up prompt, per-send joke (Haiku `claude-haiku-4-5-20251001`, canned fallback — email always sends). Cron auth = `CRON_SECRET` bearer; admin cookie works for manual runs; `?dry=1` previews without sending. 9 tests (83 total). Convention doc: `docs/health-convention.md` (`GET /api/health` → `{ok:true}`, optional deep variant non-2xx on dependency failure; garm is the reference).
- Env (Production, verified applied before deploy): `CRON_SECRET` (1P `Prompt Lab Cron`), `RESEND_API_KEY` (1P `Resend`), `HEALTH_TO_EMAIL`. Prod-verified via Playwright: 401 unauth, 403 bad pause token, cron registered (`vercel crons ls`), garm target healthy.
- **UptimeRobot is live** (Nico's account, alerts → nlovejoy@me.com): garm deep-health monitor + homepage monitors on 7 sites (prompt-labs, ibuild4you, byside, pianohouse, bakerylouise, musicforge, recountly). Homepage checks upgrade to `/api/health` URLs as apps adopt the convention. No CLI used; bulk CSV was one-shot, deleted.
- **CI ruff pinned to 0.15.22** same PR — unpinned `pip install ruff` grabbed a new release 2026-07-29 (339 new-rule errors on a docs-only push), starving deploy. Local ruff passing while CI fails on a docs commit = version drift, check the pin first.
- **Remaining #34:** `#/health` dashboard page (live-poll like Todos, later overlay UptimeRobot read-API uptime %s); grow TARGETS; denial count line once garm #7 exists (garm channel will post the shape). Verify first email arrives 2026-07-30 + pause link works.

### Read-time public counts projection — SHIPPED + LIVE 2026-07-21 (`af0b387`)
selected-projects wanted weekly `session_count`/`commit_count` for their public sparkline; they proposed a nightly writer into `public_weekly_rollups`. We took the goal, rejected the transport. `/api/public_history` now computes counts **at read time**: for a project opted in via the new `project_metadata.public_counts` flag, it overlays counts-only weekly rows (`public_summary: null`) projected from the private `weekly_rollups` table (mapping its `week_start` → the public `week_of`), for weeks with no published prose row. Published prose rows win their week. Same envelope — consumer already renders NULL-summary rows, zero change their side.
- **Why this transport:** preserves the "no automated writer to public tables" invariant (the strongest guarantee in the system), no second copy to drift, always fresh, reads Turso's *merged* rollups. This is literally Tier 1 of the `/api/private_history` design (§ below) — one implementation serves both.
- **`public_counts` is a REAL gate** (`web/api/project_metadata.py`), admin-set data-as-truth, distinct from the cosmetic `private` flag. Prose-safety is structural: the projection query selects numeric columns only (never `narrative`/`highlights`), pinned by a test. Opt-in check is best-effort so the public endpoint never 500s.
- **Seeded 7 projects LIVE** via `scripts/seed_public_counts.py --apply` (dry-run default): ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase, split-recording (counts-only — no prose published). Verified on prod: prompt-lab merges 11 published prose weeks + 11 projected counts-only weeks.
- **`am-i-an-ai` dropped** from `docs/public-allowlist.txt` (now 6 keys; site removed lojong) AND its 3 public rows unpublished via `scripts/unpublish_public.py` — because public_history has no read-time allowlist, dropping the text file alone would have kept serving the rows. Drift check clean.
- Live-status note posted to selected-projects handoff channel. `drafts/handoff-reply-public-counts-2026-07-20.md` is now historical.
- **Deferred:** the top-level aggregate (`total_sessions`/`first`/`last`) still counts only *published* sessions — the counts split only fixed the weekly rollup array. Fixing the aggregate is the rest of `/api/private_history` Tier 1.

### Public data was never stalled — there was no producer. Draft-to-artifact refresh SHIPPED 2026-07-19
selected-projects reported (handoff) that weekly rollup publishing had "stalled repo-wide" — nothing published in ~6 weeks for any key, `split-recording`/`recountly` never published at all. **The symptom was real; the inferred mechanism was wrong, and that distinction is the useful part.** The private producer is healthy (`daily_summaries` current to the day, `weekly_rollups` through the last completed week). The *public* tables have no automated writer and never did: the only things that ever wrote them are the hardcoded one-shot `backfill_public_*.py` scripts whose rows are literal Python constants, and `sync_to_turso.py` only propagates rows that already exist locally. Every observed `week_of` is just when that project's backfill script was last hand-run. **Diagnostic lesson: a frozen public tier is the designed steady state here, not a broken job — check whether a producer exists before debugging why it stopped.**

Root cause of the freeze: `/handoff`'s public-write steps were deleted 2026-06-13 (correctly — they fired for every repo incl. client work and auto-propagated to public Turso), but nothing replaced them, so refresh required remembering to hand-edit a one-shot script. **Fix shipped as the draft-to-artifact flow** CLAUDE.md already recommended:
- `scripts/draft_public_refresh.py <project>` — read-only; diffs private `weekly_rollups` against published `public_weekly_rollups` (alias-folded), writes `drafts/public-<project>-<date>.md` with each unpublished week's private narrative **blockquoted** as source material plus an empty `PUBLIC` block. `--list` shows the per-project backlog; `--all` defeats the 8-week cap.
- Human (or `/handoff` step 4.5) writes each `PUBLIC` block **from scratch**, reviews, commits.
- `scripts/publish_public_draft.py <file> [--apply]` — dry-run default. **Refuses** any project absent from `docs/public-allowlist.txt`; blocks absolute paths, emails, credential-shaped tokens, internal DB hosts, unedited blockquotes, prose <15 words, and prose ≥75% similar to the private source (the "nobody actually rewrote it" check). Writes local only — `sync_to_turso.py` propagates.
- `/handoff` step 4.5 surfaces the backlog and offers to draft, but is explicitly told **never to run the publish step** — the human review of the committed file *is* the privacy gate.
- 21 tests in `scripts/test_public_draft.py`, wired into CI. Verified: leak/similarity/allowlist refusals all fire (correctly refused `bakerylouise-v1`), `--apply` writes correct rows against a throwaway DB, real DB untouched.

**Backlog as of 2026-07-19** (`draft_public_refresh.py --list`): prompt-lab 12 weeks, musicforge 8, ibuild4you 6, prntd 6, selected-projects 2, showcase 1, am-i-an-ai 0. Nothing published yet — drafting + review is the user's call.

Incidental finding: Turso holds 11 `prompt-lab` public rollups (newest `2026-05-25`) vs 10 locally (newest `2026-05-04`) — a stray Turso-only row, almost certainly a pre-2026-06-13 `/handoff` write. **Turso is not a strict sync-superset of local** for these tables (sync only upserts; it never deletes). Harmless but worth knowing before trusting a local-only count.

Still open: `split-recording` and `recountly` have never published and aren't on the allowlist — publishing them is a manifest decision (consumer's MDX + `docs/public-allowlist.txt`), not a bug fix. Undecided.

### selected-projects tiered disclosure — `/api/private_history` design agreed, NOT yet built (2026-07-19)
selected-projects is adding tiered disclosure: anonymous visitors see the public showcase, signed-in collaborators see deeper per-project history. Authz comes from Garm (`garm.prompt-labs.org/gnipahellir`). **prompt-lab does NOT become a Garm consumer** — per `docs/garm-needs-assessment.md` it has two shared secrets and no per-user identity. selected-projects owns identity, asks Garm, and on `allowed` calls a new prompt-lab endpoint with a **shared service key**. prompt-lab trusts its caller and never learns the end user's email; PII surface stays zero.

**The load-bearing fact for this design: Turso contains no `prompts`, `sessions`, or `commits` tables at all.** Raw prompt text, commit messages, hostnames, and local paths are physically unreachable from `web/`. That's the strongest guarantee in the system — preserve it by never adding a sync leg for them, not by filtering at read time (read-time allowlists were tried twice and deleted both times for drifting).

Recommended payload, sent to the consumer 2026-07-19, awaiting their reply on sequencing:
- **Tier 1, unconditional — real metrics.** The public endpoint's `total_sessions` / `first_activity_at` / `last_activity_at` are computed over *published* sessions, so they're materially wrong (musicforge reports 126 against a much larger truth, and every "inception" date is really the earliest hand-published session). Tier 1 = full all-time activity array, true first/last/totals, weekly cadence with counts, `category`/`status`. Counts and dates only — structurally incapable of leaking prose, and always fresh.
- **Tier 2, opt-in per project — private weekly narratives** (`weekly_rollups.narrative`/`highlights`). Must be opt-in, not blanket: the synthesizer writes every project's narrative with the same code and no scrubbing step, so nothing in the schema separates safe from unsafe. Concrete evidence — musicforge's 2026-07-13 narrative reads like release notes; bakerylouise-v1's the same week names the client, her staffing plans, and characterizes her ability to give feedback. Gate on a `project_metadata` column, default off.
- **Out:** all cost/$ figures, Anthropic workspace names (often literally client names), `claude_code_usage` actor/org fields, `page_views`, `review_snapshots`, and row-level `id`/`model`/`created_at` (ids are a global monotonic counter — they leak corpus size and cross-project ordering).
- Contract: bearer auth on a shared secret, alias-folded project key, unknown/un-opted-in project → empty `200` with the same envelope, never 500/403.

### Phase A (§2.3/§2.4 + #30) — PR #33 OPEN, tests green, AWAITING NICO MERGE (2026-07-22)
Sub-agent built it per `docs/phase2-oauth-plan.md` steps 5-6: beacon.py drops hits when `BEACON_SALT` unset (no more `AUTH_SECRET` fallback, still opaque 204), #30 fixed (`google_login` flag in the 401 body gates the Google button — previews show password form only, closes #30 on merge), docs swept (`.env.tpl`, README, data-and-access, roadmap incl. its never-happened "flag for one deploy" claim corrected). https://github.com/nicolovejoy/prompt-lab/pull/33 — merge deploys to prod. **Manual env state:** `AUTH_READ_SECRET` deleted from Vercel (all envs; it only existed in Production) — preview reader login is dead as accepted. **Still owed: Preview + Development `BEACON_SALT`** — blocked mid-attempt because the `op` CLI lost its desktop-app integration (1Password app → Settings → Developer → "Integrate with 1Password CLI", then `op read "op://dev-secrets/prompt-lab-beacon-salt/credential" | vercel env add BEACON_SALT preview` and same for `development`; verify the op item path in the app first — it was never confirmed). Until set, previews/dev silently drop beacon hits once #33 deploys. Then Phase B: #31 KPI drill-downs + `#/activity` (parallel agents, TDD, spec in the issue); Phase C if room: #10 login beacon event.

### Phase 2 §2.1+§2.2 Google OAuth — SHIPPED + LIVE-VERIFIED 2026-07-21 (PRs #29, #32); §2.3/§2.4 cleanup NEXT
The keystone landed. Full spec + settled decisions in `docs/phase2-oauth-plan.md` (committed, kept current — read it before touching auth). Built TDD with sub-agents (tests red-first, 74 in `test_web_api.py`), live-verified end-to-end by Nico (Google sign-in, logout, prod probes).
- **What's live:** prod is Google-exclusive (`ADMIN_EMAILS` → admin; **`READER_EMAILS` → reader, added same day for Elijah `elovejoy5@gmail.com` — full read access, no Ask/metadata**; admin wins on overlap; anything else → readable 403). Previews keep password login (401 body's `password_login` flag drives the form). Token payload `{exp, role, email}`; `verify_token` returns the dict and requires BOTH `role` and `email` **keys** (key-presence not truthiness — `email: null` password cookies verify, legacy `{exp,role}` cookies rejected; that key requirement is the load-bearing subtlety). Fail-open admin defaults removed server- AND client-side. SameSite=Lax. HMAC `state` (10 min, deliberately not browser-bound — single-admin trade-off, documented). Callback checks `aud` + `email_verified`, html-escapes error pages (reflected-XSS was found in review, test-pinned).
- **Env done (Production):** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (1P item `Prompt Lab Google OAuth`), `ADMIN_EMAILS`, `READER_EMAILS`. New `vercel env add` trap discovered: the CLI's "Store as sensitive?" + Preview "Git branch?" prompts eat piped stdin — `--force -y` fixes the former, nothing fixes the latter (Preview adds hang; avoid piping Preview writes).
- **§2.3+§2.4 remaining:** remove `beacon.py`'s `AUTH_SECRET` fallback, delete `AUTH_READ_SECRET` from Vercel (kills preview *reader* login — accepted), set Preview/Dev `BEACON_SALT`, docs sweep (`README.md:85`, `docs/data-and-access.md:37,42`, roadmap §2.1's stale line refs). `AUTH_SECRET` is demoted not retired: still the HMAC signing key everywhere + preview password.
- **Known quirk, filed as #30:** preview deploys show the Google button but its redirect URI is pinned to prod — clicking it on a preview logs you into prod.

### Next session plan (updated 2026-07-31, post-#45) — spec is `docs/plan-2026-08-01-uptime-dashboard.md`
Written to fan out to sub-agents; read it before coding. **Open, in order:** (1) **Phase 1** uptime archive — `uptime_daily` in Turso (cloud-direct, **no sync leg**, same class as `page_views`), pulled from v2 `getMonitors` on the health cron's **send path only** (never `?dry=1` — readers reach that), plus `web/api/uptime_overview.py`; (2) **Phase 2** uptime % / sparklines / response-time trend on `#/health` — parallel-safe with Phase 1, JSON contract fixed in the plan; (3) **Phase 3** `/api/health` for byside, bakerylouise-v1, selected-projects, musicforge, prntd — five independent PRs, ibuild4you is the reference impl; (4) **Phase 4** un-gate recountly's `/api/health` (currently 401 — pointing a monitor at it now would false-DOWN forever, bug #40); (5) **Phase 5** grow `TARGETS` and add a test asserting it agrees with `HTTP_MONITORS`. **DONE 2026-07-31 (same evening the plan was written):** phases 1+2 shipped and deployed (#46, #47), byside + selected-projects `/api/health` landed and both monitors repointed, `UPTIMEROBOT_API_KEY` is in Vercel Production, and the two drafted public refreshes are published live. Remaining: Phase 3's other three repos (bakerylouise-v1, musicforge, prntd — **via handoff asks, not PRs from here**), Phase 4 recountly un-gate, Phase 5 `TARGETS`, and garm #7's denial line (`GARM_REPORTING_KEY` shipped). **Watch the GitHub Actions budget:** cycle resets 2026-08-01; `deploy` `needs: test`, so a starved run shows as *skipped*, not failed. Deferred: #14 (own session), #27 Garm rollout, private_history Tier 1, UptimeRobot paid plan / real HEARTBEAT monitors.

### Previous session plan (2026-07-30, post-header/review-email) — items 1-3 now DONE
`docs/plan-2026-07-30-build.md` is fully executed (see the block at the top of Next Steps) — Phase 2 OAuth was already closed out by `c0401c4`. The 2026-07-30 session merged #41/#42 (header, smoke-passed) and #44, and root-caused the dead review email. **Open, in order:** (1) confirm the 2026-07-31 ~8am health email reads 2/2 up with `db ok` + test the pause-a-week link; (2) confirm the 2:30am review email actually lands now that the from-address is fixed — first unattended send is the night of 2026-07-30→31; (3) **#45** ecosystem heartbeat-freshness alarming — the convention Nico asked for, and the thing that would have caught the review email on night two; (4) publish the two drafted-but-unpublished public refreshes — `drafts/public-selected-projects-2026-07-30.md` (4 weeks) and `drafts/public-ibuild4you-2026-07-30.md` (6 weeks), review done, only `--apply` + `sync_to_turso.py` owed; (5) #34 leftovers: grow `TARGETS`, garm #7 denial line (garm shipped `GARM_REPORTING_KEY` for it), UptimeRobot uptime-% overlay on `#/health`. **Watch the GitHub Actions budget:** 1,803 / 2,000 min used as of 2026-07-29 with the cycle resetting 2026-08-01 — the `deploy` job `needs: test`, so a starved run shows as *skipped*, not failed, and no prod deploy goes out silently (the exact 3-day-blind failure mode from 2026-07-09). Deferred deliberately: #14 (own session), #27 Garm rollout, private_history Tier 1 (awaiting selected-projects), public rollup backlog (human-gated — 6 projects, 44 weeks).

### Fake `agent-*` projects on dashboard — FIXED 2026-07-19 (`eb5353f`)
Sessions running inside Claude Code agent worktrees (`<repo>/.claude/worktrees/agent-<hash>`) were logged by `log-prompt.sh` under the worktree basename, creating 8 fake projects that the synthesizer summarized (real Sonnet spend) and synced to the dashboard. Hook now resolves worktree cwds to the repo and skips `<task-notification>` blocks (harness output that passed the length/`<command-` filters). Leaked rows purged from mini local, Turso, and laptop local via new idempotent `scripts/cleanup_agent_worktree_rows.py` (dry-run default, `--apply`; matches `^agent-[0-9a-f]{15,}$` only). Both machines ran `install.sh`. Verified via sandboxed-HOME hook runs (worktree→repo, notification skipped, normal cwd unchanged).

### /resync 2026-07-18 — #12 and #24 closed, #27 filed
CI has been green since 2026-07-09 (issue #12 was stale) — closed. Garm (#24) is shipped and live in production (`garm.prompt-labs.org`, ibuild4you consuming with verified dual-write) — closed, rollout continuation tracked in **#27**. Also confirmed via `/readup`: still open — Vercel `preview`/`development` envs hold the dead `ANTHROPIC_API_KEY` (prod is fixed); beacon salt decouple (§2.0) not yet started; Phase 2 OAuth is slated for next session on mini per the 2026-07-16 laptop session's decision.

### Ask feature 500s — FIXED 2026-07-14 (no key was minted)
Nico reported `/api/ask` returning 500 (surfaced on `#/todos`, but Ask is used dashboard-wide). Root-caused via `vercel logs prompt-labs.org --status-code 500 --json`: Vercel's `ANTHROPIC_API_KEY` got `401 Unauthorized` from `https://api.anthropic.com/v1/messages` — a credential problem, not a model/code one (`claude-sonnet-4-6`/`claude-opus-4-6`/`4-7` in `claude_api.py` are all still active). Todos' by-type classification still looked fine because its cache covers existing issues and hadn't needed a fresh API call.

**The first diagnosis was half wrong, and the correction is the useful part.** It concluded the key was dead and unrecoverable (Anthropic reveals a value only once, at creation) and that a new key had to be minted. In fact:
- **`prompt-lab-key-1` was alive the whole time** — verified by authenticating it against `/v1/messages` (HTTP 200). Single-reveal applies to the *console*, not to a value already saved in 1Password at creation. It's stored at `op://dev-secrets/prompt-lab-key-1/credential` and is what `.env.tpl:5` references.
- That's why the nightly synthesizer and review emails never broke — only the cloud dashboard did. **A healthy local pipeline is proof the key is fine and only the cloud copy is stale.**
- Vercel held a **different, older** key: its `ANTHROPIC_API_KEY` var was created 109 days ago vs. the op item's ~30. The age gap was the tell that these were two keys, not one dead one.

Fix was to copy the good value into Vercel: `op read "op://dev-secrets/prompt-lab-key-1/credential" | vercel env add ANTHROPIC_API_KEY <env> --force -y`, **one command per environment**, then `vercel --prod`. Verified working on prod 2026-07-14 (`/api/ask` → HTTP 200, was 500/401). **Production is done; `preview` + `development` still hold the dead key** — preview matters (Ask 401s on PR preview deploys), development only affects `vercel dev`.

**Two traps, both hit for real getting there — see `docs/roadmap-2026-07.md` §0.1:** (1) **Never pipe through `tr -d '\n'`.** `vercel env add` takes no value argument — it opens an interactive `? Value?` prompt and reads one line from stdin, so the newline is the *submit*, not part of the value. Stripping it makes the CLI read all 108 chars then block forever on an Enter that never comes, writing nothing and exiting without error. Symptom: `? Value?` + asterisks and **no `Overrode`/`Added` line**. (2) **Don't wrap it in a `for` loop** — the first prompt seizes the TTY and eats the rest of the loop's stdin, so iterations 2+ silently write nothing. **Always verify with `vercel env ls`:** a good write reads seconds old, and a partial write shows as a split (`Production | 45s ago` vs `Development, Preview | 109d ago`). Env vars apply at deploy time, so a redeploy is required either way.

**Next credential scare: check the secret store for a working value, and compare var ages, BEFORE concluding anything is unrecoverable.** The op record is `prompt-lab-key-1`; don't create a second one (Vercel has its own env store and never reads `.env.tpl`). Don't use `ANTHROPIC_ADMIN_KEY-4-prompt-lab` or `admin-cost-tracking-2026-05` (the item `.env.tpl:6` actually references for `ANTHROPIC_ADMIN_KEY`) — both are Admin-API-only, invalid for `/v1/messages`. Known consequence: local and prod now share one key, so revoking it kills both; mint a Vercel-only key if that isolation is ever wanted.

### Phased roadmap — `docs/roadmap-2026-07.md` — START HERE (its STATE OF PLAY block is the live status)
Phase 0 unblock → Phase 1 #23 metadata → Phase 2 Google login (the keystone) → Phase 3 #10 → Phase 4 Garm rollout (#27, was #24) → Phase 5 #14 tokens. Each phase has pass/fail criteria.

**Status 2026-07-14: Phase 0 essentially done** (Ask fixed + verified on prod; recountly deployed, Git-linked, beacon firing) **and Phase 1 shipped** (#23, PR #26). Remaining Phase 0 scraps: beacon fan-out for prntd + musicforge, verify Preview's Anthropic key (#12 closed 2026-07-18, CI green).

**Next: §2.0 — decouple the beacon salt.** `AUTH_SECRET` is overloaded three ways — admin password (`login.py:22`), HMAC token-signing key (`auth_helper.py:16`), and **the beacon's visitor-hash salt** (`beacon.py:73`). Retiring it without first splitting out `BEACON_SALT` silently rotates every visitor hash and breaks `#/visitors` continuity at the seam. Small, safe, independently correct — do it first even if Phase 2 then stalls.

**Phase 2's design question is SETTLED (2026-07-14): hand-roll OAuth in Python, zero new deps.** The "no `package.json` → no Auth.js → must convert to Next.js" chain is a false constraint. Because this is a confidential client doing its own server-side code exchange, the `id_token` arrives directly from Google over TLS — so **no JWT signature verification, no JWKS fetch, no crypto dependency** is needed (Google's docs sanction exactly this). It's ~150 lines of `urllib` in a 12th handler. Rejected: Next.js conversion (rewrites everything, unrelated), mixed Node+Python runtime (cookie-format interop = option A's work plus a second runtime), third-party auth (same interop, plus vendor + bill, for a one-person admin). Full reasoning in the roadmap's Phase 2 DECISION block. The real work is the `AUTH_SECRET` overload above and `SameSite=Strict` (breaks the OAuth callback → must become `Lax`).

**2026-07-16: Nico decided to do Phase 2 (§2.0 + §2.1 OAuth) on the mini, next session.** Effort estimate discussed: small-to-medium, ~3-4hrs end to end (§2.0 beacon-salt decouple ~15min, §2.1 OAuth flow ~1-2hrs, §2.2-2.4 mechanical) — the design fight is already settled, so this is spec-execution, not open-ended design. Sonnet is the right model tier for it (Opus not needed unless the `AUTH_SECRET` overload or `SameSite` landmine causes a non-obvious break). Machine choice doesn't matter technically (Vercel/Turso are cloud-side, both machines' harnesses verified identical) — picked mini because that's where Nico will be next. Also this session: first-ever `/resync --light` on the laptop (marker never existed there before) came back clean, no CLAUDE.md drift; 7 stale-but-merged remote branches (PRs #13, #15-#20) deleted from origin.

### Turso staleness warning recalibrated (SHIPPED 2026-07-18)
byside reported (handoff, 2026-07-17, now archived) the SessionStart Turso warning firing on a ~1-day-old *successful* sync. Root cause was ordering, not just threshold: the synchronous hook composes the warning BEFORE the async `turso-sync-maybe.sh` runs, so any >24h idle gap warned moments before the sync caught up. Fixed in `32b78b6`: warn only when the stamp is ≥48h old AND the newest `~/.claude/.turso-last-sync.log` line isn't an `ok` (i.e. retries are actually failing), quoting the failing line. Hook logic verified against 4 stamp/log scenarios via a sandboxed-HOME run. Laptop installed; mini caught up 2026-07-19 (`install.sh` run during the agent-worktree fix session — work.zsh badge/`--name` and readup step-9 fallback delivered with it).

### Feature-request batch 2026-07-13 → issues #21–#24 (all four SHIPPED; #24 closed 2026-07-18, follow-up #27)
Nico's checklist (screenshot) triaged into a 4-step sequence, all filed:
- **#21 + #22 — mobile chart passes (SHIPPED 2026-07-13, phone-verified).** PR #25, per `docs/plan-mobile-charts.md`: both `#/visitors` and `#/costs` charts scroll horizontally within their own panel opening at the recent end (mirrors #19's heatmap fix), floating hover tooltip gated to `hover: hover` pointers with a tap-to-select breakdown panel replacing it on touch, four two-column legend grids collapse under 600px via `.two-col`, costs legend gets per-project spend-share bars. Live phone test passed same day. Follow-up noted, not filed: `CostChart` (project detail) and the home activity chart have the same hover-only/two-col pattern.
- **#23 — project metadata layer (SHIPPED 2026-07-14).** Turso-native `project_metadata` table: `category` (Music/Art/Collabs/Tools/Other — display-only, NOT the sharing unit) + `private` (cosmetic hide-toggle + muted treatment) + `status` (active/dormant), admin-editable from the project page. **The plan's premise was wrong and the survey corrected it:** `sync_to_turso.py` never wrote the `projects` table and Turso had no `projects` table at all, so the feared "sync clobbers a cloud-set value" bug could not happen — the real gap was the inverse (project metadata never reached the cloud). `status`/`category` already existed in local SQLite (`store/sqlite_store.py:159-167`); only `private` was new. So this shipped as *create-in-Turso*, not *stop-clobbering*, following the `issue_categories`/`page_views` precedent: cloud-direct, no local copy, **no sync leg** — `sync_to_turso.py` must never learn to write it (that's what makes drift structurally impossible). Pieces: `scripts/create_project_metadata.py` (idempotent DDL), `web/api/project_metadata.py` (GET reader / POST admin-only, alias-folded, partial updates never reset a sibling field), metadata folded into `/api/overview`, editor + badges + private hide-toggle in `web/index.html`, 8 tests. Explicit status now overrides activity-derived dormancy in the picker and the KPI tile (un-annotated projects behave exactly as before) — this closes the status-toggle item stalled since 2026-05-28. Also fixed while verifying: the home activity chart legend still showed hidden private projects' names, defeating the toggle. `private` is **cosmetic only** — it is not the public-data gate and does not gate the API; see `docs/data-and-access.md`.
- **#24 — Garm (CLOSED 2026-07-18, SHIPPED, follow-up #27): per-repo per-user access control, ecosystem-wide.** Live in production at `garm.prompt-labs.org` (repo `~/src/garm`, Next.js API-only + Neon Postgres + Drizzle, `/gnipahellir` authz endpoint mapping `(email, project) → role`). ibuild4you is the first live consumer: 32/32 real grants seeded, dual-write verified working both directions 2026-07-17 (grant on membership add, revoke-recompute on removal). Howl denial-digest email shipped and verified (Resend sending domain confirmed 2026-07-16); consumer API keys scope per-project (2026-07-17). Design/build history (needs-assessment, ibuild4you-owns-build-out decision, bespoke-v1-not-OSS-authz-engine rationale, passcode retirement) preserved in `docs/garm-needs-assessment.md` and `~/src/garm/docs/build-plan.md` — not repeated here. **Remaining work tracked in #27:** finish ibuild4you's passcode-retirement cutover (PR D), onboard byside next, evaluate musicforge/recountly/selected-projects case by case, bakerylouise stays out of scope (Sanity's own role system), and decide whether prompt-lab itself becomes a Garm consumer once Phase 2's OAuth migration lands.

### Mobile readability pass: fonts, contrast, light/dark toggle (SHIPPED 2026-07-09, LIVE-VERIFIED 2026-07-10)
Nico's ask: cloud dashboard text too small/low-contrast on mobile ("old eyes"). Four PRs, in order, each responding to live feedback on the previous one — landed in the same session that also did the CI break-glass fix above:

- **#15 — font-size bump.** No design-token system existed (146 ad-hoc `font-size` declarations, 24 distinct `rem` values in `web/index.html`) — filed **issue #14** to fix that properly later. For the immediate ask, did a uniform proportional scale (~1.36x, computed to take the smallest existing text, 0.55rem/8.8px, up to a 12px floor) across all 146 sites, preserving relative hierarchy.
- **#16 — light/dark toggle + first contrast pass.** Added a manual theme toggle (sun/moon button in the header), persisted via `localStorage` + `data-theme` attribute (applied synchronously pre-paint to avoid flash), overriding the `prefers-color-scheme` media query in either direction. Also fixed dark-mode `--text-secondary` (`#777` on `#111` ≈ 4.2:1, below WCAG AA) → `#9e9e9e` (~7:1) — that var is used by ~98 of ~120 colored-text declarations in the file, so it was the dominant factor in "hard to read."
- **#17 — round 2, after Nico still couldn't see the toggle or find text clear enough.** Found two real bugs, not just insufficient contrast: (1) `.header-meta` (the "built `<time>`" / "synced `<time>`" indicator — Pacific time, to the minute, which **already existed** and is the thing Nico remembered from other tools) was unconditionally `display:none` below 600px viewport, i.e. invisible on every phone; (2) `header`/`.header-right` had no `flex-wrap`, so 6 buttons at the new larger font sizes could get squeezed/pushed off-screen on a narrow viewport instead of wrapping — the likely reason the toggle itself wasn't visible. Fixed both. Also pushed contrast further (dark secondary → `#d0d0d0` ≈ 12.2:1, light secondary → `#404040` ≈ 9.9:1) and added a light-blue accent (existing `--accent-light` token, confirmed WCAG-clear for large text in both themes) to "big" text specifically — KPI tile numbers, page H1s, the four big total callouts, project-detail page name — so prominence comes from color/hue rather than pure brightness.

**Verification:** this session's sandbox network policy blocks `esm.sh` (the CDN `web/index.html` loads Preact/HTM from at runtime), so none of the four PRs could be visually rendered/screenshotted in-session — all verified mechanically instead (contrast ratios computed against the WCAG relative-luminance formula, CSS var resolution confirmed via forced `localStorage` + `getComputedStyle`, no JS console/page errors). **Nico confirmed live on his phone 2026-07-10: "it all looks really good"** — a general confirmation, not itemized per-theme; light mode specifically was never separately called out as checked, just not flagged as a problem either. Live testing caught one real bug the mechanical checks couldn't: the project-page activity heatmap opened scrolled to its oldest (blank) end instead of today — `.heatmap`'s `overflow-x: auto` container defaults `scrollLeft` to 0 on load. Fixed same day as **#19**: a `useRef` + `useEffect` scrolls it to `scrollWidth` (the recent end) once the grid renders.

**Scope note:** Nico also asked for the build-time indicator "in all my projects really" — out of scope this session (GitHub access was scoped to `nicolovejoy/prompt-lab` only); would need repos added explicitly to pick up.

### CI break-glass: `/readup` now checks CI health (SHIPPED 2026-07-09)
Traced from a CDCI ask: the `tests` workflow (`.github/workflows/test.yml`) had been red on `main` for 3 days (since `5f5f531`, the Todos by-type feature) — 12 ruff lint errors (`E741` ambiguous var in `scripts/classify_issues.py`, `E701`/`E702` one-line if/else/semicolon statements in `scripts/test_web_api.py`) failed the `test` job, which cascaded into skipping every downstream test step **and** the `deploy` job (which `needs: test`) on every push. No prod deploys went out for 3 days and nothing surfaced it — `deploy` shows as *skipped*, not *failed*, so it reads as normal in a quick glance at Actions. Fixed the 12 lint errors (renamed the ambiguous var, split the one-liners). **Root-cause fix:** `/readup` (`workflow/commands/readup.md` step 8) now checks `gh run list` for the default branch (and current branch if different) on every session start — silent if green/no-CI, otherwise surfaces a ⚠️ leading the summary naming the workflow, how long it's been red, and whether a dependent job (like `deploy`) is being silently starved as a result. Never blocks session start (skips silently on any `gh` error). Not yet applied to the SessionStart hook (that would make it automatic/unconditional rather than a `/readup`-time check) — could move it there later if `/readup` alone doesn't catch breakage fast enough in practice.

### Cross-site visitor visibility — core SHIPPED, fan-out ON HOLD (issue #9, 2026-07-05)
Traced a 2026-06-14 ibuild4you ask ("visibility to who uses this app and all my cloudflare hosted domains") that never got filed — filed as **#9** public-site traffic + **#10** auth-gated tool usage (tied to the OAuth-migration item below).

**Decision reversed after verifying pricing: option A (Vercel Web Analytics + Drains) is dead, built option B (first-party beacon → Turso).** Verified 2026-07-05: Drains are Pro/Enterprise-only ($0.50/GB on top of $20/mo Pro), AND Hobby Web Analytics has no read API at all — 1-month retention, 50k-events/mo cap shared across ALL projects, viewable only in per-project Vercel dashboards. So option A couldn't feed a unified dashboard on Hobby regardless of export. Beacon (B) is also better long-term: hosting-neutral (covers all ~14 domains identically, not just the Vercel subset), writes cloud-direct to Turso so the cost-pipeline drift class can't recur, we own retention, and #10's login events ride the same endpoint.

**Core shipped + live-verified on prod (this session, Fable):**
- `web/api/beacon.py` — public `POST /api/beacon` collector. Anonymous by construction: no cookies, raw IP never stored, `visitor_hash` = truncated `sha256(AUTH_SECRET|UTC-date|ip|UA)` (rotates daily). Hardened: `site` from `Origin` header (never client-supplied), bot-UA + localhost-origin drop, 2 KB body cap, opaque 204 on every path. `event` allowlist currently `{pageview}` (add `login` for #10). Growth policy: `docs/measurement-policy.md` (measurement minimalism — one purposeful event at a time, never a stable identifier).
- `web/beacon.js` — one-line snippet (`<script defer src="https://prompt-labs.org/beacon.js">`), sendBeacon, skips `navigator.webdriver`.
- `page_views` Turso table (`scripts/create_page_views.py`, idempotent) — **cloud-direct, no local-SQLite copy, no sync leg** (deliberate). Classified in `docs/data-and-access.md` as the one exception to the sync flow.
- `web/api/visitor_overview.py` + `#/visitors` page (top-nav "Visitors") — auth-gated, mirrors `#/costs`: stacked daily chart, by-site / top-pages / referrers / countries. `site` is a hostname, no alias folding.
- 10 new tests in `scripts/test_web_api.py` (25/25 green). Live prod verified: beacon.js 200, clean hit → 204 → row landed in Turso with correct Origin-derived site + Vercel geo header, overview 401 without auth. prompt-labs.org now self-instrumented.

**Step 2 fan-out — 6 repos MERGED 2026-07-07** (Nico said go). One beacon PR per repo (Sonnet sub-agents, `<Script src="https://prompt-labs.org/beacon.js" strategy="afterInteractive"/>` beside the existing `<Analytics/>` in each Next root layout), all squash-merged to main → Vercel redeploys the beacon live:
- byside #88 (by-side.net) · ibuild4you #118 (ibuild4you.com) · recountly #13 (recountly.org) · invitekit #77 · selected-projects #6 (pianohouseproject.org; beacon is its only tracker, no Vercel Analytics; handoff note posted) · bakerylouise-v1 #27 (bakerylouise.com — the client-site question was resolved: Nico OK'd instrumenting it).

**Verify wave DONE 2026-07-07** (real-browser Playwright loads → Turso `page_views`). The cross-origin browser sendBeacon is now PROVEN end-to-end (previously only curl-tested). **Firing live (event landed, correct Origin-derived site):** prompt-labs.org, by-side.net, ibuild4you.com, pianohouseproject.org, bakerylouise.com, freevite.vercel.app — plus **recountly.org as of 2026-07-14** (see the resolved anomaly below).

**Actual `page_views` inventory, queried 2026-07-15** (the ground truth; beats any prose list here): bakerylouise.com 53 · prompt-labs.org 47 · ibuild4you.com 29 · by-side.net 15 · preview.ibuild4you.com 10 · pianohouseproject.org 6 · **free-vite.com 3** · offer-builder.ibuild4you.com 3 · freevite.vercel.app 2 · recountly.org 1. **`free-vite.com` is unexplained** — the note below says invitekit has no custom domain and fires only as `freevite.vercel.app`, but something served our beacon from `free-vite.com` on 2026-07-10/11. Probably invitekit gained a custom domain nobody recorded; confirm before trusting the "no real traffic" claim below.

**Anomaly 1 — recountly.org beacon: RESOLVED 2026-07-14.** Live and confirmed end-to-end (real headed browser → 204 → Turso row, `ts 2026-07-15T00:18:42Z`, `site=recountly.org`). The beacon code was never the problem — it was correctly placed at `src/app/layout.tsx:42` the whole time. **The recountly Vercel project simply had no Git integration, and never had one:** `GET /v9/projects/<id>` returned `link: NULL`, and the project had **zero preview deployments across its entire 43-day history**. Every deploy it ever had was a hand-run `vercel --prod`. Nothing broke on Jun 27; the workflow had moved to GitHub PRs, and on an unlinked project merging a PR deploys nothing — so the 17-day "gap" was just time since someone last ran the command by hand. Now linked: main auto-deploys and PRs get previews, both halves verified.

**Load-bearing detail:** that row is the **only** `recountly.org` row that has ever existed — the beacon had never fired once before this deploy. Anything upstream reading beacon data for recountly was reading **a hole, not a zero**. Don't interpret a missing site in `#/visitors` as "no traffic."

**Three diagnostics retired by this — they produce false conclusions, don't reuse them:**
1. **`gh api repos/:owner/:repo/hooks` is not evidence about Vercel linkage — it's no evidence at all.** Vercel connects via a **GitHub App**, which creates no repo-level webhooks, so this returns empty whether or not the project is linked (it still returns empty now that recountly IS connected and auto-deploying). Check `link` on `GET /v9/projects/<id>` instead.
2. **`_vercel/insights` is a stale marker for "is Vercel Analytics present."** `@vercel/analytics` 2.0.1 serves through a randomized anti-adblock path (recountly's is `/7bd029f5969d4043/script.js`, which contains `vercel/insights` internally and POSTs to `/<hash>/view`). Grepping served HTML for `_vercel/insights` reads as a false negative on any current site.
3. **`githubCommitSha`/`githubCommitRef` on a deployment do NOT imply a git trigger.** The CLI stamps local checkout metadata onto manual deploys, which is exactly what makes an unlinked project look linked. The real tell is `target`: **every deploy production, zero previews ever.** A *removed* webhook would leave previews behind from before it broke; *never linked* leaves none, ever. Distinguish those by checking the project's whole history, not just the recent window.
2. **freevite.app is NOT ours — do not instrument it.** It's almost certainly Matt Lewis's `mplewis/freevite` (same name/concept, a Vite SPA). `nicolovejoy/invitekit` is Nico's *own from-scratch* reimplementation (Next.js + Firebase, `isFork: false`, first commit 2026-04-11), deployed to `freevite.vercel.app` — that's where the beacon is live and firing (records site=`freevite.vercel.app`; no custom domain, so ~no real traffic — the beacon there is harmless but low-value). Earlier note mistakenly implied putting the beacon on freevite.app; that would be instrumenting someone else's site — DON'T. invitekit's beacon is done and correct; nothing more to do unless invitekit gets a real custom domain.

**Still held:** **prntd** + **musicforge** had dirty trees at fan-out time (do when clean; musicforge is Vite `frontend/src/main.tsx`, different injection). **Local cleanup:** sub-agents left byside/recountly/invitekit/selected-projects on the deleted `add-visitor-beacon` branch — `git checkout main && git pull` in each before local work. Cloudflare-proxied musicforge.app + recordings.pianohouseproject.org and unclear domains (eaglerockventures, robotorchestra, ruhuman) still covered identically once instrumented.

**Two trackers now live across the ecosystem — inventory (verified 2026-07-05):**
- **Our beacon** (`beacon.js` → `/api/beacon` → Turso `page_views` → `#/visitors`): **prompt-lab ONLY** (relative `/beacon.js` in `web/index.html`). No other repo has it — the fan-out is still on hold. So `#/visitors` shows only prompt-labs.org; early "N views" there = Nico's own dashboard loads.
- **Vercel Web Analytics** (feeds Vercel's per-project Analytics tab, NOT our `#/visitors`): a parallel Opus session added it to **7 repos** — prompt-lab (`ad557d5`, the `_vercel/insights` script tag; the rest use the `@vercel/analytics` React pkg), plus byside, prntd, ibuild4you, recountly, bakerylouise-v1, invitekit (all 2026-07-05 ~20:53–20:58), and musicforge (since 2026-06-22). View per-project at vercel.com → project → Analytics.

**Implication:** the ecosystem is now Vercel-instrumented (per-project, fragmented — the exact thing #9 wanted to unify) but on the Hobby data source we concluded can't feed a unified dashboard (no read API, 30-day retention, 50k/mo cap **shared across all 7**). The single cross-site view still only comes from the **beacon fan-out** (on hold). When unblocked, beacon is one line per repo — same layout file the `@vercel/analytics` component went into. **Decisions pending:** (1) keep both trackers or drop one once the beacon covers a site (double-tracking + muddies the first-party story); (2) watch the shared 50k/mo Vercel cap now that 7 projects report into it.

### Home redesign → Pulse + Todos by-type (SHIPPED 2026-07-05)
Pitched 3 home concepts (Command Center / Briefing / Pulse) via 3 parallel design agents → Artifact. Nico picked **Pulse** (metrics-first). Built: KPI tile row (active projects, 7d sessions/prompts/commits, 30d spend, 30d views — spend/views tiles link out) + a 30-day cross-project stacked activity chart (from `activity_by_project`), over the retained daily-summary stream ("Recent activity"). Pure frontend — reuses `/api/overview` + `cost_overview` + `visitor_overview`. Also added the **Todos by-type view** (see the Todos entry below). Both live, bundle verified clean (0 console errors). Considered-and-rejected: a triage band (built + removed same day — see redesign note below).

### Playwright orphan-browser reaper (SHIPPED 2026-07-05, issue #8)
Stray "Chrome for Testing" instances (diagnosed in a musicforge session) get reaped by `workflow/bin/reap-playwright.sh`: kills any `ms-playwright` process whose PPID is 1 (orphans reparented to launchd) — the PPID-1 guard is what makes it safe; a bare `pkill -f ms-playwright` would kill live sessions' browsers. Runs as an **async global SessionStart hook** (`~/.claude/bin/reap-playwright.sh`, timeout 10); no launchd interval job for now — add one only if strays accumulate during non-Claude stretches. install.sh's bin loop distributes it and its printed settings stanza includes the hook line; BULLETIN.md 2026-07-05 entry carries the behavioral half (`browser_close` when done with `mcp__playwright__*`, don't SIGKILL `playwright test`). Verified with a fake orphan (PPID 1 → reaped) and a live-parent process (survived). Mini wired. **Laptop:** SessionStart hook entry added to its `~/.claude/settings.json` 2026-07-05 (reap-playwright.sh already installed in `~/.claude/bin/`); takes effect next launch. Remaining laptop follow-up: `git pull && ./workflow/install.sh` to keep the distributed copy current.

### `work` iTerm2 launcher — now repo-synced (SHIPPED 2026-07-05)
Ported the per-project launcher from mini's unversioned `~/src/utils/work.zsh` into the repo's shared shell channel: `workflow/shell/work.zsh`, distributed by `install.sh` (copy → `~/.claude/shell/work.zsh` + idempotent `source` line in `~/.zshrc`, mirroring the `gc-shell.zsh` block). `work [name]` opens an iTerm2 window (menu / arg / `<TAB>` completion over `~/src`) with a top Claude pane + two bottom shells, all cd'd into the project; tab color is a deterministic name→HSV hash (no palette to sync). Two deltas from mini's copy: **80/20 split** (`bottom_rows = WORK_ROWS/5`; knob is the `/5`) and **bigger window** (`WORK_COLS/ROWS` 160×50 → 200×55, iTerm clamps to screen). Verified working on laptop (`907d6eb`, pushed). **2026-07-18 additions (`54dcf1e`, laptop-verified):** the top pane now gets an iTerm **badge** (project-name watermark via `iterm_badge`; programs in the pane can't overwrite it) and launches **`claude --name '<project>'`** so the tab/window title reads `· <project>` from launch. Key finding behind it: the terminal title IS Claude Code's session name — generic "Claude Code" just means the session is un-named yet (auto-topic or `/rename` fills it); nothing in `/readup` or the SessionStart hook renames sessions, and the mini's `— ~/src/<proj>` tab suffix is machine-local iTerm config (Shell Integration + "Path" title component), not the repo. The `gc-shell.zsh` precmd only titles plain zsh panes. **Known nit:** `_work_color` collides prompt-lab & byside → same blue (inherent to mini's hash; unchanged). **Mini follow-up:** `git pull && ./workflow/install.sh` to pick up work.zsh (same step also still owed for issue #7's `~/.claude/bin/handoff.sh` allow rule + wrapper install per the note below).

### Cross-repo handoff → standalone synced git repo (SHIPPED 2026-06-29)
Issue #7 done. Cross-repo coordination moved from unversioned, machine-local `~/src/.handoff/*.md` into the **standalone private repo `nicolovejoy/handoff`** (cloned to `~/src/.handoff`, synced across mini+laptop). Writes go through `workflow/bin/handoff.sh` (`append`→top of `## Active` / `sync` / `pull`; mkdir mutex w/ stale recovery, portable TERM→KILL timeout, exit 0/3/4/5) → installed to `~/.claude/bin/`. SessionStart hook does a 3s best-effort pull then injects the manifest-matched (`repos:` front-matter) channel's `## Active` section. `/handoff` step 6 (post + sync) and `/readup` step 7 (flush unpushed/offline) wired; allow rule `Bash(~/.claude/bin/handoff.sh *)` in install.sh + both machines' settings.json. Pointer stanzas in prompt-lab + selected-projects + prntd CLAUDE.md. Harness (`workflow/handoff-sim/`) re-pointed at the shipped wrapper: 26/26. **Known property:** same-file concurrent appends conflict under rebase — wrapper surfaces (rc=3) + preserves, never drops; mitigation is one-file-per-entry if it ever hurts. Design: `docs/handoff-repo-plan.md`.

### Costs overview page + cost-sync drift fix (SHIPPED 2026-06-25)
Issue #6 done. **Costs page** at `#/costs` (top-nav "Costs" link): new `web/api/cost_overview.py` (alias-folded, all projects, no `project` filter), stacked-by-project daily chart with a **zero-filled calendar axis** (30/90/365d windows), sortable per-project legend, per-model breakdown, API-spend-only caveat note. **Root-cause fix (the important part):** the dashboard was showing stale/partial cost data because the nightly `com.promptlab.api-costs` LaunchAgent ran `pull_api_costs.py` (writes **local SQLite only**) but nothing synced to Turso, which the dashboard reads — local was ~a month ahead. Coupled pull+sync in new `workflow/run-cost-pull.sh` (`pull` then `sync_to_turso.py --days 7`); plist points at it (reloaded on mini, the nightly machine). Backfilled Turso via a one-off full sync — orphan `__unmapped__` rows overwrote in place via the `UNIQUE(date,workspace_id,description)` key (project not in the key). Documented in `docs/cost-tracking.md`. **Watch:** new Anthropic workspaces (e.g. koma-launch) land in `__unmapped__` until added to `scripts/seed_project_workspaces.py`.

### Todos page — cross-project open GitHub issues (SHIPPED 2026-06-25)
Top-nav "Todos" link → `#/todos`. `web/api/todos.py` does one authenticated GitHub Search call (`is:open is:issue user:<GITHUB_USER>`, default nicolovejoy) for every open issue across **owned** repos, groups by repo (folded through the project alias map), renders per-repo. **Live-read — no table, no sync, always fresh.**

**By-type view (added 2026-07-05):** a `by project | by type` toggle. "By type" classifies every issue into a fixed work-type taxonomy (`bug / feature / infra / ux / content / research`, else `other`) via **one batched Claude call**, cached in the Turso `issue_categories` table keyed `(repo, number)` — a given issue is classified once and reused until its title changes, so steady-state cost ≈ $0 (only genuinely new issues ever hit the LLM). The endpoint serves `/api/todos?categorize=1`: reads the cache, and (admin only, `ANTHROPIC_API_KEY` present) classifies any stragglers, capped at `LIVE_CLASSIFY_CAP=40`/request with a `pending` count the frontend polls down. Taxonomy lives in `web/classify_helper.py` (`classify_batch`, mirrored in `index.html`'s `CAT_META`). **Pre-warm / periodic refresh:** `scripts/classify_issues.py` (uses `gh` CLI, no token handling; `--all` forces reclassify) — run once after deploy to fill the cache so live requests never do a big first batch; it also creates the `issue_categories` table. Readers see cached categories only (no spend). `↻ reclassify` button forces a full re-run (admin). Why LLM not labels: only 54% of issues carry labels and they mix type/platform/priority — too inconsistent to group by (checked 2026-07-05). Prominent total + project count; each repo is a **collapsed-by-default accordion** with Expand/Collapse-all. **Scope defaults to dashboard-tracked projects** (computed from `overview.all_projects` ∪ `by_project`; the endpoint folds repo→canonical so they match) with a **`Show all repos (+N)`** toggle that reveals untracked owned repos (tagged with an `untracked` chip). **Search box** filters issues by title / label / `#number` / repo across the shown scope and force-expands matching repos. Needs `GITHUB_TOKEN` (read-only fine-grained PAT, Issues+Metadata) in Vercel env (Prod+Preview) + `.env.tpl` (`op://dev-secrets/prompt-lab-github-pat`); optional `GITHUB_USER`. **Caveats:** only repos you own (org/other-owned repos' issues won't appear); the PAT expiry silently 401s the page when it lapses — regenerate longer-lived if it breaks.

### Dashboard redesign Phase 1 + perf (SHIPPED 2026-06-24)
Per `docs/dashboard-redesign-plan.md`. **Home → cross-project activity stream** (recency-sorted feed of daily summaries, expandable; replaced the project-card grid; dormant projects now a chip list behind the toggle). **Project pages → Now / Trajectory / Cost / History** sections. **Machine-voice markers** (`↳ from claude`, italic+muted) on state summaries, daily-summary bodies, rollup narratives. **Top-nav project picker** (Vercel-style, Active/Dormant sections). **Cost states**: loading + explicit no-spend empty state (notes that Claude Code subscription work isn't attributed per project). Deleted 4 dead endpoints (`intentions/projects/rollups/summaries.py`). **Perf** (separate commit): localStorage stale-while-revalidate for `/api/overview` (instant paint + ↻ refresh spinner), in-session memo for project/cost (instant back-nav), prefetch of the top project — all pure-frontend, no backend change. **Next:** costs-overview page is issue #6 (API-spend-only by necessity). (Phase 2 "triage band" — the admin-only "went quiet" / "cost spike" attention band — was built then **removed 2026-07-05**: with work split across two machines, "went quiet" fired for ~every project since it only saw one DB's prompts, so it was noise dressed as signal. Don't rebuild it without a cross-machine activity source. Removed cleanly in `web/index.html`; recover from git if wanted.)

### Intentions fully removed (REMOVED 2026-06-24; deprecated 2026-06-23)
First froze *generation* (2026-06-23); then removed the feature entirely (2026-06-24) after Nico manually purged the rows — the data was noise (bloated past its 3-8/project target: musicforge 180 "active", ibuild4you 97) and nothing rendered it after the dashboard redesign. **Gone now, not reversible:** the `intentions` table (dropped on both local SQLite and Turso), all store methods (`get_intentions`/`upsert_intention`/`get_projects_needing_intentions_refresh` + the `_dedupe_intentions` helper), `web/api/intentions.py`, the `synthesizer.py --intentions` flag + `synthesize_intentions()`, the intentions sync in `sync_to_turso.py`, the `/roadmap` + `gc-read.sh` intentions subcommands, the mobile PWA's IntentionsTab, and the orphaned `themes.intention_ids` column. Tests updated (test_web_api dropped the intentions/rollups/summaries endpoint sections; test_alias_layer dropped the `_dedupe_intentions` tests); all green. If goal-tracking ever returns, build it fresh — the old completion/abandon logic never fired.

### prompt-labs.org de-indexed from search (SHIPPED 2026-06-22)
Policy A (DE-INDEX) for the auth-gated dashboard: added `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` on `/(.*)` in `web/vercel.json` + `<meta name="robots">` in `web/index.html`; `robots.txt` already `Disallow: /`. Verified live (header + robots.txt + served meta). Not Next.js so no `app/robots.ts` layer. Doesn't touch `/api/public_history` (server-to-server, not browsed).

### Public-data drift guard — now wired in (SHIPPED standalone 2026-06-13; wiring SHIPPED 2026-07-12; purge still pending)
`scripts/check_public_allowlist.py` audits both stores' public_* tables against `docs/public-allowlist.txt` (mirror of the consumer's 7-key historyKey manifest), alias-aware, report-only (`--fix` prints unpublish commands, never runs them). Built after an earlier session reconciled the public tables to the manifest (removed `/handoff` writes, purged byside + 12 strays — see RESOLVED note below).

**Wiring shipped 2026-07-12:** (1) `sync_to_turso.py` now runs the audit as a non-fatal post-sync step (`check_public_allowlist_drift()`) — subprocesses the script, prints its output, never affects the sync's own exit code even on drift. (2) `/readup` step 9 (prompt-lab-repo only) runs the same script and, on drift, leads the session summary with a ⚠️ block naming the offending project(s) and the `unpublish_public.py <project> --apply` fix — standalone alone relies on remembering, which already failed once. Fixed a real bug found while wiring this in: the script crashed with an unhandled `sqlite3.OperationalError` on an unmigrated local DB (missing `local.migrate()` before querying) — would have made the "non-fatal" guarantee false in exactly the situation (a stale local DB) where the check matters most. Verified end-to-end in-session: clean run, a manually-inserted drift row correctly caught and reported, cleanup confirmed clean again.

**4 Turso-only strays purged 2026-07-13** (`audio-journal`, `bakerylouise_v1`, `invitekit`, `recountly` — 8 rows total in `public_session_summaries`, none local, none in weekly_rollups). `scripts/check_public_allowlist.py` now reports clean: 7 distinct projects in public tables, matching the 7-key allowlist exactly. When the manifest changes, update `docs/public-allowlist.txt` + its date.

### Shared-conventions sync across all repos (SHIPPED 2026-06-13)
`workflow/claude-md-shared.md` is the single source of truth for Nico's cross-repo output rules (clickable URLs, numbered questions, self-contained smoke-test instructions, no marker before copy-paste command blocks). `workflow/bin/sync-claude-md.sh` materializes it into a target `CLAUDE.md` between `<!-- SHARED-CONVENTIONS:BEGIN/END -->` markers — `--apply` splices only inside the markers (bespoke content untouched; creates CLAUDE.md if absent), `--check` reports `in sync`/`missing`/`drift`/`absent` via a content-hash stamp in the BEGIN marker. **Design decision: compile-to-committed-text, NOT CLAUDE.md `@import`** — verified (via claude-code-guide) that `@import` is a Claude Code *harness* feature only; cloud/headless/third-party readers see the literal `@path`, and `~/`-anchored imports break in cloud. Committed plain text is the only thing that reaches every environment. `install.sh` distributes the source to `~/.claude/claude-md-shared.md` + the script to `~/.claude/bin/`; `/readup` step 6 runs `--check` and warns on drift but **never auto-writes** (materializing into a checked-in file stays the user's explicit call). Rolled out to 30 repos (the 5 without a CLAUDE.md skipped); both machines updated. **Edit→propagate loop:** edit `claude-md-shared.md` → `./workflow/install.sh` → re-run `--apply` per repo. Caveats: (1) only binds in envs that read each repo's committed CLAUDE.md, so a repo never re-synced stays stale; (2) notemaxxing's lint-staged may have reformatted its block at commit → could show cosmetic `drift`; (3) 6 repos committed onto feature branches (block reaches their main on merge); (4) of the 30, only prompt-lab is pushed — rest are local commits awaiting per-repo push.

### Public-data surface simplified (SHIPPED 2026-06-03)
Removed the `PUBLIC_PROJECTS` read-time allowlist from `web/api/public_history.py` (PR #4, deployed). It was a third, drifting copy of "what's public" alongside the public_* table rows and the consumer's manifest. New model: the endpoint serves whatever exists in `public_session_summaries` / `public_weekly_rollups`, which are **safe-by-construction** (written only by `scripts/backfill_public_*.py` with scrubbed text). The single source of truth for *which* projects are public is now the **selected-projects MDX manifest** (`content/projects/*.mdx`). Added `scripts/unpublish_public.py <project> [--apply]` — alias-aware, dry-run-by-default tool that deletes a project's public rows from **both** local SQLite and Turso (sync only upserts, so deletes must hit Turso directly; byside had 4 local but 17 Turso rows). Unpublished byside end-to-end. Also fixed selected-projects' dead `anomatom.com` → `prompt-labs.org` API fallback in `lib/history.ts` (merged to its main). Consequence: every project with scrubbed rows is now URL-reachable (incl. client projects — all verified de-identified); use `unpublish_public.py` to pull any one. Note: `docs/selected-projects-api-migration.md` now describes the allowlist as the intended single gate — superseded/stale.

### Vibe-coding lessons doc + public page (SHIPPED 2026-06-06)
`docs/vibe-coding-lessons.md` — a 14-lesson field guide on working with Claude, extracted from real `key_decisions`/prompt history. Public GitHub links only on actually-public repos (verified prntd/ibuild4you/prompt-lab PUBLIC; byside/musicforge private → prose-only, unlinked). **Issue #3 CLOSED:** shipped as a public page at PianoHouseProject.org `/vibe-coding-lessons` (selected-projects repo, not prompt-labs.org). Lives there as `content/vibe-coding-lessons.mdx` + `app/vibe-coding-lessons/page.tsx`, top-nav "lessons". Key correction: the page first **overclaimed Nico's authorship** (machine-written prose in human-voice type, backwards from tenet #1) — rewrote with an honest machine-voice `<MachineNote>` (Claude wrote the lessons by mining Nico's real prompts; [real] prompts are his words) and cut it 60%. Added a Nico-voiced caveat to tenet #1 that clean who's-speaking separation may be unachievable. **Open follow-up: selected-projects #4** — gate the page behind auth with a teaser (deferred, needs the magic-link auth work on main). Note: shipped via isolated PRs off main (#2 create, #3 rewrite) after a two-agent collision where a concurrent selected-projects session committed a duplicate onto its local feature branch — logged in `~/src/.handoff/selected-projects-prompt-lab.md`.

### /handoff public-write steps removed — invariant now clean (RESOLVED 2026-06-13)
Chose option (a): deleted the "public session summary" + "public weekly rollup" steps from `/handoff` (`workflow/commands/handoff.md`). `public_session_summaries` / `public_weekly_rollups` are now written ONLY by the hand-reviewed, git-committed `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or sync (`sync_to_turso.py` only *propagates* existing local rows to Turso). Key finding that settled it: the "safe-by-construction" property is **not** "human-authored" (the backfill text is Claude-authored too — see `backfill_public_promptlab.py` docstring); it's "**reviewed, git-committed literal, published by a deliberate per-project one-shot**." `/handoff`'s live DB writes had neither the review gate nor the per-project opt-in, fired for every repo incl. client work, and auto-propagated to public Turso on next sync. They were also effectively dead (blocked every run by the auto-approver), and the backfill scripts are hardcoded one-shots (not incremental), so public data was never auto-fresh anyway — removing the steps lost nothing that worked. If fresh public data is wanted later, the right path is the draft-to-artifact hybrid (have `/handoff` draft scrubbed text into a reviewable backfill artifact rather than the DB), not live writes.

### Domain migration → prompt-labs.org (SHIPPED 2026-05-29)
Cloud dashboard now lives at **https://prompt-labs.org** (Cloudflare registrar, Vercel-hosted). Replaced anomatom.com, which was dropped from the project (404, no redirect). Vercel project renamed `ground-control` → `prompt-lab` (project ID unchanged: `prj_g6Bd1VG93LUDdKwg5V4d1EaoE4FV`, so GitHub Actions secret needed no change). DB `projects.site_url` updated + synced to Turso. Verified live: 200 + auth-gated API (401). The app is domain-portable (no hardcoded domain in `web/` runtime, host-relative cookies), so any future move is a Vercel-dashboard task, not a code change. Note: prompt-labs**.com** is a $2k squatter — not ours; we own the **.org**.

### Local dashboard retired (SHIPPED 2026-05-29)
The Flask `dashboard/` (port 5111) was removed — ~3mo stale, none of the cost/alias/public_history work landed there. Cloud `web/` is the single UI. Fallout fixed same session: `python-dotenv` lived only in the deleted `dashboard/requirements.txt`, breaking CI; restored via a new root `requirements.txt` (CI + install.sh point at it). `mobile/` PWA left untouched.

### Status toggle (scoped 2026-05-28 — SHIPPED 2026-07-14 as part of #23)
Done: the cloud project page has a status `<select>` writing to Turso `project_metadata` via the admin-gated `POST /api/project_metadata`. See the #23 entry above. The old plan's step (2) ("move status ownership to Turso so `sync_to_turso.py` stops clobbering a cloud-set value") was based on a bug that never existed — sync never wrote `projects`. Local `projects.status` and cloud `project_metadata.status` are now independent by design: local serves the local pipeline, cloud serves the dashboard, neither syncs to the other.

### Todos rewire (opened 2026-05-28)
`todos.py` scanner is now unwired — its only consumer was the retired local dashboard, and `web/` has no todo handling. Rewire into the cloud app when todos return to the UI.

### offer-builder → byside rename (SHIPPED 2026-05-30)
prompt-lab side of byside's GH #13 done end-to-end. Added alias `offer-builder → byside` (`scripts/alias.py`), synced to Turso, set `projects.github_url` → `nicolovejoy/byside`, and regenerated the project snapshot so the dashboard GitHub link is correct. Key finding: `web/` **never reads the `projects` table** — the home list comes from `/api/overview`, which is already alias-aware (`_resolve()`), so the dashboard groups under canonical `byside` with no code change. (`web/api/projects.py` was dead UI code; it has since been deleted — don't go looking for it.) The rename stays non-destructive: rows keep logging as `offer-builder` (dir unchanged), folded at read time. Byside's `/changelog` was still pointing at dead `anomatom.com` — flagged to that agent (now resolved on their side).

### Auth and sharing
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me
- **selected-projects → `/api/public_history` migration: complete, manual cleanup done 2026-06-05** (prompt-lab `73c7de9` + `c53c04c`, selected-projects `c895eb6`). All three owed cleanups landed this session: (1) visual-verified PianoHouseProject.org `/projects/musicforge` Evolution section via Playwright — live, current data, machine-voice marker present; (2) deleted `HISTORY_TURSO_DATABASE_URL` + `HISTORY_TURSO_AUTH_TOKEN` from selected-projects Vercel (Preview + Production), kept plain `TURSO_*` (pianohouse's own DB) — this removed the actual exposed copy of the ground-control token; (3) **rotated** the ground-control Turso token on web's Vercel (Production/Preview/Development) and verified the new token connects (`SELECT 1` → 200). `docs/selected-projects-api-migration.md` is historical.
  - **Old token invalidated — issue #5 CLOSED 2026-06-06.** Chose the *isolate* path over a group-wide rotation: created a new Turso group `promptlab` and migrated the DB into it (dump via `turso db shell ground-control ".dump"` → `turso db create promptlab --group promptlab --from-dump`; note `--from-dump` silently no-ops, had to `turso db shell promptlab < dump.sql` to actually load). Verified all 13 tables row-for-row, repointed web's Vercel env (`TURSO_DATABASE_URL` → `libsql://promptlab-nicolovejoy.aws-us-west-2.turso.io`, `TURSO_AUTH_TOKEN` → new) + both machines' repo `.env.local` (op item **`Turso`** url+token fields updated; the separate `prompt-lab-turso-token` op item is redundant), then **destroyed `ground-control`** — which neutralizes the old per-DB token (its target DB is gone). `pianohouse` + `prntd` stay in `default`, untouched. The new `promptlab` group has its own signing key, so prompt-lab data is now cryptographically isolated from any future `default`-group token. **Gotchas found:** (1) a stale repo `.env` on the laptop loaded *before* `.env.local` (load_env is first-wins) and pinned the old URL — `rm .env` fixed it; (2) `~/.claude/synthesizer.env` is the **legacy** creds source and is effectively dead — `load_env` (claude_api.py:18) reads `REPO_DIR/.env.local` first by *absolute* path so it always wins even under launchd; mini is the only machine that runs the nightly LaunchAgents (`com.promptlab.{synthesizer,review,report}`). Follow-up DONE 2026-06-06: key-diff confirmed `.env.local` is a strict superset of `synthesizer.env` (all 7 keys present, plus `ANTHROPIC_ADMIN_KEY`), so `synthesizer.env` was dropped from `load_env`'s list (claude_api.py) + purged from README/error-messages/cost-tracking docs. The hook still *blocks* `synthesizer.env` (defense-in-depth) and `.gitignore` still lists it. Laptop's copy deleted; mini's pending a manual `rm ~/.claude/synthesizer.env`.

### Responsible AI use paradigm (started 2026-05-17)
- "Machine voice" visual convention shipped on PianoHouseProject.org (`73cea5b` + `7475d88`): italic + muted + `↳ from claude` mono uppercase marker for any AI-authored text, including the Evolution rollups on each project page and a `<MachineNote>` MDX component for one-off blocks. First `/tenets` page in the nav documents the principle.
- Open: grow the `/tenets` list past tenet #1; consider applying the same convention to the cloud dashboard (prompt-labs.org) state summaries / weekly rollup text.

### Dashboard polish
- Review project detail layout on mobile (sidebar stacking) — note: sidebar dropped 2026-05-19 in favor of single-column; mobile audit still useful.
- Add ability to set/toggle project status (active/dormant) from detail page
- Project page UX cleanup (2026-05-19): collapsed text to teasers, dropped duplicate sidebar, capped timeline at 8 with Show More, added axes to CostChart, replaced "Site" link with hostname + self-link suppression. Cost drill-down (2026-05-20): `#/project/<name>/cost` opens a sortable detail table with filters; CostChart got a per-bar hover tooltip showing date + per-model breakdown. Next: figure out a coherent overall hierarchy — currently a header + heatmap + cost + timeline + intentions stack, no clear "above the fold" frame.

### Slash commands (current state, 2026-05-24)

Now installed: `/pulse` (session status), `/roadmap` (project digest), `/bulletin` (cross-project conventions), `/resync` (verify CLAUDE.md + open issues against actual code via parallel Explore agents, two modes: deep + `--light`). All read through `~/.claude/bin/gc-read.sh` wrappers so they bypass the simple_expansion permission gate.

The SessionStart hook (`workflow/hooks/session-start.sh`) auto-injects date + last-session summary + recent commits + bulletin headlines on every Claude launch under `~/src/*`. As of 2026-05-24 it also emits a **weekly nudge** listing custom commands not invoked in 30+ days (rate-limited via `~/.claude/state/commands-nudge.touch`). /readup now only does the things the hook deliberately skips: register session row, `git fetch --quiet && git status -sb`, full CLAUDE.md read, lazy unsummarized-day backfill, and auto-`/resync --light` when the per-project marker is >48h old AND >3 commits have landed.

Known nuance: prompt-history's slash-command counts under-report bare invocations because `log-prompt.sh` skips prompts starting with `<command-`. Rows that DO match (e.g., `/handoff` in "commit, push, /handoff") are conversational references, not invocations. Doesn't affect the nudge (which uses whitelist + 30-day cutoff) but limits any "trending command" analysis.

**Still to do:**
- Track session duration (ended_at − started_at) and surface in /review.

### /handoff trimming (in-progress design discussion, 2026-05-13)

Discussed five potential cuts. Decisions so far:
- **Point 1 — SHIPPED** (commit `342ceae`): dropped Turso sync from /handoff; moved to async SessionStart hook at `~/.claude/bin/turso-sync-maybe.sh` (per-machine, max once per 8h, was 24h). Synchronous hook warns when stale >24h (3 missed cycles). Cuts ~10s + a failure mode from every /handoff.
- **Point 2 — RESOLVED**: synthesizer schema-drift crash fixed in `242d343` (2026-05-13); schema verified healthy on both machines. The original idea — drop weekly rollup from /handoff once the nightly is proven stable — is now an optional cleanup, not a blocker.
- **Point 3 — SHIPPED** (this session): /handoff no longer upserts the GitHub URL. Moved to one-time `scripts/backfill_project_urls.py`; already populated all 15 projects under ~/src.
- **Point 4 — pending discussion**: batch the ~5 remaining `python3 -c "..."` invocations in /handoff into a single helper script. Worth doing only AFTER Point 2 lands.
- **Point 5 — pending discussion**: a Stop hook that captures commits + sets `ended_at` on session rows even when /handoff is skipped. Worth it only if you actually have many abandoned sessions.

### Cross-machine sync

SHIPPED (this session): bin scripts moved into the repo under `workflow/bin/` and `workflow/install.sh` extended to install them to `~/.claude/bin/`. The manual-step block at the end of install.sh now prints the full settings.json additions (allow rules + SessionStart hook entries).

Status by machine:
- **Laptop**: 8h Turso sync cadence; `~/.claude/settings.json` has gc-write/gc-read allows + SessionStart hooks. Operating from the new state.
- **Mini**: synced 2026-05-15 — pulled, install.sh ran, settings.json patched with allows + SessionStart hooks. Restart needed before hooks take effect.

**Synced shell config (2026-05-31):** `workflow/shell/gc-shell.zsh` holds machine-agnostic zsh bits (currently an iTerm2 precmd hook that puts the cwd in the tab/window title, updating on every `cd`). `install.sh` copies it to `~/.claude/shell/` and idempotently appends a `source` line to `~/.zshrc` — chosen over syncing the whole `.zshrc` so machine-specific config (nvm, paths) isn't clobbered. **Mini follow-up:** `git pull` + run `install.sh` to pick it up (the mini already has a near-identical inline precmd; the sourced one will override it harmlessly).

### Synthesizer cost reduction (shipped 2026-05-17)

Three-phase migration shipped this session in response to ~$100/2-week Opus spend on the nightly LaunchAgent:

- **Phase 1** (`598401c`): `OPUS` → `SONNET` across all unattended API call sites (`synthesizer.py`, `send-review.py`, `generate-report.py`). ~5x reduction.
- **Phase 2** (`8bea382`): `/handoff` step §3.5 refreshes intentions inline (`model='claude-code'`, free under subscription). Nightly `synthesize_intentions` now uses `get_projects_needing_intentions_refresh(today)` as a safety net (active project + no intention touched yesterday/today).
- **Phase 3** (`9ab9c25`): `/readup` step §4 backfills up to 5 recent unsummarized days inline. If >5 stale, skips with a note and lets the nightly catch them.
- **Bug-prevention** (`48802e6`): `scripts/test_imports.py` Phase 3 instantiates concrete stores so abstract-method drift breaks the test instead of silently breaking `/handoff`; `handoff.md` got a top-of-file guard telling Claude to stop on Python tracebacks.

### Backfill and maintenance
- Verify nightly synthesizer actually runs on both machines (pre-req for point 2 of /handoff trimming). On the laptop in particular — LaunchAgents pause when the lid is closed.
- Migrate other projects' `.env` files to 1Password `.env.tpl` pattern.
- The schema-drift fixes shipped in `242d343` (`projects` table + `token_count`/`hostname` ALTER) are tested only via `scripts/test_imports.py` (compile check) + `scripts/test_alias_layer.py` (in-memory store). No dedicated regression test that exercises the drift scenario specifically — Task #9 from this session, deferred.

### CI/CD follow-ups
- Stale-alias URL UX: `/project/frontend` now renders musicforge data but the URL/title still say "frontend". Consider redirecting `/project/<alias>` → `/project/<canonical>` at the SPA route layer.
- Decide whether to keep the GitHub Actions deploy path forever or eventually switch to Vercel's native git integration (simpler but loses test-gates-deploy semantics). Native is fine if you trust your tests; current setup is more conservative.

### Browser automation
- Playwright MCP installed at user scope (`claude mcp add playwright -s user`). Available after next Claude restart. Scope convention is in `BULLETIN.md` — production read-only, localhost + preview URLs full access.

### Cost tracking (issue #2 — CLOSED 2026-05-24)

End-to-end live since 2026-05-19; hardened + drill-down 2026-05-20; all 5 workspace mappings seeded 2026-05-24. Architecture, operational checklist, and gotchas in `docs/cost-tracking.md`.

Open follow-ups:
- **Watch ibuild4you spend** — ~$9-10/day for the last week (2026-05-14 to 2026-05-23, ~$113 total). Verify it's intentional usage on `#/project/ibuild4you/cost`; at this pace it'd be ~$300/mo.
- Claude Code Analytics returns 0 actors for the org (external — waiting on Anthropic to flow subscription auth through to org level; no code change needed)
- Manual PRICING refresh cadence in `claude_api.py` (no automation yet)
- Anomaly detection (originally a follow-up in #2) — not implemented. Open a new issue if/when needed.
