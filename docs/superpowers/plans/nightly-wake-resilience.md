# Nightly wake resilience

## Context

Diagnosed 2026-09-06 from a week of real unattended runs. Three defects, all
instances of this repo's signature shape: a job kept running while its output
stopped, and the absence was recorded as "nothing" rather than "failure."

Evidence (`nightly_runs` + `nightly-pipeline.log`):

- Runs that fired at 02:30:0x on an **already-awake** laptop succeeded
  (Aug 30, Sep 5, Sep 6). Runs that fired on a **scheduled wake** failed
  (Sep 1, 2, 3, 4), every one at
  `socket.gaierror: [Errno 8] nodename nor servname provided, or not known`.
  launchd fires within ~5s of the wake; DNS is not resolving yet.
- The four failed nights are `status="partial"` in `nightly_runs`, and the
  morning health email was green through all of them.
- `daily_summaries` coverage: 5-7 projects/day normally, **1-2 on
  Aug 31 - Sep 3**. The synthesizer stage reported `ok` on nights when every
  one of its API calls failed.

## Global Constraints

- **Tests are standalone runners, NOT pytest.** Each `scripts/test_*.py` is
  run directly: `.venv/bin/python scripts/test_foo.py`. Follow the existing
  file's structure exactly.
- **Never introduce a wall-clock deadline.** Any timeout or budget in the
  nightly path is measured on `time.monotonic()`. A wall-clock deadline
  aborts healthy runs on a sleeping host — this is settled, see
  `workflow/run-nightly.sh`'s header comment.
- **A monitoring write must never be able to fail the work it monitors.**
  The run-record prelude in `nightly_pipeline.main()` is guarded for this
  reason; keep that property.
- **A failed check reports "could not check", never "fresh."** An empty
  result is stale/never-produced, not healthy.
- Timestamps UTC at rest; calendar days `America/Los_Angeles` on display.
- Python 3.10 locally, but `web/` runs on the Vercel lambda — keep
  `from __future__ import annotations` where the file already has it.

## Task 1: The synthesizer stops reporting success when every call failed

**File:** `synthesizer.py`

Today each of the three API-driven phases catches `Exception` per item, logs
`status="error"` via `store.log_synthesis`, prints `ERROR: <e>`, and
continues (`synthesizer.py:113-120`, `:202-210`, `:295-303`). `main()` then
unconditionally reaches `heartbeat.ping("synthesizer")` and returns 0
(`:420-424`). A night with zero successful calls is indistinguishable from a
night with nothing to do.

Required behaviour:

1. Each of `synthesize_daily_summaries`, `synthesize_weekly_rollups` and
   `synthesize_project_states` returns a `(attempted, errored)` tuple of
   ints. Counting is per item attempted, not per project discovered.
2. `main()` sums these into totals across whichever phases ran.
3. When `errored > 0`, print exactly one line before the Run Summary:
   `WARNING: <errored>/<attempted> synthesis calls failed`
4. When `attempted > 0 and errored == attempted` — a total wipeout — `main()`
   must NOT call `heartbeat.ping("synthesizer")`, must print
   `FAILED: every synthesis call failed; not pinging the heartbeat`, and must
   return exit code 1.
5. A partial failure (`0 < errored < attempted`) still pings and still exits
   0. Some projects legitimately fail to summarize; that is not a dead night.
6. `attempted == 0` (nothing to synthesize) is unchanged: ping, exit 0. A
   quiet day is not a failure.

Do not change the per-item `try/except` bodies or the `log_synthesis` calls —
only add the counting, the summary line, and the exit decision.

**Tests:** new `scripts/test_synthesizer_outcome.py`, standalone runner. Cover
all four cases from points 4-6 (total wipeout, partial, none attempted, all
succeeded) by driving `main()` with a stubbed client whose calls raise, and
assert both the exit code and whether the heartbeat was pinged. Stub the
store and `heartbeat.ping`; make no network calls.

## Task 2: The pipeline waits for DNS before it runs the night

**File:** `nightly_pipeline.py`

Add a network-readiness gate so a wake-fired run does not start into a
resolver that is not up yet.

1. New module-level constants:
   `NETWORK_PROBE_HOST = "api.anthropic.com"`,
   `NETWORK_WAIT_SECONDS = 180`, `NETWORK_POLL_SECONDS = 5`.
2. New function
   `wait_for_network(host=NETWORK_PROBE_HOST, budget_s=NETWORK_WAIT_SECONDS, poll_s=NETWORK_POLL_SECONDS, resolve=socket.getaddrinfo, sleep=time.sleep) -> tuple[bool, str]`.
   It polls `resolve(host, 443)` until it returns without raising.
   - Returns `(True, detail)` on success. `detail` names how long it waited,
     e.g. `"resolved after 35.0s"`, or `"resolved immediately"` when the
     first probe succeeds.
   - Returns `(False, detail)` when the budget is exhausted; `detail` carries
     the last exception's type and message.
   - **The budget is measured on `time.monotonic()`**, never `time.time()` —
     a host that sleeps mid-wait must not have the sleep counted against it.
   - `resolve` and `sleep` are injected so tests need no network and no
     real delay.
3. Call it in `main()` immediately before the stages run, and AFTER the
   guarded run-record prelude (the record of a network-dead night is the
   whole point — it must still be written).
4. On success, print `--- network: <detail> ---`.
5. On failure, print `--- network: NOT READY after <budget>s (<detail>) ---`,
   run **no** stages, and finish the run record with a single synthetic
   `StageResult("network", "failed", <detail>)` so `overall_status` grades
   the night `failed`. `main()` returns 1. Do not attempt the Turso push —
   it cannot work — but do complete the local record.

**Tests:** add to `scripts/test_nightly_pipeline.py`, matching its existing
structure. Cover: resolves on the first probe; resolves on the third probe
(assert the injected sleep was called twice); budget exhausted returns
`False` with the last error in the detail; and that the budget is monotonic
(a `resolve` that also advances a fake wall clock far past the budget still
gets its full number of attempts).

## Task 3: The health email can see a run it did not see the morning it failed

**File:** `web/api/health_report.py`

`NIGHTLY_RUN_SQL` is `ORDER BY started_at DESC LIMIT 1` (`:332-336`), so the
newest run is the only one ever graded. When a night fails for lack of
network, its run record cannot be pushed either; it arrives days later via
`push_runs`' catch-up already older than a newer healthy run, and is
therefore never graded at all. The catch-up mechanism and the grading
mechanism cancel out.

1. New constant `NIGHTLY_RUN_WINDOW_DAYS = 7`.
2. Change `NIGHTLY_RUN_SQL` to select the same columns for every run whose
   `lab_date` falls within the last `NIGHTLY_RUN_WINDOW_DAYS` days, newest
   `started_at` first, with a defensive `LIMIT 50`. Bound the window in SQL
   against a parameter computed from `lab_today()` — do not filter in Python
   over an unbounded fetch.
3. `_check_nightly_run` keeps grading the NEWEST row exactly as it does today
   — every existing branch (`running`, bad stages, `status != "ok"`,
   `age_days`, the claims cross-check) is unchanged and still decides
   `entry["ok"]` and `entry["note"]` for that row.
4. It additionally populates `entry["recent_bad"]`: a list of
   `{"lab_date", "status", "host", "note"}` for every OTHER row in the window
   whose `status` is not `"ok"` or whose `stages` contain a `FAILED_OUTCOMES`
   outcome. Newest first. `note` is the same one-liner shape the newest row
   gets (`", ".join(f"{name}: {outcome}")`, else `f"run reported {status}"`).
5. When `recent_bad` is non-empty, `entry["ok"]` becomes `False` even if the
   newest run is fine, and `entry["note"]`, if empty, becomes
   `f"{len(recent_bad)} bad night(s) in the last {NIGHTLY_RUN_WINDOW_DAYS} days"`.
   A newest-run note already present is kept and the count is appended after
   a `; `.
6. `NIGHTLY_RUN_MAX_AGE_DAYS` changes from `2` to `1`. Two days of slack on a
   nightly job means a missed night is invisible until it has been missed
   twice.
7. `_compose` renders each `recent_bad` entry in the body under the existing
   nightly-run section, one line per night: `<lab_date> <host>: <note>`.
   Follow the section's existing markup and text/html split. The subject
   escalation is already driven by `entry["ok"]`, so point 5 is what makes a
   backfilled failure escalate — no separate subject logic.

**Tests:** add to `scripts/test_web_api.py` using the existing
`_health_mod(up=, hb=, ur=)` harness. Its Turso stub dispatches on the SQL
string, so the nightly-run query's new shape must be matched there — check
how the existing nightly-run tests feed rows and extend that path rather
than adding a parallel stub. Cover: newest ok + one older bad row in the
window → `ok is False` and one `recent_bad` entry; newest ok + no bad rows →
unchanged green; a bad row OUTSIDE the window → ignored; and the age
threshold now failing at 2 days where it used to pass.
