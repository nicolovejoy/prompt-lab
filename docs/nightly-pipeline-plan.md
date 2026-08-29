# Nightly pipeline: one ordered run, not four racing agents

Status: planned 2026-08-20. **Step 1 DONE 2026-08-29** — remote
`save_review_snapshot` is an upsert, `migrate()` dedupes then adds a unique
index on `(review_type, date)`, applied live (11,848 rows → 78, verified
stable across two consecutive syncs). `project_snapshots` was checked for the
same shape and is clean (live UNIQUE constraint, 0 duplicate pairs — its
1,880 rows are real history). **Step 2 DONE 2026-08-29** — `nightly_pipeline.py`
is the single entry point (cost pull → synthesizer → review → report-when-due →
publish, per-stage monotonic timeouts, failed stage skips dependents, publish
unconditional); `com.promptlab.nightly` (2:30) replaced the four agents, whose
plists are parked in `~/Library/LaunchAgents/disabled-promptlab-step2-20260829/`.
The report became artifact-keyed (runs when the current 1st/16th half-month has
no `monthly_report` snapshot), which is a slice of step 4's catch-up property.
Step 2's sleeping-host acceptance test pends the first overnight run. **Step 3
designed 2026-08-29** (below, decided with Nico); steps 3–5 not built.
Supersedes the tactical "write the review snapshot straight to Turso" idea,
which patched a symptom.

## Why

Recurring work produces artifacts in the **local** store. Turso is what every
reader actually reads — the dashboard, the `#45` freshness monitor, the
bi-monthly report. Something has to move local to remote, and nothing currently
guarantees that move happens *after* the work.

Today the only sync leg lives inside `workflow/run-cost-pull.sh`. The review and
the report have no publish of their own; they free-ride on `com.promptlab.api-costs`
happening to run after them. That is a coincidence, not a guarantee.

Two constraints make schedule-based ordering unfixable rather than merely
fragile:

- **launchd coalesces missed intervals onto one wake.** Two agents scheduled 45
  minutes apart start *simultaneously* after a closed-lid night. Retiming
  `api-costs` to 3:15 would look like a fix and would not be one.
- **The host is off for days at a time.** Catch-up is a normal path, not an
  exception.

Measured consequences as of 2026-08-20: Turso's newest `review_snapshots` row is
one day behind, permanently (inside the 2-day threshold, so nothing alarms); and
`review_snapshots` holds **10,938 rows in Turso against 69 locally**, because
`TursoKnowledgeStore.save_review_snapshot` (`store/turso_store.py:549`) is a
plain `INSERT` and the nightly sync re-pushes the newest ~68 rows every night.

## The design

**There is one nightly unit of work, not four.** Synthesize -> produce artifacts
-> publish is a pipeline with a real data dependency: the review reads summaries
the synthesizer wrote, and the publish must follow everything that writes
locally. Modelling that as N independent cron entries and hoping the clock
orders them is the bug. **A scheduler is not a dependency mechanism.**

Five properties, in the order they matter:

1. **One scheduled entry point.** Ordering lives in code, where it can be read,
   tested, and moved between hosts. The scheduler's only job is "start the
   nightly run, and start it on wake if we were asleep."
2. **Publish is the last stage and it is unconditional.** Every local write sits
   upstream of exactly one publish, so the remote cannot lag by a run — by
   construction rather than by timing.
3. **Every stage idempotent and keyed.** Re-running a whole night must be safe,
   which makes "run it again" the universal recovery action instead of surgical
   repair. Requires natural keys and upserts, not blind inserts.
4. **Catch-up is explicit.** The job asks what work is outstanding rather than
   trusting launchd to re-fire. A machine off for five days does the right thing
   on first run; a machine that runs twice does nothing the second time. This is
   what decouples correctness from scheduler semantics, and it is why the design
   survives a move to GitHub Actions or a Vercel cron.
5. **One run record per night, with per-stage outcome.** Today "nothing happened"
   and "the job died" produce the same thing — no new row. That ambiguity *is*
   this repo's recurring failure shape, and it is what hid the review email for
   sixty nights.

On (5) and the `#45` doctrine ("alarm on the artifact, never on the job's exit
status"): keep the doctrine, sharpen it. A self-reported "I'm alive" ping stays
worthless. A run record naming *which artifacts this run claims to have
produced* is checkable against the rows themselves — the alarm still fires on
the artifact, the run record just says which artifact to go look for.

## What the codebase already gets right

The principles are here; they were applied to one job instead of the pipeline.
Do not rewrite these — extend them.

- `workflow/run-cost-pull.sh` states the rule outright: *"Pull and sync MUST be
  coupled. Running the pull alone silently drifts the dashboard."* Correct
  instinct, scoped to one job.
- `synthesizer.py`'s "which days lack summaries" selection is property (4) done
  properly already.
- `heartbeat.py`'s docstring argues for asserting artifacts and keeping the
  monitor on infrastructure that fails independently. Keep both.

## Steps

Independently shippable, in dependency order. This repo has a history of
half-finished migrations; each step must stand alone.

### 1. Make the remote writes idempotent

Unique index on `review_snapshots (review_type, date)` in `store/turso_store.py`,
`save_review_snapshot` becomes an upsert, then dedupe the existing 10,938 rows
down to the ~69 real ones. Prerequisite for everything below, and it fixes the
duplication on its own.

Check the other `sync_table` legs in `sync_to_turso.py` for the same shape while
here — `project_snapshots` pushes 61 rows a night and may have the same defect.

### 2. Collapse the three daily agents into one ordered pipeline

**This is the step that answers the sequencing question.** One entry point runs:
cost pull -> synthesizer -> review -> (report, if the date matches) -> publish.
The bi-monthly report becomes a date check inside the run rather than its own
agent, and `com.promptlab.report` / `com.promptlab.api-costs` /
`com.promptlab.review` collapse to a single agent.

Order genuinely independent work (the cost pull) first, because of the tradeoff
below. Reuse `workflow/run-nightly.sh` as the outer wrapper — it already handles
caffeinate, timestamps, and log rotation.

**Tradeoff, accepted deliberately:** one job means a hung early stage blocks the
later ones, where today a hung review would not stop the cost pull. That is
correct rather than regrettable — the alternative is publishing a half-built
night — but it makes per-stage timeouts mandatory, not optional.

### 3. Add the run record and cross-check freshness against it

A `nightly_runs` row per run: `run_id` (start timestamp + host), `host`,
`started_at`, `finished_at`, `status`, `stages` (JSON), `claims` (JSON),
`exit_code`. One row per run, stages as a blob — the health check reads exactly
one row (the newest) and renders it, so per-stage rows would buy a group-by and
nothing else.

**Correction to this step as originally written.** The line above used to say
freshness reads the run record *instead of* `max(date)` over the business
tables. That is wrong and would rebuild the bug this whole plan exists to kill:
a run record is a **self-report**, precisely the side-channel claim #45 forbids.
It is **both, cross-checked**. The artifact heartbeats stay exactly as they are;
the run record is added as a new check and as the explanation attached to a
stale one. The four combinations are the point:

- run fresh + stage `ok` + artifact stale → **loudest case**: the job claims
  success and produced nothing. This is the sixty-night review email, and today
  it renders as a bare "stale" with no explanation.
- run fresh + stage `failed`/`skipped` → a named, actionable failure.
- run stale → the host has been off. One line, instead of five artifacts going
  stale at once and reading like five separate breakages.
- run fresh, all `ok`, artifact stale because there was genuinely no work → gets
  *quieter*. Today a quiet week false-alarms the synthesizer at day 2.

**Dual-write, not cloud-direct.** Decided 2026-08-29 after arguing the other
way first. The local row is the source of truth for "did I run"; the cloud row
is a publication of it. What must be avoided is putting the record *inside* the
publish stage, where a publish failure eats the record of the publish failure —
the ordering was the real issue, not the topology. So the cloud push is its own
step **after** publish, and it observes publish rather than depending on it.

The deciding scenario is not the one-night Turso blip (a ≥2-day freshness
threshold swallows that, so resilience buys nothing there). It is **asymmetric
reachability**: laptop awake and running fine, network down for days. Cloud-only
loses those runs permanently. When connectivity returns, publish's `--days 7`
backfills every artifact and the dashboard heals — so the only thing
permanently lost is the record of what the dead nights actually did, which is
exactly the forensic material wanted, and there is no other trace of it because
publish was failing precisely then.

Catch-up rule, stateless and needing no new column: read `max(started_at)` from
Turso, push every local row newer than that, upsert by `run_id`. Self-healing on
the next run — the same shape as `migrate()` deduping on every sync from step 1.

This earns its own line in the invariants list rather than an exception to the
"cloud-direct tables have no sync leg" one. That invariant exists *because* the
absence of a leg makes drift structurally impossible; here `run_id` is
`started_at` + host, rows are immutable once finished, and the push is
upsert-by-key, so drift would require one `run_id` to mean two things.

**Two writes per run**: a `status='running'` row at start, updated at finish. A
host powered off mid-run then leaves a started-never-finished row, which is
strictly more than nothing and distinguishable from "never ran" — that is
property 5 of this plan, and it cannot be had with a single end-of-run write.

**`host` comes from `GROUND_CONTROL_MACHINE`**, and doubles as the first
mechanical check on the one-sender rule: two hosts writing runs on the same
night becomes visible immediately instead of arriving as two emails.

**The write follows `heartbeat.ping`'s rule and never raises.** A monitoring
write must not be able to fail the work it monitors. A Turso outage at 2:30
costs one missing run record, which reads as stale — a loud false alarm, not a
silent pass, which is the correct direction.

**TRAP — grade freshness on `started_at`, never on an insertion timestamp.** If
it grades on arrival, a catch-up push makes three dead nights look like they all
happened at 2am today, which quietly undoes the entire mechanism. Grading on
`started_at` reports stale *during* the outage and heals after.

**Claims.** At the end of the run, before the final write, the pipeline runs the
same SQL the health email's `HEARTBEATS` list runs — but against the **local**
store — and stamps the results in: `{"daily_summaries": "2026-08-29",
"review_snapshots.daily_email": "2026-08-29", ...}`. "Here is what existed
locally when I finished."

The strong reason: **it makes the sync leg checkable.** Today the health email
sees only Turso, so when local has a row the cloud lacks it says "stale" and
you cannot tell whether the job failed to *produce* or failed to *publish* —
different fixes, and a session burned finding out which. With claims it says
*review_snapshots: run claimed 2026-08-29, Turso has 2026-08-27 → publish is
dropping rows.* That bug class is invisible today and this repo has hit it: step
1 found a `sync_table` defect by hand, and `project_snapshots` had to be audited
by hand to prove it didn't have one.

Cost is one shared SQL list with two consumers, so it moves to a module both
sides import, or is duplicated behind a grep-guard test — the pattern this repo
already uses for `describe_elapsed` and the `'weekday 1'` week expression.

### 4. Explicit outstanding-work queries for the readers

Optional, lowest value: a missed nightly email is mostly water under the bridge.
Worth doing only if catch-up after long absences becomes a real complaint.

### 5. Never destroy a paid artifact

Independent of steps 3 and 4 — ships in any order. The counterpart to step 1:
step 1 made remote writes idempotent so re-running is *safe*; this makes
re-running *non-destructive*.

`daily_summaries` has `UNIQUE(project, date)` and `upsert_daily_summary`
overwrites in place, so re-running a day silently replaces prose that was paid
for with an API call, with no history. `weekly_rollups` has the same shape, and
this is not hypothetical: the 2026-08-10 week-grouping repair **deleted 207
rollups outright**. A DB backup existed, so it was recoverable by luck rather
than by design.

The fix: capture the prior row into a `*_superseded` table before an upsert
replaces it, and change the repair scripts (`regroup_weekly_rollups.py` and
friends) to mark rather than `DELETE`. Local-only — superseded rows are history,
not something any reader needs, so no sync leg.

Take `prompt_version` while in these tables: a hash of the system prompt plus
the tool schema, stored on the artifact row. The synthesis prompts do get
iterated, so today old rows are a different vintage with nothing marking it, and
`model` alone does not say which. Roughly ten lines given we're already
migrating the table.

**Scope note, so this does not grow.** A content-addressed synthesis cache — key
on (stage, target, prompt_version, input_hash), skip the call when the tuple
already has a stored output — is the mechanism that would make re-running a
night *free* rather than merely safe. It is deliberately **not** in scope:
measured 2026-08-29, all-time synthesis spend is **$6.06 across 360 successful
calls** (daily $1.64, weekly $0.76, project states $0.48, and a retired
`intentions` type at $3.18 that stopped 2026-06-24). That is engineering to
protect an amount of money that does not matter. Revisit if the spend ever gets
interesting. Note also that 241 `daily_summaries` rows sit against only 81
`daily` synthesis calls, because most summaries came from `/handoff` generating
them inline — the majority of that tier was never bought with API dollars.

## Verification

Step 1: local count and Turso count for `review_snapshots` agree after a dedupe
and stay equal across two consecutive syncs.

Step 2: with the machine deliberately asleep across the scheduled time, one wake
produces one run in the correct order, and Turso's newest `review_snapshots`
date equals the run date — not the day before. This is the actual acceptance
test for the sequencing concern; it must be run against a sleeping host, since
an awake host passes even with the bug present.

Step 3: kill a stage mid-run and confirm the health email distinguishes it from
a night with no work. Separately, block the cloud push (bad URL) for two
consecutive runs and confirm the third run backfills all three rows and that
freshness reported stale *during* the block, not after — that is the
`started_at`-vs-arrival trap, and an awake, online host passes it either way.

Step 5: re-run a day that already has a summary; the new prose is live, the old
prose is in `daily_summaries_superseded`, and nothing was lost. Run
`regroup_weekly_rollups.py --apply` against a seeded bad row and confirm it
marks rather than deletes.
