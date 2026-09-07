# Read-only review: test coverage and the seams it exposes — 2026-09-07

Read-only. Measured: 410 `@test(...)` cases across 15 files plus `scripts/test_imports.py`
(compile+import smoke, no cases). `scripts/test_web_api.py` is **5604 lines / 243 cases**.

## 1. Coverage shape

**Real behavioural tests.** `nightly_pipeline.py` is best-covered — 38 cases with real
subprocesses, the monotonic-timeout kill (`scripts/test_nightly_pipeline.py:94`), the
network gate's monotonic budget (`:415`), the skip-stages-and-skip-the-push path (`:607`).
`web/api/health_report.py` has 23 `health_report:` + 9 `heartbeats:` + 26 `nightly:` cases
(`scripts/test_web_api.py:2737`, `:3161`, `:3328`). `synthesizer.py`'s wipeout/partial
exit contract is pinned five ways (`scripts/test_synthesizer_outcome.py:178-218`). The
public-draft refusal path — the privacy gate — has 21 cases loading the real scripts
(`scripts/test_public_draft.py:36`). Alias expansion (22), cost pipeline (22), and OAuth
`auth_helper`/`login`/`callback` (44, `scripts/test_web_api.py:1720`) are all genuine.

**Grep-guard / source-text only.** Five `clocks:` guards read source, not behaviour
(`scripts/test_web_api.py:4250`, `:4264`, `:4281`, `:4299`; `scripts/test_send_review.py:242`);
the garm gating guard globs `web/api/*.py` for `resolve_access(` (`:5565-5578`); raw-tier
pins are cross-file greps (`scripts/test_generate_report.py:107,120`,
`scripts/test_send_review.py:128`); the daily-sync leg is asserted by grep
(`scripts/test_sync_clobber.py:164`).

**No tests at all.** `sync_to_turso.sync_table` and `check_public_allowlist_drift`
(`sync_to_turso.py:151`, `:193`) — `scripts/test_sync_clobber.py` covers only
`merge_summary_parts` and `sync_daily_summaries`. Both `send_email`s (`send-review.py:136`,
`web/api/health_report.py:894`) — the health one is stubbed away at
`scripts/test_web_api.py:2931`, the review one never loaded. `send-review.main()`.
`scripts/classify_issues.py`. `web/beacon_helper.py`, `web/classify_helper.py`,
`web/day_helper.py`: transitively only.

**Three highest-risk untested paths**, against "a job keeps running while its output stops":
1. **`sync_table` counts failed rows as synced and `main()` always exits 0.** A per-row
   `upsert_fn` exception is printed and swallowed (`sync_to_turso.py:176-179`), then the
   function returns `len(rows)` (`:190`) — the count of rows *attempted*. `main()` has no
   return and no `sys.exit` (`sync_to_turso.py:221-441`), so the `publish` stage records
   `outcome="ok"` on exit code 0 (`nightly_pipeline.py:137`). The artifact heartbeats are
   the intended backstop, but they grade `max(date)` (`web/artifact_checks.py:28-38`): if
   the newest row lands and older ones drop, freshness is green and rows are silently
   missing. The failure shape exactly, un-instrumented and untested.
2. **Neither Resend send is tested, and both are about to change.** `send-review.py:172-179`
   catches `HTTPError` and returns `None` — the 60-night fix — but nothing asserts it, and
   an `URLError`/timeout (DNS down mid-night) is *not* caught and would crash before the
   snapshot at `send-review.py:259`. `web/api/health_report.py:894` has no try at all and no
   timeout on the from-address resolution path. The from-address lives in
   `REVIEW_FROM_EMAIL` (`send-review.py:144`) and a hardcoded default at
   `web/api/health_report.py:899-901`; there is no test that either falls back sanely.
   (The Resend domain consolidation was cancelled 2026-09-07, so nothing is about to
   change here — the gap is still real, just no longer urgent.)
3. **`pull_api_costs.main()` can write zero rows and exit 0.** Its only `sys.exit(1)` is
   the missing-admin-key guard (`pull_api_costs.py:284`); an empty API response prints
   `api_costs: 0 rows` and returns. Covered on the artifact axis by the `cost pull + sync`
   heartbeat (`web/artifact_checks.py:33-35`), not on the run-record axis.

Correcting `CLAUDE.md`: all three "deliberately deferred" health-email follow-ups are done —
`_apply_recent_bad`'s note-append branch (`scripts/test_web_api.py:3802`), the
`NIGHTLY_RUN_WINDOW_DAYS == 7` pin (`:3823`), the null-host guard (`:3833`).

## 2. Design smells the tests reveal

**The `turso_query` seam is four responsibilities behind one name.** `health_report.py`
calls it at `:182` (pause lookup, must fail *open*), `:296` (artifact freshness, must fail
*loud*), `:510` (nightly run record, a different axis) and `:679` (the uptime archive
*write*). The fixture therefore reconstructs intent from SQL text: `if "INSERT INTO
uptime_daily" in sql` (`scripts/test_web_api.py:2876`), `if "health_email_state" in sql`
(`:2880`), `if "FROM nightly_runs" in sql` (`:2885`), else freshness (`:2909`). Its
docstring says why (`:2790-2794`); the comment at `:2876` records a near-miss where
matching the table name conflated the archive's write with its freshness read. This wants a
`HealthSources` protocol with four named methods — `paused_until()`,
`artifact_max_date(sql)`, `recent_runs(cutoff)`, `write_uptime_row(row)` — passed into
`_compose`/`do_GET` rather than reached through a module global, so each fails
independently by construction and the "must not be conflated" comment becomes a type.

**The stub reimplements the code's own WHERE clause.** `scripts/test_web_api.py:2900-2906`
filters `rows` by `lab_date >= args[0]` "exactly like the real SQL would" — a test
re-deriving production logic is the tell that the window boundary belongs in a Python
function the test can call, not in a SQL string only Turso can execute.

**The grep guards mark behaviour that is not observable from outside.** `clocks:` at
`scripts/test_web_api.py:4281` greps `store/sqlite_store.py` for `date(timestamp)` without
`'localtime'`; `:4299` greps four files for `'weekday 1'`. The missing interface is one
`week_start_expr()` / `lab_day_bucket(col)` helper that all four homes
(`store/sqlite_store.py`, `store/turso_store.py`, `web/api/private_history.py`,
`workflow/bin/gc-read.sh`) call, so drift is impossible rather than merely detected. Same
for `scripts/test_send_review.py:242`, which greps both readers for `describe_elapsed`
because "did the diagnostic get printed" has no return value.

**`store/base.py` (51 methods) has no parity suite.** `sqlite_store.py` (55 defs) and
`turso_store.py` (57) reimplement one contract in two SQL dialects; only three behaviours
are pinned on both sides (`scripts/test_nightly_runs.py:108,142`,
`scripts/test_review_snapshot_idempotency.py`). The rest tests one store and hopes.

## 3. Test-runner design

The standalone-runner convention is fine and should stay. The problem is not pytest's
absence; it is that the `@test` registry, `load_endpoint`, `invoke`, `patch` and the
results printer are **copy-pasted into 13 files** (`grep -l '^def test(name'` over
`scripts/test_*.py`), and that one file is 5604 lines. Smallest move, changing nothing
about how tests are run:

1. Extract `scripts/testlib.py` holding `test()`, `_results`, `main()`,
   `load_endpoint()` (`scripts/test_web_api.py:31`), `invoke()`/`invoke_post()` (`:54`,
   `:79`) and `patch()`/`patch_turso_query()` (`:141`, `:153`). Each runner keeps its
   `if __name__ == "__main__": sys.exit(main())` and is still run directly.
2. Extract `scripts/health_fixture.py` with `_health_env()`/`_health_mod()`
   (`scripts/test_web_api.py:2739-2933`), then move the three health sections
   (`:2737`, `:3161`, `:3328` → `:3930`, ~1200 lines, half the file's cases) into
   `scripts/test_health_email.py`. The `# === ` markers are already the seams.

Do **not** split by endpoint further. The remaining sections are 80-300 lines each and the
cross-cutting guards (`clocks:`, the garm sweep at `:5565`) are deliberately file-global.

## 4. Recommendations, ranked by risk reduced per hour

1. **Make `sync_to_turso` report its own failures** (~1h, closes the repo's signature
   failure in the one stage that always runs). First step: change `sync_table`
   (`sync_to_turso.py:151`) to count successes rather than `len(rows)` and return
   `(synced, failed)`; have `main()` accumulate failures and `sys.exit(1)` when any is
   non-zero, so `nightly_pipeline`'s `publish` stage (`nightly_pipeline.py:117`) records
   `failed` instead of `ok`. Then add the missing cases to `scripts/test_sync_clobber.py`
   using its existing fake store.
2. **Test both `send_email` paths** (~1.5h; the only two unmonitored last steps in the
   system, and the shape of the 60-night review-email outage). First step: `scripts/test_send_email.py`
   loading `send-review.py` via `importlib` the way `scripts/test_send_review.py:31`
   already does, stubbing `urllib.request.urlopen`, pinning three cases — 200 returns the
   id; `HTTPError` returns `None` and the caller still snapshots and exits 1
   (`send-review.py:250-276`); `URLError` must not escape. Plus one `health_report:` case
   calling the real `_send_email` and asserting the `HEALTH_FROM_EMAIL` default
   (`web/api/health_report.py:899`).
3. **Extract `scripts/testlib.py` + `scripts/health_fixture.py`, split the health sections
   out of `test_web_api.py`** (~2h, no behaviour risk, makes 1 and 2 cheaper). First step:
   create `scripts/testlib.py` from `scripts/test_web_api.py:126-166` and have exactly one
   runner import it, proving the convention before the other twelve move.

A `HealthSources` protocol (§2) is the right long-term shape but refactors live
nightly-email code for a readability win; it should follow 1-3, not precede them.

## What is deliberate and should not be "fixed"

- Standalone runners over pytest (`CLAUDE.md`, Testing): no install step, each file
  independently runnable under launchd.
- The grep guards. `scripts/test_web_api.py:4250` and `:4299` exist because the bug they
  catch is invisible to a test that computes its own date. Replacing a guard with a shared
  helper is an improvement; deleting one is not.
- `send-review.py` persisting the snapshot on a failed send (`:270`) while gating only the
  heartbeat on delivery (`:276`). That asymmetry is the 60-night fix.
- `_get_paused_until` failing open (`web/api/health_report.py:188`) while freshness fails
  loud — two different correctness requirements, correctly different.
- No sync leg for the cloud-direct tables, none for `prompts`/`sessions`/`commits`
  (`CLAUDE.md`, Invariants). The absence *is* the guarantee.
