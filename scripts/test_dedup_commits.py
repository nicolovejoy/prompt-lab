"""Tests for scripts/dedup_commits.py (issue #57: no unique key on
commits.hash, so /handoff's INSERT OR IGNORE never ignores a re-run).

Every test builds its own temp-file SQLite DB shaped like the real
`commits` table (see the docstring in dedup_commits.py for the schema this
mirrors) — never the real `~/.claude/prompt-history.db`, and --apply is only
ever run against these throwaway files.

Run: .venv/bin/python scripts/test_dedup_commits.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import dedup_commits  # noqa: E402
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


SCHEMA = """
    CREATE TABLE commits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prompt_id INTEGER,
        hash TEXT NOT NULL,
        message TEXT,
        timestamp TEXT DEFAULT (datetime('now')),
        session_id INTEGER
    );
    CREATE INDEX idx_commits_prompt_id ON commits(prompt_id);
"""


def make_db(tmpdir: Path, rows) -> Path:
    """rows: list of (hash, message, session_id) inserted in order, so the
    first occurrence of a hash gets the lowest id."""
    db = tmpdir / "prompt-history.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO commits (hash, message, session_id) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def run(db: Path, *extra_args: str) -> tuple[int, str]:
    argv = sys.argv
    sys.argv = ["dedup_commits.py", "--db", str(db), *extra_args]
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            code = dedup_commits.main()
    finally:
        sys.argv = argv
    return code, out.getvalue()


@test("dry run: prints counts and changes nothing")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [
            ("aaa", "first", 1),
            ("aaa", "dup of first", 2),
            ("bbb", "only one", 1),
        ])
        code, out = run(db)
        assert code == 0, out
        assert "total rows:      3" in out, out
        assert "distinct hashes: 2" in out, out
        assert "duplicate rows:  1" in out, out
        assert "DRY RUN" in out, out
        assert not list(db.parent.glob("*.bak-*")), "dry run must not write a backup"

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0] == 3
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(commits)")}
        assert "commits_hash" not in indexes, "dry run must not create the index"
        conn.close()


@test("apply: keeps min(id) per hash, deletes the rest")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [
            ("aaa", "kept — first session to record it", 1),
            ("aaa", "duplicate", 2),
            ("aaa", "second duplicate", 3),
            ("bbb", "unique commit", 1),
        ])
        code, out = run(db, "--apply")
        assert code == 0, out
        assert "Deleted 2 duplicate rows" in out, out

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, hash, message FROM commits ORDER BY id").fetchall()
        assert [r["hash"] for r in rows] == ["aaa", "bbb"]
        assert rows[0]["message"] == "kept — first session to record it"
        conn.close()


@test("apply: creates the commits_hash unique index")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [("aaa", "one", 1), ("bbb", "two", 1)])
        run(db, "--apply")
        conn = sqlite3.connect(db)
        indexes = {r[1]: r[2] for r in conn.execute("PRAGMA index_list(commits)")}
        assert "commits_hash" in indexes, indexes
        assert indexes["commits_hash"] == 1, "index must be UNIQUE"
        # Enforced going forward: a fresh duplicate insert now raises.
        try:
            conn.execute("INSERT INTO commits (hash, message) VALUES ('aaa', 'late dup')")
            raise AssertionError("expected UNIQUE constraint to reject the duplicate hash")
        except sqlite3.IntegrityError:
            pass
        conn.close()


@test("apply: idempotent — a second run deletes 0 rows and succeeds")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [
            ("aaa", "kept", 1),
            ("aaa", "dup", 2),
            ("bbb", "solo", 1),
        ])
        code1, out1 = run(db, "--apply")
        assert code1 == 0, out1
        assert "Deleted 1 duplicate rows" in out1, out1

        code2, out2 = run(db, "--apply")
        assert code2 == 0, out2
        assert "Deleted 0 duplicate rows" in out2, out2

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0] == 2
        conn.close()


@test("apply: writes a readable backup before touching the table")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [("aaa", "kept", 1), ("aaa", "dup", 2)])
        code, out = run(db, "--apply")
        assert code == 0, out

        backups = list(Path(td).glob("prompt-history.db.bak-*"))
        assert len(backups) == 1, backups
        # The backup was taken before the delete, so it still has both rows.
        conn = sqlite3.connect(backups[0])
        assert conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0] == 2
        conn.close()


@test("dry run: reports cross-session duplicates separately from same-session ones")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td), [
            ("aaa", "kept", 1),
            ("aaa", "same session re-run", 1),
            ("bbb", "kept", 1),
            ("bbb", "credited to a different session", 2),
        ])
        code, out = run(db)
        assert code == 0, out
        assert "duplicate rows:  2" in out, out
        assert "cross-session:   1" in out, out


# --- store.sqlite_store.SqliteKnowledgeStore.migrate() coverage ---
#
# migrate() defensively (re-)creates commits_hash itself (see
# store/sqlite_store.py) so any DB opened through the store, not just one
# passed through dedup_commits.py, ends up with the index once it's safe to
# add. Both branches of that guard need direct coverage: clean table -> the
# index gets created; table still carrying duplicates -> migrate() must not
# raise, must not create the index, and must say so on stderr (the "Important"
# finding from task-3 round 1 review — a silent `except: pass` there hides
# that #57 isn't fixed on that DB and INSERT OR IGNORE is still inserting
# duplicates).

@test("migrate(): clean commits table gets the commits_hash unique index")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "store.db"
        conn = sqlite3.connect(db)
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO commits (hash, message, session_id) VALUES (?, ?, ?)",
            [("aaa", "one", 1), ("bbb", "two", 1)],
        )
        conn.commit()
        conn.close()

        err = io.StringIO()
        with redirect_stderr(err):
            store = SqliteKnowledgeStore(db_path=db)
            store.migrate()
            store.close()

        assert "commits" not in err.getvalue(), err.getvalue()
        conn = sqlite3.connect(db)
        indexes = {r[1]: r[2] for r in conn.execute("PRAGMA index_list(commits)")}
        assert indexes.get("commits_hash") == 1, indexes
        conn.close()


@test("migrate(): commits table with duplicates — no raise, no index, warns on stderr")
def _():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "store.db"
        conn = sqlite3.connect(db)
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO commits (hash, message, session_id) VALUES (?, ?, ?)",
            [("aaa", "kept", 1), ("aaa", "duplicate", 2)],
        )
        conn.commit()
        conn.close()

        err = io.StringIO()
        with redirect_stderr(err):
            store = SqliteKnowledgeStore(db_path=db)
            store.migrate()  # must not raise
            store.close()

        warning = err.getvalue()
        assert "commits" in warning and "duplicate hashes present" in warning, warning
        assert "scripts/dedup_commits.py --apply" in warning, warning

        conn = sqlite3.connect(db)
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(commits)")}
        assert "commits_hash" not in indexes, indexes
        assert conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0] == 2, \
            "migrate() must not delete anything — that's dedup_commits.py's job"
        conn.close()


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
