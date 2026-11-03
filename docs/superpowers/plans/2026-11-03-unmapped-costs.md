# Unmapped API spend (#51) — plan

**Spec:** issue #51 (reopened 2026-09-07): define what "unmapped" means,
measure it, and either surface it or fix the attribution. This plan does both.

**Definition.** Unmapped spend is any `api_costs` / `api_usage` row whose
`workspace_id` has no row in `project_workspaces`; `pull_api_costs.py` stamps
it `project='__unmapped__'` at write time (`UNMAPPED_PROJECT`).

**Measured 2026-11-03** (local DB; Admin API workspace list for names):
- $0.03 of $118.40 unmapped: `wrkspc_01UGcmKqG2oA3G5sF8vDdarX`, which the
  Admin API names **byside**.
- `wrkspc_01B8VSus5qTLtiE8YyzRBYuA` ($0.05, 12 rows, Haiku, Jun 25–Jul 29) is
  mapped to prompt-lab as "assumed"; the Admin API names it **recountly**.
  `recountly` is an alias of canonical `raconte` in `project_aliases`.
- `wrkspc_01ShSn1dhfdmFzcWeHEawKGd` (**elusion**) was created 2026-11-03 and has
  no rows yet; it will land unmapped on its first spend.

The structural problem: a new workspace lands `__unmapped__` silently. That is
the repo's recurring failure shape ("absence recorded as nothing" — see
CLAUDE.md). Fix the data, then make the residue loud.

## Global Constraints

- Tests are standalone runners, **not pytest**: `.venv/bin/python scripts/test_<x>.py`.
  New Python tests go in a new or existing `scripts/test_*.py` and must be
  added to `.github/workflows/test.yml` if a new file is created.
- No test touches the real `~/.claude/prompt-history.db` or Turso. Use a temp
  SQLite DB (`get_store` / `SQLiteStore(db_path=...)`) or the existing stubs.
- ruff is pinned to `0.15.22` in CI; run `.venv/bin/ruff check` on touched
  Python files if ruff is installed in the venv.
- Calendar days shown to humans and date windows are `America/Los_Angeles`.
  Never `toISOString().slice(0,10)` in JS or bare `date(col)` in SQL over UTC
  stamps (`api_costs.date` is already a calendar-day string; compare it to a
  Pacific "today minus N" date string).
- A failed check reports "could not check", never "fine" (CLAUDE.md, #45).
- Reader-facing copy is plain language: no "rows", "table", "query",
  "workspace_id" in dashboard text. The health email is read by the engineer
  who wrote the code, so naming the workspace id and the seed script there is
  correct.
- `web/index.html` pure helpers live between `// <pure>` and `// </pure>` and
  must not reference `window`, `document` or `html`; they are tested by
  `node scripts/test_frontend_pure.mjs`.
- Phone fixtures (`scripts/phone/fixtures.mjs`) are synthetic; the repo is
  public. Workspace ids already committed in `seed_project_workspaces.py` are
  fine to reuse.
- Commit on the current branch `claude/unmapped-costs`. Never push.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Task 1: Correct mappings and add a remap mode

Files: `scripts/seed_project_workspaces.py`, new `scripts/test_seed_project_workspaces.py`,
`.github/workflows/test.yml`.

1. In `MAPPINGS`, replace the `wrkspc_01B8VSus5qTLtiE8YyzRBYuA` row and its
   "assumed" comment with
   `("wrkspc_01B8VSus5qTLtiE8YyzRBYuA", "recountly", "raconte")` and a one-line
   comment: `# Named "recountly" by the Admin API (checked 2026-11-03); recountly is an alias of raconte.`
2. Add `("wrkspc_01UGcmKqG2oA3G5sF8vDdarX", "byside", "byside")` and
   `("wrkspc_01ShSn1dhfdmFzcWeHEawKGd", "elusion", "elusion")`.
3. Update the module docstring: say workspace names come from the Admin API
   workspace list (`GET /v1/organizations/workspaces`), and document `--remap`.
4. Add a `--remap` flag. After seeding, for every mapping, UPDATE `api_costs`
   and `api_usage` rows with that `workspace_id` whose `project` differs from
   the mapping's project, setting `project` to it. Print one line per table per
   workspace that changed: `<table>: <workspace_id> <old> -> <new>: <n> rows`,
   and a final total. Without `--remap`, behaviour is unchanged. Also accept
   `--db PATH` so the test can point at a temp DB (default: the store's
   default). Implement via the store's connection if the SQLite store exposes
   one, otherwise open the DB path with `sqlite3`; keep it local-only (never
   Turso). Use parameter bindings.
5. Test (`scripts/test_seed_project_workspaces.py`, standalone, same runner
   style as other `scripts/test_*.py`): temp DB; insert `api_costs` and
   `api_usage` rows for the recountly workspace stamped `prompt-lab`, the byside
   workspace stamped `__unmapped__`, and a prompt-lab workspace row already
   correct. Run seed with `--remap --db <tmp>`; assert recountly rows are now
   `raconte`, byside rows `byside`, the correct row untouched, and the printed
   total equals the number of changed rows. Run again; assert 0 changed
   (idempotent). Run without `--remap` on a fresh DB; assert no row changes.
6. Add the new test file to `.github/workflows/test.yml` alongside the other
   standalone suites.

## Task 2: Health email flags unmapped API spend

Files: `web/api/health_report.py`, `scripts/test_web_api.py`.

1. Add `_check_unmapped_costs()` that runs one Turso query via the module's
   existing `turso_query` helper:
   `SELECT workspace_id, SUM(cost_reported_usd), MAX(date) FROM api_costs WHERE project = '__unmapped__' AND date >= ? GROUP BY workspace_id`
   with `?` = Pacific today minus 30 days (`YYYY-MM-DD`; reuse whatever
   Pacific-date helper the module already has, e.g. `lab_today()`). Coerce the
   SUM with `float(...)` — Turso returns aggregates as strings. Return
   `{"ok": True, "workspaces": [...]}` on success (empty list = nothing
   unmapped), `{"ok": None, "note": <short error>}` when the query fails.
2. Feed it into `_problems(...)` as a new argument (update every caller):
   - workspaces non-empty → one problem: key `costs:unmapped`, severity
     `"stale"`, text
     `"API spend from <n> unmapped workspace(s) in the last 30 days ($<total, 2dp>): <ids comma-separated> — map in scripts/seed_project_workspaces.py, then run it with --remap"`,
     short `"unmapped API spend"`, `age_days` None, `since` = the earliest
     `MAX(date)` among them.
   - check failed → key `costs:unmapped`, severity `"unchecked"`, text
     `"could not check unmapped API spend (<note>)"`, short
     `"unmapped spend unchecked"`.
   - empty → no problem.
   Match the existing problem dict shape exactly (keys: key, severity, text,
   short, age_days, since).
3. Include the result in the dry-run JSON response as `"unmapped_costs"`.
4. Tests in `scripts/test_web_api.py`, using the existing `_health_mod(...)`
   stub. Its Turso stub dispatches on SQL text; add a branch for the new query
   (match on `"__unmapped__"`) so it is separately observable and cannot be
   confused with the pause, freshness or uptime queries. Cover: rows present →
   one `costs:unmapped` stale problem with the total and ids in the text; empty
   → no problem; query raises → one `unchecked` problem; SUM returned as a
   string is summed numerically. Existing tests must still pass.

## Task 3: Costs page shows unmapped spend as "Unmapped"

Files: `web/index.html`, `scripts/test_frontend_pure.mjs`,
`scripts/phone/fixtures.mjs`, `scripts/phone/checks.mjs` (only if a check is
needed).

1. Add a pure helper inside the `// <pure>` block:
   `const UNMAPPED_PROJECT = '__unmapped__';` and
   `function costProjectLabel(p) { return p === UNMAPPED_PROJECT ? 'Unmapped' : p; }`
2. Everywhere the Costs page (`#/costs`) and the daily page's API-spend section
   render a cost row's project name — list rows, chart legend/readout, any
   tooltip — use `costProjectLabel`. An `__unmapped__` row must not link or
   navigate to `#/project/__unmapped__`; render it as plain text with the
   sub-label `not mapped to a project` (same muted sub-label style the page
   already uses for secondary text).
3. Do not change the API or the numbers; totals still include unmapped spend.
4. Unit-test `costProjectLabel` in `scripts/test_frontend_pure.mjs`
   (`__unmapped__` → `Unmapped`, `prompt-lab` → `prompt-lab`).
5. Add one synthetic `__unmapped__` cost row to the costs fixture in
   `scripts/phone/fixtures.mjs` and make sure `node scripts/phone/check.mjs`
   still passes in full (it runs headless WebKit/Edge; deps are installed).
   If an existing check counts projects or rows exactly, update the expected
   value, don't weaken the check.
