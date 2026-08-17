"""Tests for the same-day clobber fix (per-machine daily-summary parts).

daily_summaries is keyed (project, date); before this fix, two machines
syncing the same project-day clobbered each other in Turso — last sync wins.
Now each machine upserts into daily_summaries_machine (keyed +machine) and
the merged row is rebuilt deterministically from all parts.

Run: .venv/bin/python scripts/test_sync_clobber.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import json
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
    """Stands in for SqliteKnowledgeStore — sync_daily_summaries only calls
    get_daily_summaries(since=...) on the local side."""

    def __init__(self, rows):
        self._rows = rows

    def get_daily_summaries(self, *, since=None):
        return self._rows


class _FakeRemoteStore:
    """Dict-backed double for TursoKnowledgeStore's surface that
    sync_daily_summaries actually calls: migrate() (no-op — not called by
    sync_daily_summaries itself, kept for shape-completeness),
    upsert_daily_summary_part, get_daily_summary_parts, upsert_daily_summary,
    plus the _execute/_execute_many attributes sync_daily_summaries
    monkeypatches for buffering. No SQL — every write lands directly in a
    plain dict so the test can assert on real end state.
    """

    def __init__(self):
        self.parts: dict[tuple[str, str, str], dict] = {}
        self.daily: dict[tuple[str, str], dict] = {}

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
            "summary": summary,
            "key_decisions": json.dumps(key_decisions or []),
            "prompt_count": prompt_count, "session_count": session_count,
            "commit_count": commit_count, "model": model,
        }

    def get_daily_summary_parts(self, *, since, until):
        return [p for p in self.parts.values() if since <= p["date"] <= until]

    def upsert_daily_summary(self, *, project, date, summary, key_decisions,
                              prompt_count, session_count, commit_count, model):
        self.daily[(project, date)] = {
            "project": project, "date": date, "summary": summary,
            "key_decisions": key_decisions, "prompt_count": prompt_count,
            "session_count": session_count, "commit_count": commit_count,
            "model": model,
        }


def _with_machine(label, fn):
    """Run fn() with GROUND_CONTROL_MACHINE set to label, restoring after."""
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


@test("sync_daily_summaries: two machines merge end-to-end; re-sync is idempotent; _execute restored")
def _():
    remote = _FakeRemoteStore()
    original_execute = remote._execute

    mini_rows = [{
        "project": "prompt-lab", "date": "2026-08-12",
        "summary": "Nightly jobs ran.", "key_decisions": '["keep jobs"]',
        "prompt_count": 3, "session_count": 1, "commit_count": 0,
        "model": "claude-code",
    }]
    laptop_rows = [{
        "project": "prompt-lab", "date": "2026-08-12",
        "summary": "Fixed the review email.",
        "key_decisions": '["keep jobs", "fix window"]',
        "prompt_count": 12, "session_count": 2, "commit_count": 5,
        "model": "claude-code",
    }]

    n1 = _with_machine("mini", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(mini_rows), remote, since=None, dry_run=False))
    # Bound-method identity isn't stable across attribute lookups in CPython
    # (each `obj.method` access mints a fresh bound-method object), so compare
    # by equality (same __self__ + __func__) rather than `is` — this is the
    # correct check for "points back at the original method", not a weaker one.
    assert remote._execute == original_execute, "_execute not restored after mini sync"
    assert n1 == 1, n1

    n2 = _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(laptop_rows), remote, since=None, dry_run=False))
    assert remote._execute == original_execute, "_execute not restored after laptop sync"
    assert n2 == 1, n2

    merged = remote.daily[("prompt-lab", "2026-08-12")]
    assert merged["summary"] == "[laptop] Fixed the review email.\n[mini] Nightly jobs ran.", merged["summary"]
    assert merged["prompt_count"] == 15 and merged["session_count"] == 3 and merged["commit_count"] == 5, merged
    assert len(remote.daily) == 1, "no stray rows from the two-machine sync"

    # Re-sync laptop's same rows again — must be idempotent, not additive.
    _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(laptop_rows), remote, since=None, dry_run=False))

    resynced = remote.daily[("prompt-lab", "2026-08-12")]
    assert resynced == merged, "re-sync must be idempotent — no duplication, same end state"
    assert len(remote.parts) == 2, "still exactly one part per machine, not accumulating"


@test("sync_daily_summaries: grouping key is (project, date) — different dates stay separate rows")
def _():
    remote = _FakeRemoteStore()
    rows = [
        {"project": "prompt-lab", "date": "2026-08-11", "summary": "Day one.",
         "key_decisions": "[]", "prompt_count": 1, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
        {"project": "prompt-lab", "date": "2026-08-12", "summary": "Day two.",
         "key_decisions": "[]", "prompt_count": 2, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
    ]
    _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(rows), remote, since=None, dry_run=False))

    assert set(remote.daily.keys()) == {
        ("prompt-lab", "2026-08-11"), ("prompt-lab", "2026-08-12")
    }, remote.daily.keys()
    assert remote.daily[("prompt-lab", "2026-08-11")]["summary"] == "Day one."
    assert remote.daily[("prompt-lab", "2026-08-12")]["summary"] == "Day two."


@test("sync_daily_summaries: a bad row's push is skipped, not fatal — other rows still sync")
def _():
    remote = _FakeRemoteStore()
    rows = [
        {"project": "prompt-lab", "date": "2026-08-10", "summary": "Bad row.",
         "key_decisions": "{not valid json", "prompt_count": 1, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
        {"project": "prompt-lab", "date": "2026-08-11", "summary": "Good row.",
         "key_decisions": "[]", "prompt_count": 2, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
    ]
    n = _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
        _FakeLocalStore(rows), remote, since=None, dry_run=False))

    assert n == 1, f"only the good row should count as synced, got {n}"
    assert ("prompt-lab", "2026-08-10") not in remote.daily, "a bad push must not produce a merged row"
    assert remote.daily[("prompt-lab", "2026-08-11")]["summary"] == "Good row."


@test("sync_daily_summaries: a bad part is skipped during rebuild too — other pairs still land")
def _():
    remote = _FakeRemoteStore()
    rows = [
        {"project": "prompt-lab", "date": "2026-08-13", "summary": "Fine.",
         "key_decisions": "[]", "prompt_count": 1, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
        {"project": "byside", "date": "2026-08-13", "summary": "Also fine.",
         "key_decisions": "[]", "prompt_count": 2, "session_count": 1,
         "commit_count": 0, "model": "claude-code"},
    ]
    orig_upsert_part = remote.upsert_daily_summary_part

    def upsert_then_corrupt(**kwargs):
        orig_upsert_part(**kwargs)
        if kwargs["project"] == "byside":
            # Corrupt the stored part directly, bypassing the normal upsert
            # path, so merge_summary_parts (which sorts on p["machine"])
            # raises for exactly this (project, date) pair during rebuild.
            del remote.parts[(kwargs["project"], kwargs["date"], kwargs["machine"])]["machine"]

    remote.upsert_daily_summary_part = upsert_then_corrupt
    try:
        n = _with_machine("laptop", lambda: sync_to_turso.sync_daily_summaries(
            _FakeLocalStore(rows), remote, since=None, dry_run=False))
    finally:
        remote.upsert_daily_summary_part = orig_upsert_part

    assert n == 2, "both parts still counted as synced — the corruption is downstream of the push"
    assert ("prompt-lab", "2026-08-13") in remote.daily, "the healthy pair must still be rebuilt"
    assert ("byside", "2026-08-13") not in remote.daily, "the corrupted pair must not silently produce a row"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
