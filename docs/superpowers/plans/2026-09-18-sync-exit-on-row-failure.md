# Plan: sync_to_turso.py exits non-zero when any row fails (#59)

Spec: GitHub issue #59, option 1. `sync_to_turso.py` catches per-row exceptions,
prints them, and exits 0, so the nightly `sync-summaries` and `publish` stages report
`ok` while part of their output never reached Turso.

## Global Constraints

- Network/Turso write failures already raise out of `_execute_many` → `_pipeline` and
  exit non-zero. Do not change that path. This plan covers only the errors the script
  currently catches and swallows.
- Keep syncing every other row and every other table after a failure: a partial sync
  beats none (same reasoning as the pipeline's "publish always runs"). Failure is
  reported at the END, as the exit status.
- `check_public_allowlist_drift()` stays non-fatal and never affects the exit code (its
  own docstring says so; drift is audited separately by readup and the health email).
- `--dry-run` behaviour unchanged.
- Tests are standalone runners, not pytest (see `scripts/test_sync_clobber.py` for the
  pattern). Run with `/Users/nico/src/prompt-lab/.venv/bin/python` (the worktree has no
  venv). CI ruff is pinned to 0.15.22: `/Users/nico/src/prompt-lab/.venv/bin/ruff check`.
- No test touches the real history DB or Turso.

## Task 1: Collect swallowed failures and exit 1

Files: `sync_to_turso.py`, new `scripts/test_sync_failures.py`,
`.github/workflows/test.yml`.

1. Every place in `sync_to_turso.py` that catches an exception and only prints it
   records a failure instead of (in addition to) printing:
   - `sync_daily_summaries`: the per-part upsert loop and the per-pair rebuild loop.
   - `sync_table`: the per-row upsert loop.
   - the `project_aliases` block in `main()` (its `except` currently swallows even a
     network error).
   Use a simple mechanism, e.g. a module-level list reset at the start of `main()`, or
   functions returning/accepting a failures list. Each entry is one human-readable
   string: `"<table>: <row identifier>: <ExceptionType>: <message>"`.
2. `sync_table` currently prints `"{table}: {len(rows)} rows synced"` even when some
   rows failed. Print the real count and, when non-zero, the failure count, e.g.
   `"  api_costs: 41 rows synced, 1 failed"`. Its return value becomes the number that
   actually synced. Same honesty for `sync_daily_summaries`' "parts synced" line (it
   already counts `synced` correctly; add the failure count to the line when non-zero).
3. At the end of `main()`, after the `Total:` line and after
   `check_public_allowlist_drift()` runs: if any failures were recorded, print
   `"\nFAILED: <N> row(s) did not sync:"` followed by one indented line per failure,
   capped at 20 lines plus `"  … and <M> more"`, and exit with status 1. No failures →
   exit 0 as today.
4. Update the module docstring (or `main`'s) with one short paragraph: per-row errors
   no longer pass silently; the run finishes every table, then exits 1 so the nightly
   stage reports failed (#59).
5. New `scripts/test_sync_failures.py` (standalone runner, PASS/FAIL lines, exit 1 on
   any failure) with fakes in the style of `scripts/test_sync_clobber.py`, covering:
   - `sync_table` with one of three rows raising in `upsert_fn`: the other two rows'
     statements are still flushed, one failure is recorded naming the table and row,
     and the return value is 2.
   - `sync_daily_summaries` with one part raising: other parts still sync and one
     failure is recorded.
   - A clean `sync_table` run records no failures.
   - The end-of-run exit decision: failures present → exit status 1 and the FAILED
     block printed; none → exit 0. Factor that decision into a small function (e.g.
     `finish(failures) -> int`) so it can be tested without running `main()`.
   - The 20-line cap on the printed list.
6. Add `python scripts/test_sync_failures.py` to `.github/workflows/test.yml` next to
   `test_sync_clobber.py`.
7. Run `scripts/test_sync_failures.py`, `scripts/test_sync_clobber.py`,
   `scripts/test_nightly_pipeline.py`, `scripts/test_public_allowlist.py` and ruff on
   the changed files. All must pass.
