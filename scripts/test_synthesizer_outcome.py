"""Tests for synthesizer.py's outcome accounting (nightly-wake-resilience task 1).

Four nights this month the machine woke with no DNS, every API call in
synthesizer.py failed, and the nightly still reported success — main()
unconditionally pinged the heartbeat and exited 0. These tests drive main()
end to end with a stubbed store and a stubbed call_claude that raises (no
network, no API key needed) and assert the exit code and whether the
heartbeat was pinged for each of: total wipeout, partial failure, nothing
attempted, and full success.

Run: .venv/bin/python scripts/test_synthesizer_outcome.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import synthesizer  # noqa: E402

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


class FakeStore:
    """Answers only what main()'s phases need. Daily pairs vary per test;
    weekly and states are starved of input so only the daily phase's counts
    reach main()'s totals — keeping the tests independent of which weekday
    they happen to run on (states only runs on Sundays or with --states)."""

    def __init__(self, daily_pairs):
        self.daily_pairs = daily_pairs
        self.logs: list[dict] = []
        self.closed = False
        self.migrated = False

    def migrate(self):
        self.migrated = True

    def close(self):
        self.closed = True

    # --- daily ---
    def get_unsummarized_days(self, target_date=None):
        return self.daily_pairs

    def get_day_data(self, project, date):
        return {"prompts": [], "commits": [], "sessions": []}

    def upsert_daily_summary(self, **kw):
        pass

    # --- weekly (starved) ---
    def get_weeks_without_rollups(self):
        return []

    def get_daily_summaries_for_week(self, project, week_start):
        return []

    def upsert_weekly_rollup(self, **kw):
        pass

    # --- states (starved) ---
    def get_projects_with_recent_summaries(self, n_days=14):
        return []

    def get_weekly_rollups(self, *, project=None, limit=None):
        return []

    def get_daily_summaries(self, *, project=None, limit=None):
        return []

    def get_project_snapshot(self, project, *, date=None):
        return None

    def save_project_snapshot(self, *, project, date, data):
        pass

    # --- shared ---
    def log_synthesis(self, **kw):
        self.logs.append(kw)

    def get_recent_synthesis_logs(self):
        if not self.logs:
            return []
        total_in = sum(e.get("input_tokens", 0) or 0 for e in self.logs)
        total_out = sum(e.get("output_tokens", 0) or 0 for e in self.logs)
        total_cost = sum(e.get("cost_cents", 0) or 0 for e in self.logs)
        return [{
            "run_type": "daily", "calls": len(self.logs),
            "total_in": total_in, "total_out": total_out,
            "total_cost": total_cost,
        }]


def call_claude_ok(*a, **kw):
    return {
        "parsed": {"summary": "did stuff", "key_decisions": []},
        "input_tokens": 10, "output_tokens": 5,
        "duration_ms": 50, "model": "claude-sonnet-4-6",
    }


def call_claude_boom(*a, **kw):
    # A DNS-outage-shaped failure: not one of call_claude's own retryable
    # exception types, since we've replaced call_claude wholesale — this
    # stub raises immediately, no sleeping, no network.
    raise OSError("[Errno 8] nodename nor servname provided, or not known")


def make_alternating(pattern):
    """pattern: list of bools, True = raise, consumed one per call."""
    calls = iter(pattern)

    def _call(*a, **kw):
        if next(calls):
            return call_claude_boom(*a, **kw)
        return call_claude_ok(*a, **kw)

    return _call


@contextmanager
def run_main_all(daily_pairs, call_claude_stub):
    """Drive synthesizer.main() as the LaunchAgent does (--all), fully
    stubbed: no store, no real client, no network, no real API key."""
    store = FakeStore(daily_pairs)
    pings: list[str] = []

    saved = (synthesizer.get_store, synthesizer.get_client,
              synthesizer.call_claude, synthesizer.load_env,
              synthesizer.heartbeat.ping, sys.argv)
    saved_key = os.environ.get("ANTHROPIC_API_KEY")

    synthesizer.get_store = lambda: store
    synthesizer.get_client = lambda: object()
    synthesizer.call_claude = call_claude_stub
    synthesizer.load_env = lambda: None
    synthesizer.heartbeat.ping = lambda job: pings.append(job) or True
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake-not-real"
    sys.argv = ["synthesizer.py", "--all"]

    out = io.StringIO()
    try:
        with redirect_stdout(out):
            code = synthesizer.main()
        yield code, pings, store, out.getvalue()
    finally:
        (synthesizer.get_store, synthesizer.get_client,
         synthesizer.call_claude, synthesizer.load_env,
         synthesizer.heartbeat.ping, sys.argv) = saved
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key


@test("total wipeout: every call fails -> exit 1, no heartbeat, FAILED line")
def _():
    pairs = [("proj1", "2026-09-01"), ("proj2", "2026-09-01")]
    with run_main_all(pairs, call_claude_boom) as (code, pings, store, out):
        assert code == 1, code
        assert pings == [], f"heartbeat must not be pinged on wipeout, got {pings}"
        assert "FAILED: every synthesis call failed; not pinging the heartbeat" in out, out
        assert "WARNING: 2/2 synthesis calls failed" in out, out


@test("partial failure: some calls fail -> exit 0, heartbeat still pinged")
def _():
    pairs = [("proj1", "2026-09-01"), ("proj2", "2026-09-01")]
    stub = make_alternating([True, False])  # first fails, second succeeds
    with run_main_all(pairs, stub) as (code, pings, store, out):
        assert code == 0, code
        assert pings == ["synthesizer"], pings
        assert "WARNING: 1/2 synthesis calls failed" in out, out
        assert "FAILED" not in out, out


@test("nothing attempted: quiet night -> exit 0, heartbeat still pinged")
def _():
    with run_main_all([], call_claude_boom) as (code, pings, store, out):
        assert code == 0, code
        assert pings == ["synthesizer"], pings
        assert "WARNING" not in out, out
        assert "FAILED" not in out, out


@test("all succeeded: exit 0, heartbeat pinged, no warning")
def _():
    pairs = [("proj1", "2026-09-01"), ("proj2", "2026-09-01")]
    with run_main_all(pairs, call_claude_ok) as (code, pings, store, out):
        assert code == 0, code
        assert pings == ["synthesizer"], pings
        assert "WARNING" not in out, out
        assert "FAILED" not in out, out


@test("wipeout still closes the store handle (no resource leak on failure)")
def _():
    pairs = [("proj1", "2026-09-01")]
    with run_main_all(pairs, call_claude_boom) as (code, pings, store, out):
        assert code == 1, code
        assert store.closed, "store.close() must run even on a total wipeout"


def main() -> int:
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
