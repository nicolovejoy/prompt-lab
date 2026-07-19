"""Session-identity tests for the prompt hook and the gc-* wrappers.

Run: .venv/bin/python scripts/test_session_identity.py

Everything runs against a throwaway DB inside a temp HOME — the hook resolves
~/.claude/prompt-history.db through $HOME, so overriding HOME fully isolates it
from the real history. Nothing here touches ~/.claude.

Covers the bug this suite exists for: "the current session" used to mean "newest
open row for this project", so a mid-session /handoff (which set ended_at)
silently re-filed every later prompt onto an unrelated stale session.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "workflow" / "hooks" / "log-prompt.sh"
GC_READ = ROOT / "workflow" / "bin" / "gc-read.sh"
GC_WRITE = ROOT / "workflow" / "bin" / "gc-write.sh"
SUMMARY_PY = ROOT / "workflow" / "bin" / "_update_session_summary.py"

PROJECT = "testproj"

SCHEMA = """
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    summary TEXT,
    utility INTEGER,
    token_count INTEGER,
    hostname TEXT,
    claude_session_id TEXT
);
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    project TEXT,
    prompt TEXT NOT NULL,
    outcome TEXT, utility INTEGER, tags TEXT, notes TEXT,
    session_id INTEGER REFERENCES sessions(id),
    context TEXT, hostname TEXT
);
CREATE TABLE projects (name TEXT PRIMARY KEY);
"""

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


class Env:
    """Temp HOME + DB + a cwd whose basename is the project name."""

    def __init__(self, tmp: Path, *, with_column: bool = True):
        self.home = tmp / "home"
        (self.home / ".claude" / "bin").mkdir(parents=True)
        (self.home / ".claude" / "state").mkdir(parents=True)
        self.cwd = tmp / "src" / PROJECT
        self.cwd.mkdir(parents=True)
        self.transcripts = self.home / ".claude" / "projects" / "slug"
        self.transcripts.mkdir(parents=True)
        self.db = self.home / ".claude" / "prompt-history.db"

        schema = SCHEMA
        if not with_column:
            schema = schema.replace(",\n    claude_session_id TEXT", "")
        conn = sqlite3.connect(self.db)
        conn.executescript(schema)
        conn.commit()
        conn.close()

        # gc-write.sh shells out to the installed copy under $HOME.
        shutil.copy(SUMMARY_PY, self.home / ".claude" / "bin" / "_update_session_summary.py")

    @property
    def env(self) -> dict:
        e = dict(os.environ)
        e["HOME"] = str(self.home)
        return e

    def transcript(self, session_uuid: str) -> Path:
        p = self.transcripts / f"{session_uuid}.jsonl"
        p.write_text(json.dumps({
            "type": "assistant", "sessionId": session_uuid,
            "message": {"content": [{"type": "text", "text": "prior reply"}],
                        "usage": {"input_tokens": 10}},
        }) + "\n")
        return p

    def submit(self, prompt: str, *, session_uuid: str | None = None,
               include_session_id: bool = True, transcript: bool = True) -> None:
        payload = {"prompt": prompt, "cwd": str(self.cwd)}
        if session_uuid:
            if transcript:
                payload["transcript_path"] = str(self.transcript(session_uuid))
            if include_session_id:
                payload["session_id"] = session_uuid
        subprocess.run([str(HOOK)], input=json.dumps(payload), text=True,
                       env=self.env, cwd=str(self.cwd),
                       capture_output=True, check=True)

    def q(self, sql: str, params: tuple = ()):
        conn = sqlite3.connect(self.db)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    def gc(self, script: Path, *args: str, stdin: str = "") -> str:
        r = subprocess.run([str(script), *args], input=stdin, text=True,
                           env=self.env, cwd=str(self.cwd), capture_output=True)
        if r.returncode != 0:
            return f"<exit {r.returncode}: {r.stderr.strip()}>"
        return r.stdout.strip()

    def pointer(self) -> str:
        p = self.home / ".claude" / "state" / f"current-session-{PROJECT}"
        return p.read_text().strip() if p.exists() else ""


def test_binds_to_real_session(tmp: Path) -> None:
    print("\n1. binds prompts to the real Claude session id")
    e = Env(tmp)
    e.submit("first prompt in this conversation, long enough", session_uuid="uuid-a")
    e.submit("second prompt in this conversation, long enough", session_uuid="uuid-a")

    check("one session row created", len(e.q("SELECT id FROM sessions")), 1)
    sid = e.q("SELECT id FROM sessions")[0][0]
    check("claude_session_id stored",
          e.q("SELECT claude_session_id FROM sessions")[0][0], "uuid-a")
    check("both prompts on that row",
          e.q("SELECT COUNT(*) FROM prompts WHERE session_id=?", (sid,))[0][0], 2)
    check("pointer file written", e.pointer(), str(sid))


def test_handoff_midsession(tmp: Path) -> None:
    print("\n2. mid-session /handoff no longer orphans later prompts (THE BUG)")
    e = Env(tmp)
    # A stale open row from another project-session, exactly like row 645.
    e.q("SELECT 1")
    conn = sqlite3.connect(e.db)
    conn.execute("INSERT INTO sessions (project, started_at) VALUES (?, "
                 "datetime('now','-12 days'))", (PROJECT,))
    conn.commit()
    stale_id = conn.execute("SELECT id FROM sessions").fetchone()[0]
    conn.close()

    e.submit("work happening before the handoff, long enough", session_uuid="uuid-b")
    live_id = e.q("SELECT id FROM sessions WHERE claude_session_id='uuid-b'")[0][0]
    check("did not adopt the 12-day-old row", live_id != stale_id, True)

    # /handoff closes the row mid-conversation.
    e.gc(GC_WRITE, "end-session", str(live_id))
    check("row ended", bool(e.q("SELECT ended_at FROM sessions WHERE id=?",
                                (live_id,))[0][0]), True)

    e.submit("more work after the handoff ran, long enough", session_uuid="uuid-b")
    check("later prompt still on the live row",
          e.q("SELECT COUNT(*) FROM prompts WHERE session_id=?", (live_id,))[0][0], 2)
    check("stale row untouched",
          e.q("SELECT COUNT(*) FROM prompts WHERE session_id=?", (stale_id,))[0][0], 0)
    check("no extra session rows", len(e.q("SELECT id FROM sessions")), 2)


def test_two_windows(tmp: Path) -> None:
    print("\n3. two windows on the same project get separate rows")
    e = Env(tmp)
    e.submit("window one is doing its own thing, long enough", session_uuid="uuid-1")
    e.submit("window two is doing something else, long enough", session_uuid="uuid-2")
    e.submit("window one again, still long enough here", session_uuid="uuid-1")

    check("two session rows", len(e.q("SELECT id FROM sessions")), 2)
    one = e.q("SELECT id FROM sessions WHERE claude_session_id='uuid-1'")[0][0]
    two = e.q("SELECT id FROM sessions WHERE claude_session_id='uuid-2'")[0][0]
    check("window one has 2 prompts",
          e.q("SELECT COUNT(*) FROM prompts WHERE session_id=?", (one,))[0][0], 2)
    check("window two has 1 prompt",
          e.q("SELECT COUNT(*) FROM prompts WHERE session_id=?", (two,))[0][0], 1)


def test_adopts_readup_row(tmp: Path) -> None:
    print("\n4. adopts the row /readup registered (no duplicate)")
    e = Env(tmp)
    e.gc(GC_WRITE, "register-session")
    registered = e.q("SELECT id FROM sessions")[0][0]

    e.submit("first real prompt after readup registered, long", session_uuid="uuid-c")
    check("still exactly one row", len(e.q("SELECT id FROM sessions")), 1)
    check("that row got bound",
          e.q("SELECT claude_session_id FROM sessions WHERE id=?",
              (registered,))[0][0], "uuid-c")


def test_transcript_fallback(tmp: Path) -> None:
    print("\n5. derives the id from transcript_path when session_id is absent")
    e = Env(tmp)
    e.submit("prompt with no session_id field present, long",
             session_uuid="uuid-d", include_session_id=False)
    check("bound via transcript basename",
          e.q("SELECT claude_session_id FROM sessions")[0][0], "uuid-d")


def test_no_id_falls_back(tmp: Path) -> None:
    print("\n6. underivable id falls back to old behavior, never drops the prompt")
    e = Env(tmp)
    conn = sqlite3.connect(e.db)
    conn.execute("INSERT INTO sessions (project) VALUES (?)", (PROJECT,))
    conn.commit()
    conn.close()
    open_id = e.q("SELECT id FROM sessions")[0][0]

    e.submit("prompt with neither session_id nor transcript path",
             session_uuid=None)
    check("prompt still logged", e.q("SELECT COUNT(*) FROM prompts")[0][0], 1)
    check("attached to the open row",
          e.q("SELECT session_id FROM prompts")[0][0], open_id)


def test_missing_column_self_heals(tmp: Path) -> None:
    print("\n7. self-heals a pre-migration schema")
    e = Env(tmp, with_column=False)
    cols = {r[1] for r in sqlite3.connect(e.db).execute("PRAGMA table_info(sessions)")}
    check("column absent to start", "claude_session_id" in cols, False)

    e.submit("first prompt on a machine that never migrated yet", session_uuid="uuid-e")
    cols = {r[1] for r in sqlite3.connect(e.db).execute("PRAGMA table_info(sessions)")}
    check("column added by the hook", "claude_session_id" in cols, True)
    check("prompt bound correctly",
          e.q("SELECT claude_session_id FROM sessions")[0][0], "uuid-e")


def test_gc_read_contract(tmp: Path) -> None:
    print("\n8. gc-read.sh current-session keeps its id|started_at contract")
    e = Env(tmp)
    e.submit("a prompt so the pointer file gets written, long", session_uuid="uuid-f")
    sid = e.q("SELECT id FROM sessions")[0][0]
    started = e.q("SELECT started_at FROM sessions")[0][0]

    check("current-session output", e.gc(GC_READ, "current-session"), f"{sid}|{started}")

    # Ended session: the pointer still resolves it (that is the point).
    e.gc(GC_WRITE, "end-session", str(sid))
    check("still resolves after end-session",
          e.gc(GC_READ, "current-session"), f"{sid}|{started}")

    # Pointer removed -> falls back to the old query.
    (e.home / ".claude" / "state" / f"current-session-{PROJECT}").unlink()
    check("falls back to open-row query when pointer is gone",
          e.gc(GC_READ, "current-session"), "")

    check("pulse-prompts survives a missing pointer",
          e.gc(GC_READ, "pulse-prompts"), "")


def test_summary_does_not_end(tmp: Path) -> None:
    print("\n9. update-session-summary writes summary only; end-session ends")
    e = Env(tmp)
    e.submit("a prompt to create the session row here, long", session_uuid="uuid-g")
    sid = e.q("SELECT id FROM sessions")[0][0]

    e.gc(GC_WRITE, "update-session-summary", str(sid), stdin="did some things")
    row = e.q("SELECT summary, ended_at FROM sessions WHERE id=?", (sid,))[0]
    check("summary written", row[0], "did some things")
    check("ended_at still null", row[1], None)

    e.gc(GC_WRITE, "end-session", str(sid))
    check("ended_at set by end-session",
          bool(e.q("SELECT ended_at FROM sessions WHERE id=?", (sid,))[0][0]), True)

    check("end-session rejects a non-numeric id",
          e.gc(GC_WRITE, "end-session", "abc").startswith("<exit 2"), True)


def main() -> int:
    # The hook is bash and shells out; skip rather than fail red if the runner
    # lacks a dependency. A skip is honest; a red CI for an env reason is noise.
    missing = [t for t in ("jq", "sqlite3", "bash") if shutil.which(t) is None]
    if missing:
        print(f"SKIP session-identity tests — missing: {', '.join(missing)}")
        return 0

    tests = [
        test_binds_to_real_session,
        test_handoff_midsession,
        test_two_windows,
        test_adopts_readup_row,
        test_transcript_fallback,
        test_no_id_falls_back,
        test_missing_column_self_heals,
        test_gc_read_contract,
        test_summary_does_not_end,
    ]
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            t(Path(d))

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + ", ".join(failures))
        return 1
    print("All session-identity tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
