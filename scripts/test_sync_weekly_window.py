"""The weekly-rollup sync leg selects by WHEN THE ROW WAS WRITTEN, not by
week_start.

Found 2026-10-27: `sync_to_turso.py --days 7` filtered weekly_rollups by
`week_start >= today - 7d`. A week's rollup is written after the week ends,
so its week_start is already outside a 7-day window on every night except
the one Sunday where the two dates coincide. The publish log showed exactly
that: rows synced on 10-05, 10-12, 10-19 and "0 rows (skip)" every other
night, and the week of 10-19 (eight rollups written 10-27) could never reach
Turso. Local INSERT OR REPLACE resets created_at, so created_at is the
write time and is the right key.

Run: .venv/bin/python scripts/test_sync_weekly_window.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sync_to_turso  # noqa: E402

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


class _FakeLocalStore:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_weekly_rollups(self, *, project=None, since=None, limit=None):
        self.calls.append(since)
        if since:
            return [r for r in self._rows if r["week_start"] >= since]
        return list(self._rows)


ROWS = [
    # Week two Mondays back, rolled up this morning (the 10-27 shape).
    {"project": "a", "week_start": "2026-10-19", "created_at": "2026-10-27 09:35:30"},
    # Same week, rolled up when it first became complete, a week ago.
    {"project": "b", "week_start": "2026-10-19", "created_at": "2026-10-26 09:33:00"},
    # An old week whose rollup was (re)written this week: a catch-up or a
    # /handoff-full refresh. Must sync too.
    {"project": "c", "week_start": "2026-09-07", "created_at": "2026-10-25 14:11:05"},
    # Old and untouched.
    {"project": "d", "week_start": "2026-10-12", "created_at": "2026-10-19 09:30:00"},
    # Legacy row with no write time: nothing says it changed, leave it.
    {"project": "e", "week_start": "2026-10-12", "created_at": None},
]


@test("window: a rollup written inside the window syncs whatever its week_start")
def _():
    got = sync_to_turso.recent_weekly_rollups(_FakeLocalStore(ROWS), since="2026-10-20")
    assert [r["project"] for r in got] == ["a", "b", "c"], got


@test("window: the 10-27 shape — week_start before `since`, written after it")
def _():
    # Tonight's since was 2026-10-20 and week_start 2026-10-19 < since, which
    # is exactly the row the old week_start filter dropped.
    got = sync_to_turso.recent_weekly_rollups(_FakeLocalStore(ROWS[:1]), since="2026-10-20")
    assert len(got) == 1, got


@test("window: no `since` means a full sync of every row")
def _():
    store = _FakeLocalStore(ROWS)
    got = sync_to_turso.recent_weekly_rollups(store, since=None)
    assert len(got) == len(ROWS), got
    assert store.calls == [None], store.calls


@test("window: the local query is never narrowed by week_start")
def _():
    store = _FakeLocalStore(ROWS)
    sync_to_turso.recent_weekly_rollups(store, since="2026-10-20")
    assert store.calls == [None], store.calls


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += not ok
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
