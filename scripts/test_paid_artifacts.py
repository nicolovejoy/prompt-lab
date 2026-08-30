"""Tests for archive-before-overwrite on paid prose
(nightly-pipeline-plan step 5).

`daily_summaries` and `weekly_rollups` upserts used to be plain
`INSERT OR REPLACE`, so a re-run silently destroyed prose that cost an
Anthropic API call. These tests pin: overwriting different content archives
the old row into `<table>_superseded`; overwriting identical content archives
nothing; two successive overwrites leave two archive rows in order; a fresh
insert (no prior row) archives nothing; `prompt_version` round-trips onto the
live row; and `synthesizer.prompt_version` is a stable digest that changes
when either input changes.

Run: /Users/nico/src/prompt-lab/.venv/bin/python scripts/test_paid_artifacts.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import synthesizer  # noqa: E402
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


def _upsert_daily(s, summary, prompt_version=None, date="2026-08-29"):
    s.upsert_daily_summary(
        project="prompt-lab", date=date, summary=summary,
        key_decisions=["d1"], prompt_count=3, session_count=1,
        commit_count=2, model="claude-sonnet-4-6",
        prompt_version=prompt_version)


def _upsert_weekly(s, narrative, prompt_version=None, week_start="2026-08-24"):
    s.upsert_weekly_rollup(
        project="prompt-lab", week_start=week_start, narrative=narrative,
        highlights=["h1"], daily_summary_ids=[1],
        prompt_count=10, session_count=3, commit_count=5,
        model="claude-sonnet-4-6", prompt_version=prompt_version)


# ---- daily_summaries ----

@test("overwriting a daily summary archives the OLD prose, live row holds the new")
def _():
    s = _store()
    _upsert_daily(s, "first draft")
    _upsert_daily(s, "second draft")
    live = s.get_daily_summaries(project="prompt-lab")
    assert len(live) == 1, live
    assert live[0]["summary"] == "second draft", live[0]["summary"]
    archived = s._conn.execute(
        "SELECT * FROM daily_summaries_superseded").fetchall()
    assert len(archived) == 1, len(archived)
    assert archived[0]["summary"] == "first draft", archived[0]["summary"]
    s.close()


@test("re-writing IDENTICAL daily content archives nothing")
def _():
    s = _store()
    _upsert_daily(s, "same content")
    _upsert_daily(s, "same content")
    archived = s._conn.execute(
        "SELECT * FROM daily_summaries_superseded").fetchall()
    assert len(archived) == 0, len(archived)
    s.close()


@test("two successive daily overwrites leave TWO archive rows, in order")
def _():
    s = _store()
    _upsert_daily(s, "v1")
    _upsert_daily(s, "v2")
    _upsert_daily(s, "v3")
    archived = s._conn.execute(
        "SELECT summary FROM daily_summaries_superseded ORDER BY id").fetchall()
    assert [r["summary"] for r in archived] == ["v1", "v2"], archived
    live = s.get_daily_summaries(project="prompt-lab")
    assert live[0]["summary"] == "v3", live[0]["summary"]
    s.close()


@test("a fresh daily insert (no prior row) archives nothing")
def _():
    s = _store()
    _upsert_daily(s, "brand new")
    archived = s._conn.execute(
        "SELECT * FROM daily_summaries_superseded").fetchall()
    assert len(archived) == 0, len(archived)
    s.close()


@test("the archive keeps the PRE-replace created_at, not the new row's")
def _():
    """`INSERT OR REPLACE` resets the live row's created_at, so
    original_created_at is the only surviving record of when the archived
    prose was written — the archive's entire point. A regression capturing
    the post-replace stamp would be invisible and unrecoverable."""
    s = _store()
    _upsert_daily(s, "v1")
    s._conn.execute("UPDATE daily_summaries SET created_at = ?",
                    ("2020-01-02 03:04:05",))
    s._conn.commit()
    _upsert_daily(s, "v2")
    archived = s._conn.execute(
        "SELECT original_created_at FROM daily_summaries_superseded").fetchall()
    assert len(archived) == 1, archived
    assert archived[0]["original_created_at"] == "2020-01-02 03:04:05", \
        archived[0]["original_created_at"]
    live = s._conn.execute(
        "SELECT created_at FROM daily_summaries").fetchone()
    assert live["created_at"] != "2020-01-02 03:04:05", dict(live)
    s.close()


# ---- weekly_rollups ----

@test("overwriting a weekly rollup archives the OLD narrative, live row holds the new")
def _():
    s = _store()
    _upsert_weekly(s, "first narrative")
    _upsert_weekly(s, "second narrative")
    live = s.get_weekly_rollups(project="prompt-lab")
    assert len(live) == 1, live
    assert live[0]["narrative"] == "second narrative", live[0]["narrative"]
    archived = s._conn.execute(
        "SELECT * FROM weekly_rollups_superseded").fetchall()
    assert len(archived) == 1, len(archived)
    assert archived[0]["narrative"] == "first narrative", archived[0]["narrative"]
    s.close()


@test("re-writing IDENTICAL weekly content archives nothing")
def _():
    s = _store()
    _upsert_weekly(s, "same narrative")
    _upsert_weekly(s, "same narrative")
    archived = s._conn.execute(
        "SELECT * FROM weekly_rollups_superseded").fetchall()
    assert len(archived) == 0, len(archived)
    s.close()


@test("two successive weekly overwrites leave TWO archive rows, in order")
def _():
    s = _store()
    _upsert_weekly(s, "w1")
    _upsert_weekly(s, "w2")
    _upsert_weekly(s, "w3")
    archived = s._conn.execute(
        "SELECT narrative FROM weekly_rollups_superseded ORDER BY id").fetchall()
    assert [r["narrative"] for r in archived] == ["w1", "w2"], archived
    live = s.get_weekly_rollups(project="prompt-lab")
    assert live[0]["narrative"] == "w3", live[0]["narrative"]
    s.close()


@test("a fresh weekly insert (no prior row) archives nothing")
def _():
    s = _store()
    _upsert_weekly(s, "brand new week")
    archived = s._conn.execute(
        "SELECT * FROM weekly_rollups_superseded").fetchall()
    assert len(archived) == 0, len(archived)
    s.close()


# ---- prompt_version round-trip ----

@test("prompt_version round-trips onto the live daily_summaries row")
def _():
    s = _store()
    _upsert_daily(s, "some prose", prompt_version="abc123def456")
    live = s.get_daily_summaries(project="prompt-lab")
    assert live[0]["prompt_version"] == "abc123def456", live[0]["prompt_version"]
    s.close()


@test("prompt_version round-trips onto the live weekly_rollups row")
def _():
    s = _store()
    _upsert_weekly(s, "some narrative", prompt_version="abc123def456")
    live = s.get_weekly_rollups(project="prompt-lab")
    assert live[0]["prompt_version"] == "abc123def456", live[0]["prompt_version"]
    s.close()


# ---- synthesizer.prompt_version ----

@test("synthesizer.prompt_version is stable for identical input")
def _():
    v1 = synthesizer.prompt_version("system prompt", {"name": "tool"})
    v2 = synthesizer.prompt_version("system prompt", {"name": "tool"})
    assert v1 == v2, (v1, v2)
    assert len(v1) == 12, v1


@test("synthesizer.prompt_version differs when the system prompt changes")
def _():
    v1 = synthesizer.prompt_version("system prompt A", {"name": "tool"})
    v2 = synthesizer.prompt_version("system prompt B", {"name": "tool"})
    assert v1 != v2, (v1, v2)


@test("synthesizer.prompt_version differs when the tool schema changes")
def _():
    v1 = synthesizer.prompt_version("system prompt", {"name": "tool_a"})
    v2 = synthesizer.prompt_version("system prompt", {"name": "tool_b"})
    assert v1 != v2, (v1, v2)


def main():
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
