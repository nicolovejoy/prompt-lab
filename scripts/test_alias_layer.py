"""Smoke tests for the alias mapping layer.

Run: .venv/bin/python scripts/test_alias_layer.py

Self-contained: uses in-memory SQLite, no external dependencies, no pytest.
Prints PASS/FAIL per test. Exits 0 if all pass, 1 if any fail.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from alias import cmd_add, cmd_rm  # noqa: E402
from store.base import (  # noqa: E402
    fold_by_canonical,
    keep_latest_session,
    merge_session_data,
)
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402


def make_store() -> SqliteKnowledgeStore:
    """Fresh in-memory store with migrations + minimal prompts/sessions fixtures.

    The real prompts and sessions tables are created by the prompt-log hook,
    not by `migrate()`. Tests recreate minimal versions so the queries that
    read them work.
    """
    s = SqliteKnowledgeStore(db_path=":memory:")
    s.migrate()
    s._conn.executescript("""
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            timestamp TEXT NOT NULL,
            prompt TEXT, outcome TEXT, utility INTEGER,
            tags TEXT, context TEXT, hostname TEXT
        );
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            started_at TEXT, ended_at TEXT,
            summary TEXT, utility INTEGER, hostname TEXT
        );
    """)
    s._conn.commit()
    return s


_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
            return fn
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}"))
            return fn
        _results.append((name, True, ""))
        return fn
    return deco


# === expand_project ===

@test("expand_project: unknown name passes through")
def _():
    s = make_store()
    assert s.expand_project("anything") == ["anything"]


@test("expand_project: empty input passes through")
def _():
    s = make_store()
    assert s.expand_project("") == [""]


@test("expand_project: canonical with aliases returns canonical first, all members")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('old1','new')")
    s._conn.execute("INSERT INTO project_aliases VALUES ('old2','new')")
    s._conn.commit()
    s.invalidate_alias_cache()
    result = s.expand_project("new")
    assert result[0] == "new", f"canonical not first: {result}"
    assert set(result) == {"new", "old1", "old2"}, f"missing members: {result}"


@test("expand_project: alias resolves to canonical + siblings")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('old1','new')")
    s._conn.execute("INSERT INTO project_aliases VALUES ('old2','new')")
    s._conn.commit()
    s.invalidate_alias_cache()
    result = s.expand_project("old1")
    assert result[0] == "new", f"canonical not first: {result}"
    assert set(result) == {"new", "old1", "old2"}


# === canonical_projects ===

@test("canonical_projects: collapses alias buckets, preserves first-canonical order")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('old','new')")
    s._conn.commit()
    s.invalidate_alias_cache()
    assert s.canonical_projects(["old", "other", "new"]) == ["new", "other"]


# === get_unsummarized_days ===

@test("get_unsummarized_days: no aliases, prompts but no summary → returned")
def _():
    s = make_store()
    s._conn.execute(
        "INSERT INTO prompts (project, timestamp) VALUES ('p','2026-05-01 10:00')"
    )
    s._conn.commit()
    assert ("p", "2026-05-01") in s.get_unsummarized_days()


@test("get_unsummarized_days: alias prompts + canonical summary → not returned")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('frontend','musicforge')")
    s._conn.execute(
        "INSERT INTO prompts (project, timestamp) VALUES ('frontend','2026-05-01 10:00')"
    )
    s.upsert_daily_summary(
        project="musicforge", date="2026-05-01", summary="x",
        key_decisions=[], prompt_count=1, session_count=0, commit_count=0, model="m",
    )
    s.invalidate_alias_cache()
    days = s.get_unsummarized_days()
    assert ("frontend", "2026-05-01") not in days, f"got {days}"
    assert ("musicforge", "2026-05-01") not in days, f"got {days}"


@test("get_unsummarized_days: canonical prompts + alias summary → not returned")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('frontend','musicforge')")
    s._conn.execute(
        "INSERT INTO prompts (project, timestamp) VALUES ('musicforge','2026-05-01 10:00')"
    )
    s.upsert_daily_summary(
        project="frontend", date="2026-05-01", summary="x",
        key_decisions=[], prompt_count=1, session_count=0, commit_count=0, model="m",
    )
    s.invalidate_alias_cache()
    days = s.get_unsummarized_days()
    assert ("frontend", "2026-05-01") not in days, f"got {days}"
    assert ("musicforge", "2026-05-01") not in days, f"got {days}"


@test("get_unsummarized_days: prompts under both names, no summary → returned once as canonical")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('frontend','musicforge')")
    s._conn.executescript("""
        INSERT INTO prompts (project, timestamp) VALUES ('frontend','2026-05-01 10:00');
        INSERT INTO prompts (project, timestamp) VALUES ('musicforge','2026-05-01 11:00');
    """)
    s.invalidate_alias_cache()
    days = s.get_unsummarized_days()
    canonical_hits = [d for d in days if d == ("musicforge", "2026-05-01")]
    alias_hits = [d for d in days if d == ("frontend", "2026-05-01")]
    assert len(canonical_hits) == 1, f"expected 1 canonical hit, got {canonical_hits}"
    assert len(alias_hits) == 0, f"alias should not appear: {alias_hits}"


# === get_weeks_without_rollups ===

@test("get_weeks_without_rollups: alias summary on a week already rolled-up under canonical → not returned")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('old','new')")
    s.upsert_daily_summary(
        project="old", date="2026-04-27", summary="x",
        key_decisions=[], prompt_count=1, session_count=0, commit_count=0, model="m",
    )
    s.upsert_weekly_rollup(
        project="new", week_start="2026-04-27", narrative="x",
        highlights=[], daily_summary_ids=[],
        prompt_count=0, session_count=0, commit_count=0, model="m",
    )
    s.invalidate_alias_cache()
    weeks = s.get_weeks_without_rollups()
    assert ("old", "2026-04-27") not in weeks, f"got {weeks}"
    assert ("new", "2026-04-27") not in weeks, f"got {weeks}"


# === fold_by_canonical / merge_session_data / keep_latest_session ===

@test("fold_by_canonical: merges alias entries into canonical key")
def _():
    out = fold_by_canonical(
        {"frontend": [1, 2], "musicforge": [3]},
        {"frontend": "musicforge"},
        lambda a, b: a + b,
    )
    assert set(out.keys()) == {"musicforge"}
    assert sorted(out["musicforge"]) == [1, 2, 3]


@test("fold_by_canonical: leaves unaliased keys alone, empty alias map is identity")
def _():
    out = fold_by_canonical({"a": 1, "b": 2}, {}, lambda x, y: x + y)
    assert out == {"a": 1, "b": 2}


@test("merge_session_data: weights avg_tokens, sums counts, picks max started + max peak")
def _():
    a = {"session_count": 4, "last_started": "2026-05-01",
         "avg_tokens": 100, "peak_tokens": 200}
    b = {"session_count": 6, "last_started": "2026-05-03",
         "avg_tokens": 50, "peak_tokens": 300}
    out = merge_session_data(a, b)
    assert out["session_count"] == 10
    assert out["last_started"] == "2026-05-03"
    assert out["avg_tokens"] == (100 * 4 + 50 * 6) / 10
    assert out["peak_tokens"] == 300


@test("merge_session_data: tolerates None tokens / counts")
def _():
    a = {"session_count": 0, "last_started": None,
         "avg_tokens": None, "peak_tokens": None}
    b = {"session_count": 2, "last_started": "2026-05-01",
         "avg_tokens": 100, "peak_tokens": 200}
    out = merge_session_data(a, b)
    assert out["session_count"] == 2
    assert out["last_started"] == "2026-05-01"
    assert out["peak_tokens"] == 200


@test("keep_latest_session: picks later started_at regardless of arg order")
def _():
    a = {"summary": "old", "started_at": "2026-04-01"}
    b = {"summary": "new", "started_at": "2026-05-01"}
    assert keep_latest_session(a, b) is b
    assert keep_latest_session(b, a) is b


@test("keep_latest_session: tolerates one None started_at")
def _():
    a = {"summary": "x", "started_at": None}
    b = {"summary": "y", "started_at": "2026-05-01"}
    assert keep_latest_session(a, b) is b
    assert keep_latest_session(b, a) is b


# === alias.py CLI commands ===

@test("cmd_add: rejects chain (canonical is itself an alias)")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('a','b')")
    s._conn.commit()
    s.invalidate_alias_cache()
    with redirect_stdout(io.StringIO()):
        rc = cmd_add(s, "c", "a")  # c → a, but a is alias of b
    assert rc == 2, f"expected rc=2, got {rc}"
    rows = list(s._conn.execute("SELECT alias FROM project_aliases").fetchall())
    assert [r["alias"] for r in rows] == ["a"], f"unexpected rows: {rows}"


@test("cmd_add: rejects circular (alias is already a canonical for others)")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('a','b')")
    s._conn.commit()
    s.invalidate_alias_cache()
    with redirect_stdout(io.StringIO()):
        rc = cmd_add(s, "b", "c")  # b → c, but a → b exists
    assert rc == 2, f"expected rc=2, got {rc}"
    rows = list(s._conn.execute("SELECT alias FROM project_aliases").fetchall())
    assert [r["alias"] for r in rows] == ["a"], f"unexpected rows: {rows}"


@test("cmd_add: rejects alias == canonical")
def _():
    s = make_store()
    with redirect_stdout(io.StringIO()):
        rc = cmd_add(s, "x", "x")
    assert rc == 2


@test("cmd_add: happy path adds row and invalidates cache")
def _():
    s = make_store()
    _ = s.expand_project("anything")  # prime the cache
    with redirect_stdout(io.StringIO()):
        rc = cmd_add(s, "old", "new")
    assert rc == 0
    # After invalidation, expand sees the new alias
    assert sorted(s.expand_project("new")) == ["new", "old"]


@test("cmd_rm: returns 1 for nonexistent alias")
def _():
    s = make_store()
    with redirect_stdout(io.StringIO()):
        rc = cmd_rm(s, "doesnt-exist")
    assert rc == 1


@test("cmd_rm: removes existing alias and invalidates cache")
def _():
    s = make_store()
    s._conn.execute("INSERT INTO project_aliases VALUES ('old','new')")
    s._conn.commit()
    s.invalidate_alias_cache()
    _ = s.expand_project("new")  # prime cache
    with redirect_stdout(io.StringIO()):
        rc = cmd_rm(s, "old")
    assert rc == 0
    assert s.expand_project("new") == ["new"]


# === Main ===

def main() -> int:
    if not _results:
        print("no tests ran")
        return 1
    passed = 0
    for name, ok, err in _results:
        mark = "PASS" if ok else "FAIL"
        if ok:
            print(f"  {mark}  {name}")
            passed += 1
        else:
            print(f"  {mark}  {name}")
            print(f"        → {err}")
    failed = len(_results) - passed
    print()
    print(f"{passed} passed, {failed} failed (of {len(_results)})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
