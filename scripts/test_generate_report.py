"""Regression tests for the bi-monthly report's data sourcing.

The report read get_raw_sessions()/get_period_stats() from the machine-local
raw tier, so a report generated on one machine silently omitted every other
machine's work (same defect as the review email, found 2026-08-13 minutes
before its Aug 15 run would have shipped a two-week report blind to the
laptop). Pinned here: reads come from processed tables via the merged store,
stats derive from daily summaries, and windows are lab-days.

Run: .venv/bin/python scripts/test_generate_report.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

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


def _load_generate_report():
    spec = importlib.util.spec_from_file_location(
        "generate_report", ROOT / "generate-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@test("derive_stats aggregates daily summaries into the period-stats shape")
def _():
    mod = _load_generate_report()
    rows = [
        {"project": "raconte", "date": "2026-08-11", "prompt_count": 20,
         "session_count": 2, "commit_count": 1},
        {"project": "raconte", "date": "2026-08-12", "prompt_count": 4,
         "session_count": 1, "commit_count": 0},
        {"project": "musicforge", "date": "2026-08-12", "prompt_count": 27,
         "session_count": 3, "commit_count": 2},
        # NULL-ish counts must not crash the sums
        {"project": "byside", "date": "2026-08-12", "prompt_count": None,
         "session_count": None, "commit_count": None},
    ]
    st = mod.derive_stats(rows)
    assert st["total_prompts"] == 51, st
    assert st["total_sessions"] == 6, st
    assert st["total_projects"] == 3, st
    by_name = {p["name"]: p for p in st["projects"]}
    assert by_name["raconte"] == {"name": "raconte", "prompts": 24, "active_days": 2}
    assert by_name["musicforge"]["active_days"] == 1
    # ordered by prompts descending, so the report leads with the big work
    assert st["projects"][0]["name"] == "musicforge", st["projects"]


@test("derive_stats coerces Turso's string counts instead of crashing")
def _():
    # Turso returns every integer column as a JSON string over its HTTP API
    # (store/turso_store.py:840; sync_to_turso.py's merge_summary_parts does
    # the same int(...) coercion at the same boundary). A row shaped like a
    # real Turso read must not raise TypeError on `+=` or string-concatenate.
    mod = _load_generate_report()
    rows = [
        {"project": "raconte", "date": "2026-08-11", "prompt_count": "20",
         "session_count": "2", "commit_count": "1"},
        {"project": "raconte", "date": "2026-08-12", "prompt_count": "4",
         "session_count": "1", "commit_count": "0"},
        {"project": "musicforge", "date": "2026-08-12", "prompt_count": "27",
         "session_count": "3", "commit_count": "2"},
    ]
    st = mod.derive_stats(rows)
    assert st["total_prompts"] == 51, st
    assert isinstance(st["total_prompts"], int), st
    assert st["total_sessions"] == 6, st
    assert isinstance(st["total_sessions"], int), st
    by_name = {p["name"]: p for p in st["projects"]}
    assert by_name["raconte"] == {"name": "raconte", "prompts": 24, "active_days": 2}
    assert isinstance(by_name["raconte"]["prompts"], int), by_name


@test("derive_stats of nothing is zeros, not a crash")
def _():
    mod = _load_generate_report()
    st = mod.derive_stats([])
    assert st == {"total_prompts": 0, "total_sessions": 0,
                  "total_projects": 0, "projects": []}, st


@test("report reads the merged store and never the raw tier")
def _():
    src = (ROOT / "generate-report.py").read_text()
    assert "get_raw_sessions" not in src, \
        "the report must not read machine-local raw sessions"
    assert "get_period_stats" not in src, \
        "period stats must derive from daily summaries, not raw prompts"
    assert 'get_store("turso")' in src, \
        "reads must go through the merged (Turso) store"
    assert "lab_days_ago" in src, \
        "the window must be a lab-day, not naive datetime arithmetic"


@test("neither reader script touches the raw tier (cross-file pin)")
def _():
    for fname in ("send-review.py", "generate-report.py"):
        src = (ROOT / fname).read_text()
        assert "get_raw_sessions" not in src, f"{fname} reads raw sessions"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
