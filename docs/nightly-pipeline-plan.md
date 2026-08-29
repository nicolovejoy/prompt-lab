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
Step 2's sleeping-host acceptance test pends the first overnight run. Steps 3–4
not started. Supersedes the tactical "write the review snapshot straight to
Turso" idea, which patched a symptom.

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

### 3. Add the run record and point freshness at it

A `nightly_runs` row per run: started_at, finished_at, per-stage status, and the
artifacts each stage claims. Freshness in `web/api/health_report.py` reads that
instead of inferring health from `max(date)` over business tables, so a quiet
night stops looking like a dead job.

### 4. Explicit outstanding-work queries for the readers

Optional, lowest value: a missed nightly email is mostly water under the bridge.
Worth doing only if catch-up after long absences becomes a real complaint.

## Verification

Step 1: local count and Turso count for `review_snapshots` agree after a dedupe
and stay equal across two consecutive syncs.

Step 2: with the machine deliberately asleep across the scheduled time, one wake
produces one run in the correct order, and Turso's newest `review_snapshots`
date equals the run date — not the day before. This is the actual acceptance
test for the sequencing concern; it must be run against a sleeping host, since
an awake host passes even with the bug present.

Step 3: kill a stage mid-run and confirm the health email distinguishes it from
a night with no work.
