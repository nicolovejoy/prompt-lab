"""Tests for scripts/close_stale_sessions.py, the nightly `scrub` stage.

Run: .venv/bin/python scripts/test_close_stale_sessions.py

The script runs as a subprocess against a throwaway DB under a temp HOME, so
neither the real history nor ~/.claude/state is ever touched.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "close_stale_sessions.py"
WEEK = ("--recent-hours", "168")  # what the nightly passes

SCHEMA = """
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY, project TEXT NOT NULL, started_at TEXT,
    ended_at TEXT, summary TEXT, claude_session_id TEXT
);
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, session_id INTEGER
);
"""

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


class Env:
    """Temp HOME (for the pointer files) plus a DB of sessions and prompts."""

    def __init__(self, tmp: Path):
        self.home = tmp / "home"
        self.state = self.home / ".claude" / "state"
        self.state.mkdir(parents=True)
        self.db = tmp / "history.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    def session(self, sid: int, *, started: str, prompts: tuple = (),
                native: str | None = None, pointer: str | None = None,
                ended: str | None = None, summary: str | None = None) -> None:
        """Times are SQLite modifiers relative to now, e.g. '-30 days'."""
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO sessions VALUES (?, 'proj', datetime('now', ?), "
            "CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END, ?, ?)",
            (sid, started, ended, ended, summary, native))
        conn.executemany(
            "INSERT INTO prompts (timestamp, session_id) VALUES (datetime('now', ?), ?)",
            [(p, sid) for p in prompts])
        conn.commit()
        conn.close()
        if pointer:
            (self.state / f"current-session-{pointer}").write_text(f"{sid}\n")

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(self.db), *args],
            capture_output=True, text=True, env={**os.environ, "HOME": str(self.home)})

    def q(self, sql: str, params: tuple = ()):
        conn = sqlite3.connect(self.db)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    def open_ids(self) -> list[int]:
        return [r[0] for r in self.q(
            "SELECT id FROM sessions WHERE ended_at IS NULL ORDER BY id")]


def test_closes_idle_rows_to_their_last_activity(tmp: Path) -> None:
    print("\n1. rows idle past the window close at their last activity")
    e = Env(tmp)
    e.session(1, started="-30 days", prompts=("-30 days", "-29 days"))
    e.session(2, started="-20 days")
    e.session(3, started="-30 days", prompts=("-10 days",), native="uuid-idle")
    e.session(4, started="-30 days", prompts=("-1 hours",), native="uuid-live")
    e.session(5, started="-1 hours")
    e.session(6, started="-40 days", ended="-39 days", summary="handed off")
    before = e.q("SELECT ended_at FROM sessions WHERE id=6")

    dry = e.run(*WEEK)
    check("dry run exits 0", dry.returncode, 0)
    check("dry run writes nothing", e.open_ids(), [1, 2, 3, 4, 5])

    run = e.run(*WEEK, "--execute")
    check("execute exits 0", run.returncode, 0)
    check("a live conversation and a just-started row stay open", e.open_ids(), [4, 5])
    check("closed at the last prompt, not at now",
          e.q("SELECT ended_at = (SELECT MAX(timestamp) FROM prompts WHERE session_id=1) "
              "FROM sessions WHERE id=1"), [(1,)])
    check("a row with no prompts closes at its start",
          e.q("SELECT ended_at = started_at FROM sessions WHERE id=2"), [(1,)])
    # A summary marks a handed-off session to the nightly and the dashboard.
    check("no summary is invented",
          e.q("SELECT COUNT(*) FROM sessions WHERE id IN (1,2,3) AND summary IS NOT NULL"),
          [(0,)])
    check("an already-closed row is untouched",
          e.q("SELECT ended_at FROM sessions WHERE id=6"), before)
    check("the log line says what it did",
          "Closed 3. Open sessions remaining: 2" in run.stdout, True)

    again = e.run(*WEEK, "--execute")
    check("a second run closes nothing", "Closed 0." in again.stdout, True)


def test_a_pointer_protects_only_a_row_that_is_still_active(tmp: Path) -> None:
    """Pointer files in ~/.claude/state are written and never removed.

    Treating every row a pointer names as live kept 58 rows open after the
    2026-10-08 sweep, each idle for more than a week: 41 named by a launcher
    pointer, 10 by a Codex one, 7 by a project one.
    """
    print("\n2. a pointer protects a row only while the row is still active")
    e = Env(tmp)
    e.session(1, started="-30 days", prompts=("-20 days",), native="uuid-old",
              pointer="proj-launch:old-window")
    e.session(2, started="-30 days", prompts=("-20 days",), pointer="proj")
    e.session(3, started="-30 days", pointer="other-codex:thread", native="codex:thread")
    # The one case a pointer exists for: no conversation ID, still in use.
    e.session(4, started="-30 days", prompts=("-1 hours",), pointer="legacy")
    # Recent activity alone never protects an unbound row (the landmine rows).
    e.session(5, started="-30 days", prompts=("-1 hours",))

    run = e.run(*WEEK, "--execute")
    check("execute exits 0", run.returncode, 0)
    check("idle rows close even when a pointer names them; a live one stays",
          e.open_ids(), [4])
    (e.state / "current-session-broken").write_text("not a number\n")
    check("an unreadable pointer does not break the run",
          e.run(*WEEK, "--execute").returncode, 0)


def main() -> int:
    for t in (test_closes_idle_rows_to_their_last_activity,
              test_a_pointer_protects_only_a_row_that_is_still_active):
        with tempfile.TemporaryDirectory() as d:
            t(Path(d))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + ", ".join(failures))
        return 1
    print("All close-stale-sessions tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
