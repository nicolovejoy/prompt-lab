# Nightly Run Record + Paid-Artifact Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the nightly pipeline a per-run record that the health email cross-checks against the existing artifact heartbeats, and stop the synthesizer from silently destroying prose that cost an API call.

**Architecture:** A `nightly_runs` table written twice per run (a `running` row at start, a final row at finish) to the **local** store, then pushed to Turso as its own step *after* the publish stage so it observes publish rather than depending on it. Catch-up is stateless: push local rows newer than Turso's newest `started_at`, upsert by `run_id`. The health email keeps every existing `max(date)` artifact check unchanged and adds the run record as a second axis — the run record explains a stale artifact, it never replaces the check on it. Separately, the two paid-artifact tables gain archive-before-overwrite.

**Tech Stack:** Python 3.9-compatible stdlib, SQLite (local), Turso HTTP v3 pipeline API (cloud), Vercel Python serverless (`web/api/`), standalone test runners (no pytest).

**Spec:** `docs/nightly-pipeline-plan.md` — steps 3 and 5. Read the "### 3." and "### 5." sections plus "Invariants" and "Traps" in `CLAUDE.md` before starting.

## Global Constraints

- **Tests are standalone runners, NOT pytest.** `python -m pytest` fails at collection. Each file is run directly and prints PASS/FAIL per case, exiting 1 if any fail. Follow the existing harness shape in `scripts/test_nightly_pipeline.py`.
- **This is a git worktree with no `.venv` of its own.** Run every test with the main checkout's interpreter: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_<name>.py`. Do not create a venv here, do not `pip install` anything.
- **Python 3.9 compatibility is required.** Every new module starts with `from __future__ import annotations`. Using `X | None` in an annotation without that import has broken this repo's jobs before.
- **UTC at rest, `America/Los_Angeles` on display.** Never form a date bucket with a bare `date(col)` in SQL or `toISOString().slice(0,10)` in JS. New date-bucket columns store a Pacific calendar day computed explicitly.
- **Never add a sync leg to a cloud-direct table** (`page_views`, `health_email_state`, `project_metadata`, `issue_categories`, `uptime_daily`). `nightly_runs` is a new, separate case, explicitly allowed by the spec, and its push is upsert-by-`run_id`.
- **Turso returns `SUM()`/`COUNT()` aggregates as JSON strings.** Coalesce with `int()` before arithmetic.
- **Timeouts are monotonic, never wall-clock.** Do not add a wall-clock deadline anywhere in `nightly_pipeline.py`.
- **Never let a monitoring write fail the work it monitors.** Every `nightly_runs` write is wrapped so it cannot raise into the pipeline — same rule as `heartbeat.ping`.
- **Bind SQL parameters.** No f-string interpolation of values into SQL.
- **Do not run the real pipeline, send email, or write to the real Turso database.** Tests use in-memory or temp-file SQLite only. Do not read `.env`, `.env.local`, or any secret material.
- **CI pins ruff to `0.15.22`.** Match the existing style; do not reformat untouched code.
- Commit after each task's tests pass. Conventional-ish subject lines, wrapped body explaining *why*.

---

### Task 1: `nightly_runs` schema and store methods

**Files:**
- Modify: `store/base.py` (add two abstract methods near the `save_review_snapshot` block)
- Modify: `store/sqlite_store.py` (table in `migrate()`, two methods)
- Modify: `store/turso_store.py` (table in `migrate()`, two methods)
- Test: `scripts/test_nightly_runs.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, on `KnowledgeStore` (both backends implement identically):
  - `upsert_nightly_run(self, *, run_id: str, host: str, started_at: str, lab_date: str, status: str, finished_at: str | None = None, stages: list | None = None, claims: dict | None = None, exit_code: int | None = None) -> None`
  - `get_nightly_runs(self, *, limit: int = 10, started_after: str | None = None) -> list[dict]` — newest first, ordered by `started_at DESC`. Rows have keys `run_id, host, started_at, lab_date, finished_at, status, stages, claims, exit_code, created_at`; `stages` and `claims` come back **decoded** (list / dict), or `None` when the column is NULL.

**Schema (identical in both stores):**

```sql
CREATE TABLE IF NOT EXISTS nightly_runs (
    run_id TEXT PRIMARY KEY,
    host TEXT NOT NULL,
    started_at TEXT NOT NULL,
    lab_date TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    stages TEXT,
    claims TEXT,
    exit_code INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_nightly_runs_started ON nightly_runs(started_at);
```

`started_at`/`finished_at` are UTC ISO-8601 seconds (`2026-08-30T09:30:04Z`). `lab_date` is the Pacific calendar day the run started — it exists so the health check compares plain date strings like every other artifact, instead of doing timezone math inside the Vercel lambda. `status` is one of `running`, `ok`, `partial`, `failed`.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_nightly_runs.py`:

```python
"""Tests for the nightly_runs table and its store methods
(nightly-pipeline-plan step 3).

The Turso store's real SQL is exercised against in-memory sqlite — the same
technique as scripts/test_review_snapshot_idempotency.py — so the upsert
semantics that matter in production are asserted here without a network call.

Run: /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_runs.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

_results = []


def test(name):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
        except Exception as e:  # noqa: BLE001
            _results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn
    return deco


def _store():
    s = SqliteKnowledgeStore(db_path=":memory:")
    s.migrate()
    return s


@test("start then finish leaves exactly one row")
def _():
    s = _store()
    s.upsert_nightly_run(run_id="r1", host="laptop",
                         started_at="2026-08-30T09:30:04Z",
                         lab_date="2026-08-30", status="running")
    s.upsert_nightly_run(run_id="r1", host="laptop",
                         started_at="2026-08-30T09:30:04Z",
                         lab_date="2026-08-30", status="ok",
                         finished_at="2026-08-30T09:34:00Z",
                         stages=[{"name": "publish", "outcome": "ok"}],
                         claims={"synthesizer": "2026-08-29"},
                         exit_code=0)
    rows = s.get_nightly_runs()
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert rows[0]["status"] == "ok", rows[0]["status"]
    assert rows[0]["finished_at"] == "2026-08-30T09:34:00Z"
    s.close()


@test("stages and claims round-trip decoded")
def _():
    s = _store()
    s.upsert_nightly_run(run_id="r1", host="laptop",
                         started_at="2026-08-30T09:30:04Z",
                         lab_date="2026-08-30", status="ok",
                         stages=[{"name": "review", "outcome": "failed",
                                  "detail": "exit 1"}],
                         claims={"synthesizer": "2026-08-29"})
    row = s.get_nightly_runs()[0]
    assert row["stages"][0]["outcome"] == "failed", row["stages"]
    assert row["claims"]["synthesizer"] == "2026-08-29", row["claims"]
    s.close()


@test("null stages and claims come back as None, not a crash")
def _():
    s = _store()
    s.upsert_nightly_run(run_id="r1", host="laptop",
                         started_at="2026-08-30T09:30:04Z",
                         lab_date="2026-08-30", status="running")
    row = s.get_nightly_runs()[0]
    assert row["stages"] is None, row["stages"]
    assert row["claims"] is None, row["claims"]
    s.close()


@test("get_nightly_runs orders newest first and honours started_after")
def _():
    s = _store()
    for n, ts in [("r1", "2026-08-28T09:30:00Z"),
                  ("r2", "2026-08-29T09:30:00Z"),
                  ("r3", "2026-08-30T09:30:00Z")]:
        s.upsert_nightly_run(run_id=n, host="laptop", started_at=ts,
                             lab_date=ts[:10], status="ok")
    assert [r["run_id"] for r in s.get_nightly_runs()] == ["r3", "r2", "r1"]
    later = s.get_nightly_runs(started_after="2026-08-28T09:30:00Z")
    assert [r["run_id"] for r in later] == ["r3", "r2"], later
    assert len(s.get_nightly_runs(limit=1)) == 1
    s.close()


@test("migrate is idempotent")
def _():
    s = _store()
    s.upsert_nightly_run(run_id="r1", host="laptop",
                         started_at="2026-08-30T09:30:04Z",
                         lab_date="2026-08-30", status="ok")
    s.migrate()
    assert len(s.get_nightly_runs()) == 1
    s.close()


def main():
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_runs.py`
Expected: every case FAILs with `AttributeError: 'SqliteKnowledgeStore' object has no attribute 'upsert_nightly_run'`.

- [ ] **Step 3: Add the abstract methods**

In `store/base.py`, after the `save_review_snapshot` abstract method, add:

```python
    # ---- Nightly run record (nightly-pipeline-plan step 3) ----

    @abstractmethod
    def upsert_nightly_run(self, *, run_id: str, host: str, started_at: str,
                           lab_date: str, status: str,
                           finished_at: str | None = None,
                           stages: list | None = None,
                           claims: dict | None = None,
                           exit_code: int | None = None) -> None:
        """Write or update one nightly pipeline run, keyed by run_id.

        Called twice per run: once with status='running' before any stage,
        once at the end with the full outcome. Upsert rather than insert so a
        catch-up push of an already-pushed row is a no-op.
        """

    @abstractmethod
    def get_nightly_runs(self, *, limit: int = 10,
                         started_after: str | None = None) -> list[dict]:
        """Runs newest first. `stages` and `claims` are decoded, or None."""
```

- [ ] **Step 4: Implement in the SQLite store**

In `store/sqlite_store.py`, add the table to the `executescript` block in `migrate()` (put it after `review_snapshots`), then add the methods near `save_review_snapshot`:

```python
    # ---- Nightly run record ----

    def upsert_nightly_run(self, *, run_id, host, started_at, lab_date, status,
                           finished_at=None, stages=None, claims=None,
                           exit_code=None):
        self._conn.execute("""
            INSERT INTO nightly_runs
                (run_id, host, started_at, lab_date, finished_at, status,
                 stages, claims, exit_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                host = excluded.host,
                started_at = excluded.started_at,
                lab_date = excluded.lab_date,
                finished_at = excluded.finished_at,
                status = excluded.status,
                stages = excluded.stages,
                claims = excluded.claims,
                exit_code = excluded.exit_code
        """, (run_id, host, started_at, lab_date, finished_at, status,
              json.dumps(stages) if stages is not None else None,
              json.dumps(claims) if claims is not None else None,
              exit_code))
        self._conn.commit()

    def get_nightly_runs(self, *, limit=10, started_after=None):
        clauses, params = ["1=1"], []
        if started_after:
            clauses.append("started_at > ?")
            params.append(started_after)
        sql = (f"SELECT * FROM nightly_runs WHERE {' AND '.join(clauses)} "
               "ORDER BY started_at DESC LIMIT ?")
        params.append(limit)
        return [_decode_run(dict(r))
                for r in self._conn.execute(sql, params).fetchall()]
```

Add this module-level helper near the top of `store/sqlite_store.py` (below the imports):

```python
def _decode_run(row: dict) -> dict:
    """JSON-decode a nightly_runs row's blob columns in place.

    Shared shape with the Turso store: both return `stages` as a list and
    `claims` as a dict, so no reader needs to know which backend it holds.
    """
    for col in ("stages", "claims"):
        raw = row.get(col)
        row[col] = json.loads(raw) if raw else None
    return row
```

- [ ] **Step 5: Run the tests**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_runs.py`
Expected: 5/5 passed.

- [ ] **Step 6: Implement in the Turso store**

In `store/turso_store.py`, add the same `CREATE TABLE`/`CREATE INDEX` to the `_pipeline([...])` list in `migrate()` (as two separate `{"sql": ...}` entries), and add the methods next to `save_review_snapshot`:

```python
    # ---- Nightly run record ----

    def upsert_nightly_run(self, *, run_id, host, started_at, lab_date, status,
                           finished_at=None, stages=None, claims=None,
                           exit_code=None):
        # Upsert by run_id: the pipeline's catch-up push replays local rows
        # newer than the remote high-water mark, so re-pushing an already
        # pushed run must be a no-op rather than a duplicate. created_at is
        # deliberately not updated on conflict — it records first arrival.
        self._execute("""
            INSERT INTO nightly_runs
                (run_id, host, started_at, lab_date, finished_at, status,
                 stages, claims, exit_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                host = excluded.host,
                started_at = excluded.started_at,
                lab_date = excluded.lab_date,
                finished_at = excluded.finished_at,
                status = excluded.status,
                stages = excluded.stages,
                claims = excluded.claims,
                exit_code = excluded.exit_code
        """, [run_id, host, started_at, lab_date, finished_at, status,
              json.dumps(stages) if stages is not None else None,
              json.dumps(claims) if claims is not None else None,
              exit_code])

    def get_nightly_runs(self, *, limit=10, started_after=None):
        clauses, args = ["1=1"], []
        if started_after:
            clauses.append("started_at > ?")
            args.append(started_after)
        sql = (f"SELECT * FROM nightly_runs WHERE {' AND '.join(clauses)} "
               "ORDER BY started_at DESC LIMIT ?")
        args.append(limit)
        rows = self._rows_to_dicts(self._execute(sql, args))
        for row in rows:
            for col in ("stages", "claims"):
                raw = row.get(col)
                row[col] = json.loads(raw) if raw else None
        return rows
```

- [ ] **Step 7: Add a Turso-SQL-against-sqlite test**

Append to `scripts/test_nightly_runs.py`, above `def main()`. Read `scripts/test_review_snapshot_idempotency.py` first and mirror however it extracts and replays the Turso store's SQL against an in-memory sqlite connection — reuse that helper rather than inventing a second technique.

The case to assert: run the Turso `upsert_nightly_run` SQL twice with the same `run_id` and different `status`, and confirm the table holds exactly one row whose `status` is the second value. This is the property that keeps the catch-up push from re-duplicating Turso the way `review_snapshots` was duplicated 11,848-fold before step 1.

- [ ] **Step 8: Run tests and commit**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_runs.py`
Then the full suite: `for f in scripts/test_*.py; do /Users/nico/src/prompt-lab/.venv/bin/python "$f"; done`
Expected: all green, including the pre-existing files.

```bash
git add store/base.py store/sqlite_store.py store/turso_store.py scripts/test_nightly_runs.py
git commit -m "nightly_runs table and store methods (both backends)"
```

---

### Task 2: The pipeline writes the run record

**Files:**
- Modify: `nightly_pipeline.py`
- Test: `scripts/test_nightly_pipeline.py` (extend)

**Interfaces:**
- Consumes: `store.get_store()`, `upsert_nightly_run(...)` from Task 1.
- Produces:
  - `run_identity(now_utc: datetime, host: str) -> tuple[str, str, str]` returning `(run_id, started_at, lab_date)`.
  - `overall_status(results: list[StageResult]) -> str` returning `"ok" | "partial" | "failed"`.
  - `record_run(store, *, run_id, host, started_at, lab_date, status, **kw) -> bool` — the never-raises wrapper. Returns True if the write landed.
  - `main()` continues to return the process exit code.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_nightly_pipeline.py`, above `def main()`:

```python
@test("run_identity derives run_id from started_at and host")
def _():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 30, 9, 30, 4, tzinfo=timezone.utc)
    run_id, started_at, lab_date = np.run_identity(now, "laptop")
    assert started_at == "2026-08-30T09:30:04Z", started_at
    # 09:30 UTC on Aug 30 is 02:30 Pacific the SAME day — the nightly slot.
    assert lab_date == "2026-08-30", lab_date
    assert run_id == "2026-08-30T09:30:04Z|laptop", run_id


@test("lab_date is Pacific, not UTC (the 5pm rollover trap)")
def _():
    from datetime import datetime, timezone
    # 02:00 UTC on Aug 30 is 19:00 Pacific on Aug 29.
    now = datetime(2026, 8, 30, 2, 0, 0, tzinfo=timezone.utc)
    _, _, lab_date = np.run_identity(now, "laptop")
    assert lab_date == "2026-08-29", lab_date


@test("overall_status distinguishes ok, partial and failed")
def _():
    R = np.StageResult
    assert np.overall_status([R("a", "ok"), R("b", "not-due")]) == "ok"
    assert np.overall_status([R("a", "ok"), R("b", "failed")]) == "partial"
    assert np.overall_status([R("a", "failed"), R("b", "timeout")]) == "failed"
    assert np.overall_status([]) == "failed"


@test("record_run never raises when the store blows up")
def _():
    class Exploding:
        def upsert_nightly_run(self, **kw):
            raise RuntimeError("turso is down")

    ok = np.record_run(Exploding(), run_id="r1", host="laptop",
                       started_at="2026-08-30T09:30:04Z",
                       lab_date="2026-08-30", status="running")
    assert ok is False, "a failed monitoring write must report False, not raise"


@test("record_run returns True on success and forwards every field")
def _():
    seen = {}

    class Capturing:
        def upsert_nightly_run(self, **kw):
            seen.update(kw)

    ok = np.record_run(Capturing(), run_id="r1", host="laptop",
                       started_at="2026-08-30T09:30:04Z",
                       lab_date="2026-08-30", status="ok",
                       finished_at="2026-08-30T09:34:00Z",
                       stages=[{"name": "publish", "outcome": "ok"}],
                       exit_code=0)
    assert ok is True
    assert seen["status"] == "ok"
    assert seen["stages"][0]["name"] == "publish"
    assert seen["exit_code"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_pipeline.py`
Expected: the five new cases FAIL with `AttributeError: module 'nightly_pipeline' has no attribute 'run_identity'`; the pre-existing cases still pass.

- [ ] **Step 3: Implement the helpers**

Add to `nightly_pipeline.py`, after `run_pipeline`:

```python
def run_identity(now_utc: datetime, host: str) -> tuple:
    """(run_id, started_at, lab_date) for a run starting at `now_utc`.

    run_id is deterministic from the pair that identifies a run, so the start
    write and the finish write address the same row without carrying state,
    and a catch-up push cannot mint a second row for a run already sent.

    lab_date is the PACIFIC calendar day (#48). The nightly slot is 02:30
    Pacific, which is 09:30 UTC — the same date — but a run that starts
    before 5pm Pacific on the preceding evening is a different UTC day, and
    grading freshness on a UTC bucket is the phantom-tomorrow bug.
    """
    started_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    lab_date = now_utc.astimezone(LAB_TZ).date().isoformat()
    return f"{started_at}|{host}", started_at, lab_date


def overall_status(results: list) -> str:
    """ok when nothing failed, partial when some did, failed when none ran."""
    if not results:
        return "failed"
    bad = {"failed", "timeout", "skipped"}
    failures = [r for r in results if r.outcome in bad]
    if not failures:
        return "ok"
    return "failed" if len(failures) == len(results) else "partial"


def record_run(store, **fields) -> bool:
    """Write the run record. NEVER raises — returns True if the write landed.

    Same rule as heartbeat.ping and record_login: a monitoring write must not
    be able to fail the work it monitors. A dropped record costs one false
    staleness line in the health email; an exception here would cost the
    night's actual work, which is the wrong trade in every direction.
    """
    try:
        store.upsert_nightly_run(**fields)
        return True
    except Exception as e:  # noqa: BLE001 — deliberately swallowed, see above
        print(f"run record: write failed ({type(e).__name__}: {e})", flush=True)
        return False


def machine_host() -> str:
    """This machine's label, shared with the Turso sync so both agree.

    Imported lazily: sync_to_turso pulls in the store and env loading, and
    nightly_pipeline must stay importable by tests without that cost.
    """
    from sync_to_turso import machine_label
    return machine_label()
```

Add `from datetime import date, datetime, timezone` to the existing datetime import line.

- [ ] **Step 4: Wire it into `main()`**

Rewrite `main()` so the record brackets the run. The start write happens **before** the first stage and the finish write **after** the heartbeat:

```python
def main() -> int:
    from store import get_store

    host = machine_host()
    run_id, started_at, lab_date = run_identity(
        datetime.now(timezone.utc), host)

    store = get_store()
    try:
        store.migrate()
    except Exception as e:  # noqa: BLE001
        print(f"run record: migrate failed ({type(e).__name__}: {e})", flush=True)

    # Written before any stage so a host powered off mid-run leaves a
    # started-never-finished row. "Died mid-run" and "never ran" are
    # different facts and this is the only thing that tells them apart.
    record_run(store, run_id=run_id, host=host, started_at=started_at,
               lab_date=lab_date, status="running")

    stages = build_stages()
    results = run_pipeline(stages)
    by_name = {r.name: r for r in results}

    # Heartbeat only when both legs actually landed (see module docstring).
    if by_name.get("cost-pull") and by_name["cost-pull"].ok \
            and by_name.get("publish") and by_name["publish"].ok:
        subprocess.run([sys.executable, str(ROOT / "heartbeat.py"), "cost-pull"],
                       cwd=ROOT, timeout=60)

    failed = [r for r in results if r.outcome in ("failed", "timeout", "skipped")]
    exit_code = 1 if failed else 0
    summary = " · ".join(f"{r.name}={r.outcome}" for r in results)
    print(f"pipeline: {summary}", flush=True)

    record_run(store, run_id=run_id, host=host, started_at=started_at,
               lab_date=lab_date, status=overall_status(results),
               finished_at=datetime.now(timezone.utc).strftime(
                   "%Y-%m-%dT%H:%M:%SZ"),
               stages=[{"name": r.name, "outcome": r.outcome,
                        "detail": r.detail} for r in results],
               exit_code=exit_code)
    try:
        store.close()
    except Exception:  # noqa: BLE001
        pass
    return exit_code
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_pipeline.py`
Expected: all cases pass, including the 11 pre-existing ones.

- [ ] **Step 6: Commit**

```bash
git add nightly_pipeline.py scripts/test_nightly_pipeline.py
git commit -m "Pipeline brackets each run with a nightly_runs record"
```

---

### Task 3: Shared artifact-check list and the claims stamp

**Files:**
- Create: `web/artifact_checks.py`
- Modify: `web/vercel.json` (add the new file to `includeFiles`)
- Modify: `web/api/health_report.py` (build `HEARTBEATS` from the shared list)
- Modify: `nightly_pipeline.py` (add `collect_claims`, pass into the finish write)
- Test: `scripts/test_nightly_pipeline.py` (extend), `scripts/test_web_api.py` (extend)

**Interfaces:**
- Consumes: `record_run` and `main()` from Task 2.
- Produces:
  - `web/artifact_checks.py` exporting `ARTIFACT_CHECKS: list[tuple[str, str, int]]` — `(label, sql, max_age_days)`.
  - `nightly_pipeline.collect_claims(store) -> dict` mapping label → max date string (or `None`), never raising.

**Why a shared module rather than a duplicated list:** the run record's claims are only meaningful if they name the same artifacts the health email grades. Two copies would drift and a claim would silently start answering a question nobody asked. Root scripts already put `web/` on `sys.path` and import `day_helper` (see `send-review.py:14`), so one module serves both readers with no duplication and no grep guard.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_nightly_pipeline.py`, above `def main()`:

```python
@test("collect_claims reports a max date per artifact and never raises")
def _():
    class FakeStore:
        def __init__(self, rows):
            self.rows = rows

        class _Conn:
            def __init__(self, rows):
                self.rows = rows

            def execute(self, sql, params=None):
                return [(self.rows.get(sql),)]

        @property
        def conn(self):
            return self._Conn(self.rows)

    import web.artifact_checks as ac  # noqa: F401
    from web.artifact_checks import ARTIFACT_CHECKS
    rows = {sql: "2026-08-29" for _, sql, _ in ARTIFACT_CHECKS}
    claims = np.collect_claims(FakeStore(rows))
    assert set(claims) == {label for label, _, _ in ARTIFACT_CHECKS}, claims
    assert all(v == "2026-08-29" for v in claims.values()), claims


@test("collect_claims survives a store that raises")
def _():
    class Exploding:
        @property
        def conn(self):
            raise RuntimeError("db gone")

    assert np.collect_claims(Exploding()) == {}


@test("ARTIFACT_CHECKS excludes uptime archive (no local counterpart)")
def _():
    from web.artifact_checks import ARTIFACT_CHECKS
    labels = {label for label, _, _ in ARTIFACT_CHECKS}
    assert "uptime archive" not in labels, (
        "uptime_daily is cloud-direct — the pipeline cannot claim it locally")
```

Append to `scripts/test_web_api.py` (follow the file's existing test-registration style, whatever it is — read the top of the file first):

```python
# HEARTBEATS must stay a superset of the shared list: the pipeline claims what
# it can see locally, the email grades that plus the cloud-direct archive.
def test_heartbeats_superset_of_artifact_checks():
    from web.artifact_checks import ARTIFACT_CHECKS
    mod = _health_mod()
    hb_labels = {name for name, _, _ in mod.HEARTBEATS}
    shared = {label for label, _, _ in ARTIFACT_CHECKS}
    assert shared <= hb_labels, shared - hb_labels
    assert "uptime archive" in hb_labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run both files. Expected: `ModuleNotFoundError: No module named 'web.artifact_checks'`.

- [ ] **Step 3: Create the shared module**

Create `web/artifact_checks.py`:

```python
"""Artifact-freshness declarations, shared by two readers on purpose.

The Vercel health email (web/api/health_report.py) runs these against Turso
and grades the age. nightly_pipeline.py runs the same SQL against the LOCAL
store at the end of a run and stamps the results into the run record as
`claims` — "here is what existed locally when I finished".

Both readers must name the same artifacts or the cross-check is meaningless:
comparing a claim against a differently-scoped remote query would answer a
question nobody asked. That is why this list has one home.

What the cross-check buys, and it is the point of the whole mechanism: today
the health email sees only Turso, so when local holds a row the cloud lacks
it reports "stale" and cannot say whether the job failed to PRODUCE or failed
to PUBLISH — different bugs, different fixes. With claims it can say which.

`uptime_daily` is deliberately absent: it is cloud-direct, written by the
Vercel cron itself, and has no local counterpart for the pipeline to claim.
health_report.py appends it to its own HEARTBEATS list.

Thresholds are DAYS, not hours — every artifact here is date-granular.
"""

from __future__ import annotations

# (label, sql, max_age_days)
ARTIFACT_CHECKS = [
    ("review email",
     "SELECT max(date) AS d FROM review_snapshots "
     "WHERE review_type IN ('daily_email', 'weekly_email')", 2),
    ("synthesizer", "SELECT max(date) AS d FROM daily_summaries", 2),
    ("weekly rollups", "SELECT max(week_start) AS d FROM weekly_rollups", 10),
    # Anthropic's Admin API reports a day behind, so yesterday is the normal
    # newest row — 2 would alarm on a healthy pipeline.
    ("cost pull + sync", "SELECT max(date) AS d FROM api_costs", 3),
    ("bi-monthly report",
     "SELECT max(date) AS d FROM review_snapshots "
     "WHERE review_type = 'monthly_report'", 20),
]
```

- [ ] **Step 4: Rebuild `HEARTBEATS` from the shared list**

In `web/api/health_report.py`, replace the literal `HEARTBEATS = [...]` with a composition, **preserving every existing comment** by moving it to the appropriate place:

```python
from artifact_checks import ARTIFACT_CHECKS

# ... existing explanatory comment block stays here, unchanged ...
HEARTBEATS = ARTIFACT_CHECKS + [
    # Added 2026-08-02 after the archive wrote on Aug 1 and not Aug 2, and
    # nothing said so for two days. READ THE LIMIT BEFORE TRUSTING THIS ONE:
    # unlike every entry above, the watcher is not outside the watched job —
    # this same request writes uptime_daily and then reports on it. So it
    # catches "cron alive, pull broken" and CANNOT catch "cron dead", which
    # degrades to "no email arrived" — the weakest signal in the system and the
    # one that hid the review email for sixty nights. Closing that properly
    # needs a check on infrastructure that fails independently of Vercel's
    # scheduler; UptimeRobot's HEARTBEAT type is paid-only, which is what sent
    # #45 down the artifact-freshness route in the first place.
    ("uptime archive", "SELECT max(date) AS d FROM uptime_daily", 2),
]
```

Note the import is `from artifact_checks import ...` (not `from web.artifact_checks`) because the lambda flattens `includeFiles` next to the handler — match how `day_helper` is imported in the same file.

- [ ] **Step 5: Add the file to `includeFiles`**

In `web/vercel.json`, add `artifact_checks.py` to the `includeFiles` brace list. It must be present or the deployed lambda raises `ModuleNotFoundError` at import and the health email stops entirely.

- [ ] **Step 6: Implement `collect_claims` and stamp it**

Add to `nightly_pipeline.py`:

```python
def collect_claims(store) -> dict:
    """Max date per artifact in the LOCAL store, as of end of run.

    Never raises: a claims failure must not lose the run record that carries
    the stage outcomes, which is the more valuable half.
    """
    sys.path.insert(0, str(ROOT / "web"))
    try:
        from artifact_checks import ARTIFACT_CHECKS
    except Exception as e:  # noqa: BLE001
        print(f"run record: claims unavailable ({type(e).__name__}: {e})",
              flush=True)
        return {}

    claims = {}
    for label, sql, _ in ARTIFACT_CHECKS:
        try:
            row = store.conn.execute(sql).fetchone()
            claims[label] = row[0] if row else None
        except Exception as e:  # noqa: BLE001
            print(f"run record: claim {label} failed ({type(e).__name__})",
                  flush=True)
    return claims
```

The test's `FakeStore.execute` returns a list, so use `fetchone()` only if the real sqlite cursor supports it — it does; adjust the fake in the test to return an object with `fetchone()` if the shapes disagree. Keep the production code idiomatic for `sqlite3` and make the fake match it, not the reverse.

Then in `main()`, pass `claims=collect_claims(store)` into the finish `record_run` call.

- [ ] **Step 7: Run tests and commit**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_pipeline.py` and `.../scripts/test_web_api.py`
Expected: all pass.

```bash
git add web/artifact_checks.py web/vercel.json web/api/health_report.py nightly_pipeline.py scripts/test_nightly_pipeline.py scripts/test_web_api.py
git commit -m "Shared artifact-check list; run record stamps local claims"
```

---

### Task 4: Push the run record to Turso, after publish, with catch-up

**Files:**
- Modify: `nightly_pipeline.py`
- Test: `scripts/test_nightly_pipeline.py` (extend)

**Interfaces:**
- Consumes: `get_nightly_runs`/`upsert_nightly_run` from Task 1, `main()` from Tasks 2-3.
- Produces: `push_runs(local_store, remote_store, *, limit: int = 30) -> int` returning the number of rows pushed. Never raises.

**Ordering is the whole design.** This runs **after** the publish stage, as its own step, so it observes publish rather than depending on it. Putting the record inside the sync leg would mean a publish failure eats the record of the publish failure — the exact bug this plan exists to kill.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_nightly_pipeline.py`, above `def main()`:

```python
class _FakeRemote:
    """Minimal store double: records upserts, answers get_nightly_runs."""

    def __init__(self, existing=None, explode=False):
        self.rows = dict(existing or {})
        self.explode = explode

    def upsert_nightly_run(self, **kw):
        if self.explode:
            raise RuntimeError("turso down")
        self.rows[kw["run_id"]] = kw

    def get_nightly_runs(self, *, limit=10, started_after=None):
        rows = sorted(self.rows.values(), key=lambda r: r["started_at"],
                      reverse=True)
        if started_after:
            rows = [r for r in rows if r["started_at"] > started_after]
        return rows[:limit]


class _FakeLocal(_FakeRemote):
    pass


@test("push_runs sends only rows newer than the remote high-water mark")
def _():
    local = _FakeLocal()
    for n, ts in [("a", "2026-08-27T09:30:00Z"), ("b", "2026-08-28T09:30:00Z"),
                  ("c", "2026-08-29T09:30:00Z")]:
        local.upsert_nightly_run(run_id=n, host="laptop", started_at=ts,
                                 lab_date=ts[:10], status="ok")
    remote = _FakeRemote()
    remote.upsert_nightly_run(run_id="a", host="laptop",
                              started_at="2026-08-27T09:30:00Z",
                              lab_date="2026-08-27", status="ok")
    pushed = np.push_runs(local, remote)
    assert pushed == 2, pushed
    assert set(remote.rows) == {"a", "b", "c"}, remote.rows


@test("push_runs backfills every run when the remote is empty")
def _():
    local = _FakeLocal()
    for n, ts in [("a", "2026-08-27T09:30:00Z"), ("b", "2026-08-28T09:30:00Z")]:
        local.upsert_nightly_run(run_id=n, host="laptop", started_at=ts,
                                 lab_date=ts[:10], status="ok")
    remote = _FakeRemote()
    assert np.push_runs(local, remote) == 2
    assert set(remote.rows) == {"a", "b"}


@test("push_runs is a no-op when the remote is already current")
def _():
    local = _FakeLocal()
    local.upsert_nightly_run(run_id="a", host="laptop",
                             started_at="2026-08-27T09:30:00Z",
                             lab_date="2026-08-27", status="ok")
    remote = _FakeRemote(existing={"a": {"run_id": "a", "host": "laptop",
                                         "started_at": "2026-08-27T09:30:00Z",
                                         "lab_date": "2026-08-27",
                                         "status": "ok"}})
    assert np.push_runs(local, remote) == 0


@test("push_runs never raises when the remote is down")
def _():
    local = _FakeLocal()
    local.upsert_nightly_run(run_id="a", host="laptop",
                             started_at="2026-08-27T09:30:00Z",
                             lab_date="2026-08-27", status="ok")
    assert np.push_runs(local, _FakeRemote(explode=True)) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_pipeline.py`
Expected: the four new cases fail with `AttributeError: ... 'push_runs'`.

- [ ] **Step 3: Implement `push_runs`**

Add to `nightly_pipeline.py`:

```python
def push_runs(local_store, remote_store, *, limit: int = 30) -> int:
    """Publish local run records Turso has not seen. Returns rows pushed.

    Stateless catch-up, deliberately: read the remote high-water mark and
    send everything local holds after it. No `pushed_at` column to keep in
    sync, no local mutation, and a machine that was offline for days heals on
    its next run — the same self-healing shape as migrate()'s dedupe.

    This runs AFTER the publish stage, as its own step, so it observes
    publish rather than depending on it. A record that travelled inside the
    sync leg would be eaten by exactly the publish failure it needs to
    report, which is the failure shape this whole plan exists to kill.

    Never raises: see record_run.
    """
    try:
        newest = remote_store.get_nightly_runs(limit=1)
        high_water = newest[0]["started_at"] if newest else None
        pending = local_store.get_nightly_runs(limit=limit,
                                               started_after=high_water)
    except Exception as e:  # noqa: BLE001
        print(f"run record: push skipped ({type(e).__name__}: {e})", flush=True)
        return 0

    pushed = 0
    for row in sorted(pending, key=lambda r: r["started_at"]):
        try:
            remote_store.upsert_nightly_run(
                run_id=row["run_id"], host=row["host"],
                started_at=row["started_at"], lab_date=row["lab_date"],
                status=row["status"], finished_at=row.get("finished_at"),
                stages=row.get("stages"), claims=row.get("claims"),
                exit_code=row.get("exit_code"))
            pushed += 1
        except Exception as e:  # noqa: BLE001
            print(f"run record: push of {row['run_id']} failed "
                  f"({type(e).__name__}: {e})", flush=True)
            break  # remote is unhealthy; the next run retries the whole tail
    return pushed
```

- [ ] **Step 4: Call it from `main()`**

After the finish `record_run` call and before `store.close()`:

```python
    # Own step, after publish (see push_runs' docstring). Opened lazily so a
    # machine with no Turso credentials still completes its local run record.
    try:
        from store import get_store as _get_store
        remote = _get_store("turso")
        try:
            n = push_runs(store, remote)
            print(f"run record: pushed {n} run(s) to Turso", flush=True)
        finally:
            remote.close()
    except Exception as e:  # noqa: BLE001
        print(f"run record: remote unavailable ({type(e).__name__}: {e})",
              flush=True)
```

- [ ] **Step 5: Run tests and commit**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_pipeline.py`
Expected: all pass.

```bash
git add nightly_pipeline.py scripts/test_nightly_pipeline.py
git commit -m "Push run records to Turso after publish, with stateless catch-up"
```

---

### Task 5: Health email reads the run record and cross-checks it

**Files:**
- Modify: `web/api/health_report.py`
- Test: `scripts/test_web_api.py` (extend)

**Interfaces:**
- Consumes: the `nightly_runs` table in Turso (Task 1), `claims` written by Task 3, rows pushed by Task 4.
- Produces:
  - `_check_nightly_run() -> dict | None` — `{"lab_date", "host", "status", "age_days", "ok", "stages", "mismatches", "note"}`, or `None` when the table is unreadable.
  - `_compose(...)` gains a `nightly_run=None` keyword.

**The doctrine this must not break.** The run record is a **self-report** — the side-channel claim #45 forbids. It is added as a second axis, never as a replacement: every existing `max(date)` heartbeat stays exactly as it is. A reviewer should reject any diff that removes or weakens an entry in `HEARTBEATS`.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_web_api.py`, matching the file's existing conventions and using its `_health_mod(up=, hb=, ur=)` stub. Read how that stub dispatches on SQL before writing — the nightly-run query must be separately observable from the pause lookup, the freshness lookups and the uptime upsert, exactly as those three already are.

Cases to assert:

```python
# 1. A fresh, all-ok run renders one line and grades ok.
# 2. A run whose stages contain a failure grades not-ok and names the stage.
# 3. A run older than 2 lab days grades not-ok as "host has been off".
# 4. No rows at all -> ok is False with "never produced", NOT fresh.
# 5. The query raising -> ok is None ("could not check"), never True.
#    This mirrors _check_heartbeats: freshness must fail LOUD, unlike the
#    pause lookup which deliberately fails open.
# 6. Cross-check: a claim NEWER than the matching Turso artifact produces a
#    mismatch naming the artifact, the claimed date and the remote date.
# 7. Cross-check: claim equal to or older than the remote value -> no
#    mismatch (the remote may legitimately be ahead after a later sync).
# 8. The existing HEARTBEATS list is unchanged in length and content by this
#    task — a regression guard, because replacing artifact checks with the
#    self-report is the specific mistake this design rejects.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`
Expected: the new cases fail on the missing `_check_nightly_run`.

- [ ] **Step 3: Implement `_check_nightly_run`**

Add to `web/api/health_report.py`, next to `_check_heartbeats`:

```python
# Max age in LAB DAYS for the nightly run itself. 2 matches the artifact
# thresholds: one missed night is quiet (a closed lid is normal and was
# accepted when the jobs moved to the laptop), two is a breach.
NIGHTLY_RUN_MAX_AGE_DAYS = 2


def _check_nightly_run(heartbeats=None):
    """The newest nightly pipeline run, graded and cross-checked.

    A SECOND AXIS, not a replacement. The artifact heartbeats above ask "did
    the output appear"; this asks "did the job run, and what did it say
    happened". Both are needed: a run record is a self-report, and #45 exists
    because self-reports are exactly what failed in all six incidents. Keep
    HEARTBEATS intact.

    Graded on `lab_date` — the day the run STARTED — never on arrival time.
    A catch-up push sends several days of backlog at once, and grading on
    arrival would make three dead nights look like they all happened at 2am
    today, silently undoing the mechanism.

    Fails loud (ok=None) when unreadable, like _check_heartbeats and unlike
    the pause lookup.
    """
    entry = {"lab_date": None, "host": None, "status": None,
             "age_days": None, "ok": None, "stages": [], "mismatches": [],
             "note": ""}
    try:
        rows = turso_query(
            "SELECT run_id, host, started_at, lab_date, finished_at, status, "
            "stages, claims, exit_code FROM nightly_runs "
            "ORDER BY started_at DESC LIMIT 1")
    except Exception as e:
        entry["note"] = f"could not check ({type(e).__name__})"
        print(f"health_report: nightly run unreadable: {e}"[:200])
        return entry

    if not rows:
        entry["ok"] = False
        entry["note"] = "no rows — never produced"
        return entry

    row = rows[0]
    entry["host"] = row.get("host")
    entry["status"] = row.get("status")
    entry["lab_date"] = str(row.get("lab_date") or "")[:10]
    try:
        last = datetime.strptime(entry["lab_date"], "%Y-%m-%d").date()
    except ValueError:
        entry["ok"] = False
        entry["note"] = f"unparseable lab_date {entry['lab_date']!r}"
        return entry

    entry["age_days"] = (lab_today() - last).days
    if entry["age_days"] > NIGHTLY_RUN_MAX_AGE_DAYS:
        entry["ok"] = False
        entry["note"] = (f"no run for {entry['age_days']} days — "
                         "host has been off")
        return entry

    try:
        stages = json.loads(row.get("stages") or "[]")
    except (TypeError, ValueError):
        stages = []
    entry["stages"] = stages
    bad = [s for s in stages
           if s.get("outcome") in ("failed", "timeout", "skipped")]
    if row.get("status") == "running":
        entry["ok"] = False
        entry["note"] = "started but never finished — died mid-run"
        return entry
    if bad:
        entry["ok"] = False
        entry["note"] = ", ".join(
            f"{s['name']}: {s['outcome']}" for s in bad)
        return entry

    entry["ok"] = True
    return entry
```

- [ ] **Step 4: Implement the claims cross-check**

Add, and call it from `_check_nightly_run` just before the final `entry["ok"] = True` (populating `entry["mismatches"]`; a non-empty list sets `ok` False with a note naming the artifacts):

```python
def _claims_vs_remote(claims, heartbeats):
    """Artifacts the run says it produced that Turso does not have.

    This is what makes the sync leg checkable. Without it, "local has it and
    the cloud does not" is indistinguishable from "the job never produced
    it" — different bugs with different fixes, and the health email has never
    been able to tell them apart.

    Only a claim STRICTLY NEWER than the remote value is a mismatch: the
    remote being ahead is normal after a later sync from another source, and
    flagging it would make the check cry wolf.
    """
    by_name = {h["name"]: h for h in heartbeats}
    out = []
    for label, claimed in (claims or {}).items():
        remote = (by_name.get(label) or {}).get("last")
        if claimed and remote and str(claimed) > str(remote):
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": str(remote)})
        elif claimed and not remote:
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": None})
    return out
```

Wire it: `_check_nightly_run` takes an optional `heartbeats=None` argument, decodes `row["claims"]`, and sets `entry["mismatches"] = _claims_vs_remote(claims, heartbeats or [])`. In the handler, call `_check_heartbeats()` first and pass its result in — the mismatch is a comparison between the two, so the order matters.

- [ ] **Step 5: Render it in the email**

In `_compose`, add a `nightly_run=None` keyword and one line in both the text and HTML bodies, placed directly under the heartbeats block:

- all ok → `nightly run: 2026-08-30 ok on laptop — 5 stages` (green in HTML)
- not ok → red, with `note`, then one indented line per failed stage, then one line per mismatch: `review email: run claimed 2026-08-29, Turso has 2026-08-27 — publish is dropping rows`
- `ok is None` → the same "could not check" treatment the heartbeats already get

Pass `nightly_run=_check_nightly_run(heartbeats)` from the handler, and add its state to the JSON response next to `"stale"`.

- [ ] **Step 6: Run tests and commit**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_web_api.py`
Expected: all pass, including the ~162 pre-existing cases.

```bash
git add web/api/health_report.py scripts/test_web_api.py
git commit -m "Health email cross-checks the nightly run record against artifacts"
```

---

### Task 6: Never destroy a paid artifact

**Files:**
- Modify: `store/sqlite_store.py` (two archive tables, `prompt_version` on two live tables, `_ARCHIVE_SPEC` + `_archive_row`, both upserts)
- Modify: `store/turso_store.py` (`prompt_version` column on `daily_summaries` and `weekly_rollups` + the matching keyword on both upserts, so the sync leg keeps working — **no archive tables here**)
- Modify: `store/base.py` (the `prompt_version` keyword on the two abstract upserts, plus a docstring note that they archive before replacing)
- Modify: `sync_to_turso.py` (carry `prompt_version` through the two summary legs if they enumerate columns explicitly — read them and check)
- Modify: `synthesizer.py` (pass `prompt_version`)
- Modify: `scripts/regroup_weekly_rollups.py` (archive before delete)
- Test: `scripts/test_paid_artifacts.py` (create)

**Interfaces:**
- Consumes: nothing from Tasks 1-5 — this is independent and could ship alone.
- Produces:
  - `daily_summaries_superseded` and `weekly_rollups_superseded` tables (LOCAL ONLY — no Turso counterpart, no sync leg; superseded rows are history, and no reader needs them).
  - `upsert_daily_summary` and `upsert_weekly_rollup` gain an optional `prompt_version: str | None = None` keyword and archive-before-overwrite behaviour.
  - `synthesizer.prompt_version(system: str, tool: dict) -> str` — a stable 12-char hex digest.

**Why:** `daily_summaries` has `UNIQUE(project, date)` and the upsert does `INSERT OR REPLACE`, so re-running a day silently replaces prose that cost an API call. `weekly_rollups` is the same shape, and the 2026-08-10 week-grouping repair deleted 207 rollups outright — recoverable only because a DB backup happened to exist.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_paid_artifacts.py` with the same harness shape as Task 1's file. Cases:

```python
# 1. Overwriting a daily summary moves the OLD prose into
#    daily_summaries_superseded, and the live row holds the new prose.
# 2. Re-writing IDENTICAL content archives nothing (no churn on a re-run
#    that changed nothing).
# 3. Two successive overwrites leave TWO superseded rows, in order — the
#    archive is append-only history, not a single previous-value slot.
# 4. Inserting a summary for a (project, date) that has none archives
#    nothing.
# 5. The same four cases for upsert_weekly_rollup / weekly_rollups_superseded.
# 6. prompt_version round-trips onto the live row.
# 7. synthesizer.prompt_version is stable for identical input and differs
#    when the system prompt OR the tool schema changes.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_paid_artifacts.py`
Expected: fails on the missing table.

- [ ] **Step 3: Add the archive tables and the guard**

In `store/sqlite_store.py`'s `migrate()` `executescript` block:

```sql
            -- Append-only history of paid prose that an upsert replaced.
            -- LOCAL ONLY: never synced, no reader needs it, and it must not
            -- grow a sync leg. These rows cost real API calls; an upsert
            -- that overwrote them in place is how a re-run silently
            -- destroyed a night's work (nightly-pipeline-plan step 5).
            CREATE TABLE IF NOT EXISTS daily_summaries_superseded (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                date TEXT NOT NULL,
                summary TEXT NOT NULL,
                key_decisions TEXT,
                model TEXT,
                prompt_version TEXT,
                original_created_at TEXT,
                superseded_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS weekly_rollups_superseded (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                week_start TEXT NOT NULL,
                narrative TEXT NOT NULL,
                highlights TEXT,
                model TEXT,
                prompt_version TEXT,
                original_created_at TEXT,
                superseded_at TEXT DEFAULT (datetime('now'))
            );
```

Add `prompt_version TEXT` to the live `daily_summaries` and `weekly_rollups` tables. Because both tables already exist on real machines, `CREATE TABLE IF NOT EXISTS` will not add the column — follow the defensive `PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN` pattern already used at the top of `migrate()` for `api_costs`, and make it a no-op when the column is present so `migrate()` stays safe to call on every run.

Then add the archiving helper and use it in both upserts:

```python
    # Columns copied to the archive, per live table. The archive keeps the
    # prose, what produced it, and when — not the counts, which are cheap to
    # recompute and are not what the API call was spent on.
    _ARCHIVE_SPEC = {
        "daily_summaries": ("daily_summaries_superseded",
                            ("project", "date"), "summary",
                            ("project", "date", "summary", "key_decisions",
                             "model", "prompt_version")),
        "weekly_rollups": ("weekly_rollups_superseded",
                           ("project", "week_start"), "narrative",
                           ("project", "week_start", "narrative", "highlights",
                            "model", "prompt_version")),
    }

    def _archive_row(self, table, existing, new_content):
        """Copy `existing` into <table>_superseded when the incoming write
        carries DIFFERENT content.

        Identical content archives nothing — the nightly pipeline re-runs days
        routinely, and a re-run that changed nothing should not churn history.
        Called inside the caller's transaction, so the archive and the replace
        commit together or not at all.
        """
        archive, _key_cols, content_col, cols = self._ARCHIVE_SPEC[table]
        if existing is None or existing[content_col] == new_content:
            return
        placeholders = ", ".join("?" * (len(cols) + 1))
        self._conn.execute(
            f"INSERT INTO {archive} ({', '.join(cols)}, original_created_at) "
            f"VALUES ({placeholders})",
            tuple(existing[c] for c in cols) + (existing["created_at"],))
```

The table and column names interpolated into that SQL come only from
`_ARCHIVE_SPEC`, a module constant — never from an argument a caller controls.
Keep it that way; values stay bound.

Call them from both upserts. `upsert_daily_summary` becomes:

```python
    def upsert_daily_summary(self, *, project, date, summary, key_decisions,
                             prompt_count, session_count, commit_count, model,
                             prompt_version=None):
        # Archive first, in the same transaction: this prose cost an API call,
        # and INSERT OR REPLACE would drop it on the floor (step 5).
        existing = self._conn.execute(
            "SELECT * FROM daily_summaries WHERE project = ? AND date = ?",
            (project, date)).fetchone()
        self._archive_row("daily_summaries", existing, summary)
        self._conn.execute("""
            INSERT OR REPLACE INTO daily_summaries
                (project, date, summary, key_decisions, prompt_count,
                 session_count, commit_count, model, prompt_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, date, summary, json.dumps(key_decisions),
              prompt_count, session_count, commit_count, model,
              prompt_version))
        self._conn.commit()
```

Apply the same shape to `upsert_weekly_rollup`, keyed on `(project, week_start)` with `narrative` as the content column. Delete the vestigial `_archive_if_replacing` above — `_archive_row` plus the caller's own SELECT is the whole mechanism, and a helper that half-does the lookup is worse than none. (The `_ARCHIVE_SPEC` table and `_archive_row` are what you keep.)

Note `INSERT OR REPLACE` deletes and re-inserts, so the live row's `created_at` resets on every overwrite. That is why `original_created_at` is captured into the archive from the row being replaced: it is the only surviving record of when that prose was first produced.

**Both backends?** No — `store/turso_store.py` gains only the `prompt_version` column on its two tables and the matching keyword on the two upserts, so the sync leg keeps working. It gets **no** archive tables: superseded prose is local history and must not gain a sync leg.

- [ ] **Step 4: Add `prompt_version` in the synthesizer**

```python
def prompt_version(system: str, tool: dict) -> str:
    """Stable digest of the prompt that produced an artifact.

    `model` alone does not identify a vintage: these prompts get iterated, and
    without this an old row is indistinguishable from a new one produced by
    different instructions.
    """
    payload = json.dumps({"system": system, "tool": tool}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]
```

Pass it at all three `call_claude` sites that write an artifact (daily, weekly, project state — the project-state one writes a snapshot, so pass it only where the store method accepts it).

- [ ] **Step 5: Make the repair script archive rather than delete**

Read `scripts/regroup_weekly_rollups.py`. Every `DELETE FROM weekly_rollups` must first copy the doomed rows into `weekly_rollups_superseded`. Keep the dry-run default and the `--apply` gate exactly as they are; do not change what the script decides to repair, only what it destroys.

- [ ] **Step 6: Run tests and commit**

Run: `/Users/nico/src/prompt-lab/.venv/bin/python scripts/test_paid_artifacts.py`
Then the full suite.

```bash
git add store/sqlite_store.py store/base.py synthesizer.py scripts/regroup_weekly_rollups.py scripts/test_paid_artifacts.py
git commit -m "Archive paid prose before an upsert or repair destroys it"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md` (Invariants section, Next Steps)
- Modify: `docs/nightly-pipeline-plan.md` (mark steps 3 and 5 done)

- [ ] **Step 1: Add the invariant**

In `CLAUDE.md` under "Invariants", after the cloud-direct bullet:

```markdown
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
```

- [ ] **Step 2: Update Next Steps and the plan doc**

Rewrite the nightly-pipeline paragraph in `CLAUDE.md`'s Next Steps to say steps 3 and 5 are done, name the acceptance tests that still need a real overnight (step 2's sleeping-host test and step 3's blocked-push test), and drop the "open design question: cloud-direct vs synced" line — it is decided. Mark steps 3 and 5 DONE in `docs/nightly-pipeline-plan.md`'s status header.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/nightly-pipeline-plan.md
git commit -m "Document the run-record invariants and mark steps 3 and 5 done"
```
