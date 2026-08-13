"""Regression tests for the review email's "Today" window (the 2:30am bug).

Run: .venv/bin/python scripts/test_send_review.py

The nightly review fires at 2:30am and used to ask for *today's* data —
structurally empty, since a day's summaries are written at the end of that
day — and picked sessions by `started_at` in a rolling UTC day, so a long
session was invisible to the day it actually worked (raconte ran 31 hours
across Aug 10-11 and never appeared in an Aug 11 "today").

Pinned here:
- "Today" means yesterday's completed lab-day (Pacific), never the run date.
- Sessions are selected by *overlap* with that day's UTC bounds, not by
  started_at, and an unfinished session (ended_at NULL) still counts.
- The Pacific-day → UTC bounds conversion is DST-correct.

No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from day_helper import lab_today  # noqa: E402
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

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


def _load_send_review():
    spec = importlib.util.spec_from_file_location("send_review", ROOT / "send-review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_store_with_sessions(rows):
    """In-memory store with a hand-made sessions table (the hook owns its DDL)."""
    store = SqliteKnowledgeStore(":memory:")
    store.migrate()
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, project TEXT, started_at TEXT,
            ended_at TEXT, summary TEXT, utility INTEGER, hostname TEXT
        )
    """)
    store._conn.executemany(
        "INSERT INTO sessions (id, project, started_at, ended_at, summary, hostname)"
        " VALUES (?, ?, ?, ?, ?, 'testhost')", rows)
    store._conn.commit()
    return store


@test("clocks: lab_day_bounds_utc is DST-correct (PDT summer, PST winter)")
def _():
    from day_helper import lab_day_bounds_utc
    assert lab_day_bounds_utc("2026-08-11") == ("2026-08-11 07:00:00", "2026-08-12 07:00:00"), \
        f"summer bounds wrong: {lab_day_bounds_utc('2026-08-11')}"
    assert lab_day_bounds_utc("2026-01-15") == ("2026-01-15 08:00:00", "2026-01-16 08:00:00"), \
        f"winter bounds wrong: {lab_day_bounds_utc('2026-01-15')}"


@test("sessions are selected by overlap with the day, not by started_at")
def _():
    # Lab-day 2026-08-11 = UTC [2026-08-11 07:00, 2026-08-12 07:00)
    store = _mem_store_with_sessions([
        # the raconte case: 31h session spanning into the day — must count
        ("s1", "raconte", "2026-08-10 16:03:00", "2026-08-11 22:51:00", "long session"),
        # entirely before the day — must not count
        ("s2", "oldwork", "2026-08-09 12:00:00", "2026-08-09 13:00:00", "done earlier"),
        # started inside the day, still running (ended_at NULL) — must count
        ("s3", "ongoing", "2026-08-11 20:00:00", None, "in flight"),
        # started after the day ended — must not count
        ("s4", "tomorrow", "2026-08-12 08:00:00", "2026-08-12 09:00:00", "next day"),
        # overlaps but never summarized — excluded (nothing to narrate)
        ("s5", "silent", "2026-08-11 10:00:00", "2026-08-11 11:00:00", None),
    ])
    got = store.get_raw_sessions(
        overlap_utc=("2026-08-11 07:00:00", "2026-08-12 07:00:00"))
    projects = sorted(s["project"] for s in got)
    store.close()
    assert projects == ["ongoing", "raconte"], f"got {projects}"


@test("since_days selection still works unchanged")
def _():
    store = _mem_store_with_sessions([
        ("s1", "recent", "2099-01-01 00:00:00", "2099-01-01 01:00:00", "future = recent"),
        ("s2", "ancient", "2000-01-01 00:00:00", "2000-01-01 01:00:00", "old"),
    ])
    got = store.get_raw_sessions(since_days=1)
    store.close()
    assert [s["project"] for s in got] == ["recent"], f"got {got}"


@test("review window: 'today' is yesterday's completed lab-day, week reaches 7 back")
def _():
    mod = _load_send_review()
    w = mod.review_windows()
    yesterday = (lab_today() - timedelta(days=1)).isoformat()
    week_since = (lab_today() - timedelta(days=7)).isoformat()
    assert w["review_day"] == yesterday, f"review_day={w['review_day']}, want {yesterday}"
    assert w["week_since"] == week_since, f"week_since={w['week_since']}, want {week_since}"
    # bounds must be the UTC window of that lab-day, start < end
    assert w["day_start_utc"] < w["day_end_utc"]
    assert w["day_start_utc"].startswith(w["review_day"]), \
        f"day_start_utc {w['day_start_utc']} not on review_day"


@test("send-review no longer queries daily summaries with the run date")
def _():
    src = (ROOT / "send-review.py").read_text()
    assert "get_daily_summaries(since=today_str)" not in src, \
        "the 2:30am bug is back: daily summaries fetched with the run date"
    assert "get_raw_sessions(since_days=1)" not in src, \
        "daily sessions still selected by started_at in a rolling UTC day"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
