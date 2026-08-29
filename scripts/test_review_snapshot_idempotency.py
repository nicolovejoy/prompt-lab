"""Tests for nightly-pipeline-plan step 1: idempotent review_snapshot writes.

TursoKnowledgeStore.save_review_snapshot was a plain INSERT, so the nightly
sync re-pushed the same local rows every night — 11,848 Turso rows for 78 real
(review_type, date) pairs by 2026-08-29. Now migrate() dedupes (newest id per
pair survives), adds a unique index, and save_review_snapshot upserts without
touching created_at on replay.

The store's real SQL is executed against an in-memory sqlite via a _pipeline
double — same dialect Turso speaks — so these assert on end state, not on
string-matching the statements.

Run: .venv/bin/python scripts/test_review_snapshot_idempotency.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from store.turso_store import TursoKnowledgeStore  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def test(name: str):
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


# Production-shaped legacy table: what Turso actually held before this change
# (no unique index — CREATE TABLE IF NOT EXISTS in migrate() never adds one
# to an existing table).
LEGACY_SCHEMA = """
    CREATE TABLE review_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        review_type TEXT NOT NULL,
        date TEXT NOT NULL,
        subject TEXT,
        content_html TEXT,
        content_text TEXT,
        content_markdown TEXT,
        model TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    )
"""


def make_store(db: sqlite3.Connection) -> TursoKnowledgeStore:
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


def seed_duplicated_table(db: sqlite3.Connection) -> None:
    db.execute(LEGACY_SCHEMA)
    # Three pairs; "daily"/2026-08-01 pushed three times, weekly twice.
    rows = [
        ("daily", "2026-08-01", "old subject", "first push"),
        ("daily", "2026-08-01", "old subject", "second push"),
        ("daily", "2026-08-01", "newest subject", "third push"),
        ("weekly", "2026-08-03", "wk", "first push"),
        ("weekly", "2026-08-03", "wk", "second push"),
        ("daily", "2026-08-02", "solo", "only push"),
    ]
    for rt, d, subj, txt in rows:
        db.execute(
            "INSERT INTO review_snapshots (review_type, date, subject, content_text, model)"
            " VALUES (?, ?, ?, ?, 'm')",
            (rt, d, subj, txt),
        )
    db.commit()


@test("migrate dedupes a legacy table down to one row per (review_type, date)")
def _():
    db = sqlite3.connect(":memory:")
    seed_duplicated_table(db)
    make_store(db).migrate()
    n = db.execute("SELECT COUNT(*) FROM review_snapshots").fetchone()[0]
    assert n == 3, f"expected 3 rows after dedupe, got {n}"


@test("migrate keeps the newest copy of each duplicated pair")
def _():
    db = sqlite3.connect(":memory:")
    seed_duplicated_table(db)
    make_store(db).migrate()
    subj, txt = db.execute(
        "SELECT subject, content_text FROM review_snapshots"
        " WHERE review_type='daily' AND date='2026-08-01'"
    ).fetchone()
    assert (subj, txt) == ("newest subject", "third push"), f"kept wrong row: {subj!r}/{txt!r}"


@test("migrate leaves the unique index in place so duplicates cannot re-form")
def _():
    db = sqlite3.connect(":memory:")
    seed_duplicated_table(db)
    make_store(db).migrate()
    try:
        db.execute(
            "INSERT INTO review_snapshots (review_type, date, model)"
            " VALUES ('daily', '2026-08-01', 'm')"
        )
    except sqlite3.IntegrityError:
        return
    raise AssertionError("plain INSERT of an existing pair should violate the unique index")


@test("migrate is a no-op on an already-clean table (safe to run every sync)")
def _():
    db = sqlite3.connect(":memory:")
    seed_duplicated_table(db)
    store = make_store(db)
    store.migrate()
    before = db.execute(
        "SELECT id, subject FROM review_snapshots ORDER BY id"
    ).fetchall()
    store.migrate()
    after = db.execute(
        "SELECT id, subject FROM review_snapshots ORDER BY id"
    ).fetchall()
    assert before == after, "second migrate changed rows"


@test("save_review_snapshot replayed with same key yields one row, newest content")
def _():
    db = sqlite3.connect(":memory:")
    store = make_store(db)
    store.migrate()
    for subject in ("first", "second"):
        store.save_review_snapshot(
            review_type="daily", date="2026-08-29", subject=subject,
            content_text=subject, model="m", input_tokens=1, output_tokens=2,
        )
    rows = db.execute(
        "SELECT subject, content_text FROM review_snapshots"
    ).fetchall()
    assert rows == [("second", "second")], f"expected single updated row, got {rows}"


@test("replay does not bump created_at (history keeps first-arrival order)")
def _():
    db = sqlite3.connect(":memory:")
    store = make_store(db)
    store.migrate()
    store.save_review_snapshot(
        review_type="daily", date="2026-08-29", subject="a",
        model="m", input_tokens=0, output_tokens=0,
    )
    db.execute("UPDATE review_snapshots SET created_at='SENTINEL'")
    db.commit()
    store.save_review_snapshot(
        review_type="daily", date="2026-08-29", subject="b",
        model="m", input_tokens=0, output_tokens=0,
    )
    created, subj = db.execute(
        "SELECT created_at, subject FROM review_snapshots"
    ).fetchone()
    assert subj == "b", "content should update on replay"
    assert created == "SENTINEL", f"created_at was rewritten to {created!r}"


@test("different (review_type, date) pairs still coexist")
def _():
    db = sqlite3.connect(":memory:")
    store = make_store(db)
    store.migrate()
    for rt, d in (("daily", "2026-08-28"), ("daily", "2026-08-29"),
                  ("weekly", "2026-08-29")):
        store.save_review_snapshot(review_type=rt, date=d, subject="s",
                                   model="m", input_tokens=0, output_tokens=0)
    n = db.execute("SELECT COUNT(*) FROM review_snapshots").fetchone()[0]
    assert n == 3, f"expected 3 distinct rows, got {n}"


def main() -> int:
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
