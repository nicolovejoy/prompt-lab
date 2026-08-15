"""Tests for the same-day clobber fix (per-machine daily-summary parts).

daily_summaries is keyed (project, date); before this fix, two machines
syncing the same project-day clobbered each other in Turso — last sync wins.
Now each machine upserts into daily_summaries_machine (keyed +machine) and
the merged row is rebuilt deterministically from all parts.

Run: .venv/bin/python scripts/test_sync_clobber.py
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


@test("single-machine part passes through unmerged (the common case)")
def _():
    part = {"project": "raconte", "date": "2026-08-12", "machine": "laptop",
            "summary": "Shipped the exporter.",
            "key_decisions": '["ship it"]',
            "prompt_count": 24, "session_count": 3, "commit_count": 2,
            "model": "claude-code"}
    m = sync_to_turso.merge_summary_parts([part])
    assert m["summary"] == "Shipped the exporter.", m
    assert "[laptop]" not in m["summary"], "no machine prefix when only one machine"
    assert m["key_decisions"] == ["ship it"], "JSON-string key_decisions must decode"
    assert m["prompt_count"] == 24 and m["model"] == "claude-code", m
    assert "machine" not in m, "merged rows carry no machine column"


@test("two machines merge deterministically: prefixed prose, summed counts")
def _():
    a = {"project": "prompt-lab", "date": "2026-08-12", "machine": "mini",
         "summary": "Nightly jobs ran.", "key_decisions": ["keep jobs"],
         "prompt_count": 3, "session_count": 1, "commit_count": 0,
         "model": "claude-code"}
    b = {"project": "prompt-lab", "date": "2026-08-12", "machine": "laptop",
         "summary": "Fixed the review email.", "key_decisions": ["keep jobs", "fix window"],
         "prompt_count": "12", "session_count": "2", "commit_count": "5",
         "model": "claude-code"}  # string counts: Turso returns aggregates as strings
    m1 = sync_to_turso.merge_summary_parts([a, b])
    m2 = sync_to_turso.merge_summary_parts([b, a])
    assert m1 == m2, "merge must be order-independent"
    assert m1["summary"] == "[laptop] Fixed the review email.\n[mini] Nightly jobs ran.", m1["summary"]
    assert m1["prompt_count"] == 15 and m1["session_count"] == 3 and m1["commit_count"] == 5, m1
    assert m1["key_decisions"] == ["keep jobs", "fix window"], "dedup preserves first-seen order"
    assert m1["model"] == "merged", m1


@test("machine_label: env override wins, fallback is short lowercase hostname")
def _():
    import os
    import socket
    had = os.environ.get("GROUND_CONTROL_MACHINE")
    os.environ["GROUND_CONTROL_MACHINE"] = "testbox"
    try:
        assert sync_to_turso.machine_label() == "testbox"
    finally:
        if had is None:
            del os.environ["GROUND_CONTROL_MACHINE"]
        else:
            os.environ["GROUND_CONTROL_MACHINE"] = had
    if os.environ.get("GROUND_CONTROL_MACHINE") is None:
        expect = socket.gethostname().split(".")[0].lower()
        assert sync_to_turso.machine_label() == expect


@test("the daily leg goes through parts, not a blind whole-row upsert")
def _():
    src = (ROOT / "sync_to_turso.py").read_text()
    assert "daily_summaries_machine" in src, "parts table never written"
    assert "sync_daily_summaries(" in src, "dedicated daily leg missing"
    assert "merge_summary_parts" in src, "merged rebuild missing"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
