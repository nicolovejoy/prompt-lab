# Review-email ordering (#56) and commits dedup (#57)

Spec: GitHub issues #56 and #57 (their bodies are the authority). No separate spec doc.

## Context

#56, confirmed 2026-09-18 from `nightly-pipeline.log`: the synthesizer finished writing
Sep 17's `daily_summaries` locally at 02:38:40; the `review` stage started the same second and
read Turso (`send-review.py` → `get_store("turso")`); `publish` synced those rows at 02:39:48.
Since f8916c0 made routine `/handoff` lean, the nightly synthesizer is the only writer of
yesterday's rows, so the review now always reads a Turso that is one night behind. The
`publish` leg takes ~14s.

#57: `commits` has no unique key on `hash`, so `INSERT OR IGNORE` never ignores. 2,983 rows,
2,588 distinct hashes on the laptop DB. Daily `commit_count` is NOT inflated —
`SqliteStore` day context dedups by hash (`store/sqlite_store.py` ~L816) — so no downstream
recompute is needed. Session-level commit lists and the raw `COUNT(*)` (~L969) are inflated.

## Global Constraints

- Tests are standalone runners, not pytest: `.venv/bin/python scripts/test_<name>.py`.
  Run the full suite before finishing: `for f in scripts/test_*.py; do .venv/bin/python "$f"; done`.
- No test may touch `~/.claude/prompt-history.db` or Turso, or send email.
- `nightly_runs` is pushed to Turso as its own step AFTER the final `publish` stage — never
  inside a sync leg. Do not change `_finish_run` / `push_runs` ordering.
- The final `publish` stage stays `always=True` and stays last among stages. The cost-pull
  heartbeat still keys on the stage named `publish`.
- Alarm on the artifact; a failure must surface as a failed stage (non-zero exit), never as
  "nothing happened". Absence recorded as nothing is the bug class being fixed.
- `send-review.py` must never read raw-tier *content* (prompts/sessions/commits text) — the
  email's content comes from Turso. A local *count* used only as a guard is allowed.
- Calendar days are `America/Los_Angeles`. Never bucket UTC timestamps with bare `date(col)`.
- Match surrounding code style and comment density. Commit per task, message ending with
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## Task 1: Sync summaries to Turso before the review and report read them

Files: `nightly_pipeline.py`, `scripts/test_nightly_pipeline.py`.

In `build_stages()`, insert a stage between `synthesizer` and `review`:

```python
Stage("sync-summaries", [py, "sync_to_turso.py", "--days", "7"], timeout=900,
      needs=("synthesizer",)),
```

- `review` gets `needs=("synthesizer", "sync-summaries")`; `report` gets the same `needs`
  (`generate-report.py` also reads Turso) and keeps its `condition`.
- If `sync-summaries` fails, `review` and `report` are skipped (a skipped review is a loud,
  recorded failure; a review composed over stale Turso is the silent one). The final
  `publish` stage is unchanged and still runs always.
- Update the module docstring's stage list and the `--help` text (both say
  "cost pull -> synthesizer -> review -> report -> publish") and explain in one or two
  sentences why the early sync exists (the review reads Turso; the synthesizer writes local).
- Check that `sync_to_turso.py` has no side effect that must happen once per night (e.g. a
  heartbeat, a public-allowlist check that emails). If it does, note it in the report; do not
  restructure sync_to_turso.
- Tests: stage order; `review`/`report` needs include `sync-summaries`; a failed
  `sync-summaries` skips `review` and `report` but `publish` still runs; the cost-pull
  heartbeat condition still references `publish`. Follow the existing test style in
  `scripts/test_nightly_pipeline.py`.

## Task 2: Review refuses to report "no activity" on a day that had activity

Files: `send-review.py`, `scripts/test_send_review.py` (and a store method only if none exists).

After the Turso reads in `main()` and BEFORE the existing
`if not weekly_summaries and not weekly_rollups: ... return`, add a guard: if
`daily_summaries_1d` is empty, count this machine's local prompts for `w["review_day"]`
(Pacific calendar day) via the local store. If that count is > 0, print a loud error to stderr
naming the day, the local prompt count and "Turso has no daily_summaries for it", and exit
non-zero (`sys.exit(1)`) — no email, no `review_snapshots` row.

- Use an existing store method for the count if one exists (search `store/sqlite_store.py`
  for prompt counts by date); otherwise add a narrow `count_prompts_on(date)` to the SQLite
  store that buckets by Pacific day consistently with how the rest of the store buckets
  prompts. Do not add it to the abstract base unless the codebase pattern requires it.
- A failure to open or query the local store must not crash differently from other errors —
  let it raise (the stage fails, which is loud). Do not fail open.
- Also make the existing "No summaries or rollups found" early return exit non-zero if local
  prompts exist in the week window — or, if that is materially riskier, leave it and say why
  in the report. Your call; justify it.
- Tests: empty Turso daily + local prompts → exits non-zero, no send, no snapshot; empty
  Turso daily + zero local prompts → current behaviour unchanged; non-empty Turso daily →
  guard not consulted. Stub stores the way `scripts/test_send_review.py` already does.

## Task 3: Dedup script and unique index for `commits`

Files: new `scripts/dedup_commits.py`, new `scripts/test_dedup_commits.py`, the place that
creates the `commits` table for new DBs (find it — likely a schema/init file or the prompt
hook under `workflow/`), `.github/workflows/test.yml` (add the new test to the CI list if the
workflow enumerates tests explicitly).

`scripts/dedup_commits.py [--db PATH] [--apply]`, default DB `~/.claude/prompt-history.db`,
dry-run by default:

- Dry run prints: total rows, distinct hashes, duplicate rows to delete, and how many hashes
  have copies credited to different `session_id`s.
- `--apply`: first write a backup with SQLite's online backup API (`conn.backup`) to
  `<db>.bak-<UTC YYYYmmddTHHMMSSZ>` and print its path; abort if the backup fails. Then, in
  one transaction: `DELETE FROM commits WHERE id NOT IN (SELECT min(id) FROM commits GROUP BY
  hash)` and `CREATE UNIQUE INDEX IF NOT EXISTS commits_hash ON commits(hash)`. Print rows
  deleted. Idempotent: a second `--apply` deletes 0 and succeeds.
- Attribution rule: keep `min(id)` (the first session that recorded the commit). State it in
  the script docstring.
- For new DBs, wherever `CREATE TABLE ... commits` lives, add the same unique index so a fresh
  DB is born correct. `INSERT OR IGNORE` in `workflow/commands/handoff.md` then works as
  written — do not change the skill text beyond, at most, one clause noting the index.
- Grep for every other writer of `commits` (`INSERT INTO commits`, `INSERT OR REPLACE`,
  shell/sqlite3 in `workflow/`, `~/.claude/bin` sources in `workflow/bin/`). Any plain
  `INSERT` would now raise on a duplicate — make it `INSERT OR IGNORE`. List what you found.
- Tests on a temp DB only: dups removed keeping min(id); index exists; second apply is a
  no-op; backup file created and readable; dry run changes nothing.
- DO NOT run `--apply` against the real DB. The controller does that after review, with
  authorization.
