"""Tests for the nightly_runs table and its store methods
(nightly-pipeline-plan step 3).

The Turso store's real SQL is exercised against in-memory sqlite — the same
technique as scripts/test_review_snapshot_idempotency.py — so the upsert
semantics that matter in production are asserted here without a network call.

Run: /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_nightly_runs.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402
from store.turso_store import TursoKnowledgeStore  # noqa: E402

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


# ---- Turso store's real SQL, replayed against in-memory sqlite ----
# Same technique as scripts/test_review_snapshot_idempotency.py: a fake
# _pipeline executes the store's actual statements against a real sqlite
# connection, so the upsert semantics are asserted without a network call.

def make_turso_store(db: sqlite3.Connection) -> TursoKnowledgeStore:
    store = TursoKnowledgeStore(url="https://test.invalid", token="t")

    def fake_pipeline(stmts):
        results = []
        for s in stmts:
            args = [a["value"] for a in s.get("args") or []]
            cur = db.execute(s["sql"], args)
            cols = [{"name": d[0]} for d in cur.description or []]
            rows = [[{"value": v} for v in row] for row in cur.fetchall()]
            results.append({"cols": cols, "rows": rows})
        db.commit()
        return results

    store._pipeline = fake_pipeline
    return store


@test("Turso upsert_nightly_run replayed with same run_id yields one row, newest status")
def _():
    db = sqlite3.connect(":memory:")
    store = make_turso_store(db)
    store.migrate()
    store.upsert_nightly_run(run_id="r1", host="laptop",
                             started_at="2026-08-30T09:30:04Z",
                             lab_date="2026-08-30", status="running")
    store.upsert_nightly_run(run_id="r1", host="laptop",
                             started_at="2026-08-30T09:30:04Z",
                             lab_date="2026-08-30", status="ok")
    rows = db.execute("SELECT status FROM nightly_runs").fetchall()
    assert rows == [("ok",)], f"expected single updated row, got {rows}"


def main():
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
