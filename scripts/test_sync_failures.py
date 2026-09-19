"""Tests for per-row sync failure collection and exit-1 on partial sync (#59).

Before this fix, sync_table and sync_daily_summaries printed a per-row
exception and moved on, and sync_to_turso.py always exited 0 — a partial
sync (some rows never landed in Turso) read as full success to the nightly
pipeline, which grades each stage purely on exit status. Now every swallowed
exception is also recorded in sync_to_turso._FAILURES, the row/part counts
printed are honest, and main() exits 1 when any failure was recorded.

Run: .venv/bin/python scripts/test_sync_failures.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
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

    def get_daily_summaries(self, *, since=None):
        return self._rows


class _FakeRemoteStore:
    """Minimal double for the surface sync_table / sync_daily_summaries call:
    _execute/_execute_many (monkeypatched for buffering) plus whatever
    upsert methods a given test's upsert_fn calls."""

    def __init__(self):
        self.parts: dict = {}
        self.daily: dict = {}

    def migrate(self):
        pass

    def _execute(self, sql, args=None):
        pass

    def _execute_many(self, statements):
        return []

    def upsert_daily_summary_part(self, *, project, date, machine, summary,
                                   key_decisions, prompt_count, session_count,
                                   commit_count, model):
        self.parts[(project, date, machine)] = {
            "project": project, "date": date, "machine": machine,
            "summary": summary, "key_decisions": key_decisions,
            "prompt_count": prompt_count, "session_count": session_count,
            "commit_count": commit_count, "model": model,
        }

    def get_daily_summary_parts(self, *, since, until):
        return [p for p in self.parts.values() if since <= p["date"] <= until]

    def upsert_daily_summary(self, *, project, date, summary, key_decisions,
                              prompt_count, session_count, commit_count, model):
        self.daily[(project, date)] = {"project": project, "date": date}


def _with_machine(label, fn):
    import os
    had = os.environ.get("GROUND_CONTROL_MACHINE")
    os.environ["GROUND_CONTROL_MACHINE"] = label
    try:
        return fn()
    finally:
        if had is None:
            os.environ.pop("GROUND_CONTROL_MACHINE", None)
        else:
            os.environ["GROUND_CONTROL_MACHINE"] = had


def _reset_failures():
    sync_to_turso._FAILURES = []


@test("sync_table: one of three rows fails — others still flush, one failure recorded, returns 2")
def _():
    _reset_failures()
    remote = _FakeRemoteStore()
    rows = [{"id": "a"}, {"id": "bad"}, {"id": "c"}]
    flushed = []

    def upsert_fn(r, row):
        if row["id"] == "bad":
            raise ValueError("boom")
        r._execute("INSERT ...", [row["id"]])
        flushed.append(row["id"])

    with redirect_stdout(io.StringIO()) as out:
        n = sync_to_turso.sync_table(
            _FakeLocalStore(rows), remote, "widgets",
            lambda s: rows, upsert_fn,
        )

    assert n == 2, f"expected 2 synced rows, got {n}"
    assert flushed == ["a", "c"], f"other rows should still have been flushed: {flushed}"
    assert len(sync_to_turso._FAILURES) == 1, sync_to_turso._FAILURES
    failure = sync_to_turso._FAILURES[0]
    assert "widgets" in failure and "bad" in failure and "ValueError" in failure, failure
    assert "2 rows synced, 1 failed" in out.getvalue(), out.getvalue()


@test("sync_table: clean run records no failures")
def _():
    _reset_failures()
    remote = _FakeRemoteStore()
    rows = [{"id": "a"}, {"id": "b"}]

    def upsert_fn(r, row):
        r._execute("INSERT ...", [row["id"]])

    with redirect_stdout(io.StringIO()) as out:
        n = sync_to_turso.sync_table(
            _FakeLocalStore(rows), remote, "widgets",
            lambda s: rows, upsert_fn,
        )

    assert n == 2, n
    assert sync_to_turso._FAILURES == [], sync_to_turso._FAILURES
    assert "2 rows synced" in out.getvalue()
    assert "failed" not in out.getvalue()


@test("sync_daily_summaries: one part fails — other parts still sync, one failure recorded")
def _():
    _reset_failures()
    remote = _FakeRemoteStore()
    rows = [
        {"project": "prompt-lab", "date": "2026-08-10", "summary": "Fine.",
         "key_decisions": "[]", "prompt_count": 1, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
        {"project": "prompt-lab", "date": "2026-08-11", "summary": "Bad.",
         "key_decisions": "{not valid json", "prompt_count": 1, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
    ]

    n = _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(rows), remote, since=None, dry_run=False))

    assert n == 1, f"only the good part should count as synced, got {n}"
    assert len(sync_to_turso._FAILURES) == 1, sync_to_turso._FAILURES
    assert "daily_summaries" in sync_to_turso._FAILURES[0]
    assert "2026-08-11" in sync_to_turso._FAILURES[0]


@test("finish(): no failures -> exit 0, nothing printed")
def _():
    with redirect_stdout(io.StringIO()) as out:
        code = sync_to_turso.finish([])
    assert code == 0, code
    assert out.getvalue() == ""


@test("finish(): failures present -> exit 1, FAILED block printed")
def _():
    with redirect_stdout(io.StringIO()) as out:
        code = sync_to_turso.finish(["widgets: a: ValueError: boom"])
    assert code == 1, code
    text = out.getvalue()
    assert "FAILED: 1 row(s) did not sync:" in text, text
    assert "widgets: a: ValueError: boom" in text, text


@test("finish(): more than 20 failures — capped at 20 lines plus a '… and N more' line")
def _():
    failures = [f"widgets: {i}: ValueError: boom" for i in range(25)]
    with redirect_stdout(io.StringIO()) as out:
        code = sync_to_turso.finish(failures)
    assert code == 1, code
    text = out.getvalue()
    assert "FAILED: 25 row(s) did not sync:" in text, text
    for i in range(20):
        assert f"widgets: {i}: ValueError: boom" in text, f"line {i} missing"
    for i in range(20, 25):
        assert f"widgets: {i}: ValueError: boom" not in text, f"line {i} should be capped"
    assert "… and 5 more" in text, text


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
