"""Exercise installed helpers with two conversations and a disposable local DB."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import shlex
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402


def run(script, *args, env, cwd, stdin="", ok=True):
    result = subprocess.run([str(script), *args], cwd=cwd, env=env, input=stdin,
                            text=True, capture_output=True)
    if ok:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, result.stdout
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="workflow-roundtrip-") as temp:
    home = Path(temp) / "home"
    installed = home / ".claude" / "bin"
    installed.mkdir(parents=True)
    for source in (ROOT / "workflow" / "bin").iterdir():
        if source.is_file():
            shutil.copy2(source, installed / source.name)
    # The launcher's actual project attribution should see a real repository.
    cwd = Path(temp) / "roundtrip"
    cwd.mkdir()
    subprocess.run(["git", "init", "-q", str(cwd)], check=True)
    # CI installs into its selected interpreter, not a repository .venv. Build
    # the same runtime layout the real installer provides, inside the fixture.
    runtime = Path(temp) / "runtime"
    (runtime / ".venv/bin").mkdir(parents=True)
    interpreter = runtime / ".venv/bin/python"
    interpreter.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    interpreter.chmod(0o755)
    shutil.copytree(ROOT / "store", runtime / "store", ignore=shutil.ignore_patterns("__pycache__"))
    env = dict(os.environ, HOME=str(home), PROMPT_LAB_DIR=str(runtime),
               GROUND_CONTROL_STORE="turso", TZ="Asia/Tokyo")
    env.pop("GC_SESSION_SCOPE", None)
    first_env = dict(env, CODEX_THREAD_ID="roundtrip-first")
    second_env = dict(env, CODEX_THREAD_ID="roundtrip-second")
    db = home / ".claude" / "prompt-history.db"
    store = SqliteKnowledgeStore(db)
    store.migrate()
    store.conn.executescript("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
            started_at TEXT DEFAULT (datetime('now')), ended_at TEXT, summary TEXT,
            hostname TEXT, claude_session_id TEXT
        );
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now')),
            project TEXT, prompt TEXT, session_id INTEGER
        );
        CREATE TABLE commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT, message TEXT,
            timestamp TEXT DEFAULT (datetime('now')), prompt_id INTEGER, session_id INTEGER
        );
    """)
    store.close()
    read = installed / "gc-read.sh"
    write = installed / "gc-write.sh"
    first = run(write, "register-session", env=first_env, cwd=cwd)
    second = run(write, "register-session", env=second_env, cwd=cwd)
    first_id = first.split("|")[0]
    second_id = second.split("|")[0]
    assert first_id != second_id
    assert run(write, "register-session", env=first_env, cwd=cwd) == first
    assert run(read, "current-session", first_id, env=first_env, cwd=cwd) == first
    run(read, "current-session", second_id, env=first_env, cwd=cwd, ok=False)
    run(write, "update-session-summary", first_id, env=first_env, cwd=cwd,
        stdin="Completed alpha")
    run(write, "update-session-summary", second_id, env=second_env, cwd=cwd,
        stdin="Completed beta")
    context = json.loads(run(read, "today-context", env=first_env, cwd=cwd))
    assert {row["summary"] for row in context["sessions"]} == {"Completed alpha", "Completed beta"}
    assert context["counts"] == {"sessions": 2, "prompts": 0, "commits": 0}
    draft = Path(temp) / "daily.json"

    def make_draft(context, summary):
        draft.write_text(json.dumps(dict(
            project=context["project"], date=context["date"],
            context_revision=context["context_revision"], model="codex", summary=summary,
            synthesis_session_id=context["synthesis_session_id"],
            key_decisions=["Combine both sessions"], prompt_count=context["counts"]["prompts"],
            session_count=context["counts"]["sessions"], commit_count=context["counts"]["commits"],
        )))

    make_draft(context, "Combined alpha and beta")
    run(write, "save-daily-summary", str(draft), env=first_env, cwd=cwd)
    run(write, "save-daily-summary", str(draft), env=second_env, cwd=cwd, ok=False)
    refreshed = json.loads(run(read, "today-context", env=second_env, cwd=cwd))
    assert refreshed["existing_daily"][0]["summary"] == "Combined alpha and beta"
    make_draft(refreshed, "Revised alpha and beta")
    run(write, "save-daily-summary", str(draft), env=second_env, cwd=cwd)
    run(write, "end-session", first_id, env=first_env, cwd=cwd)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT ended_at FROM sessions WHERE id=?", (second_id,)).fetchone()[0] is None
    assert conn.execute("SELECT summary FROM daily_summaries").fetchone()[0] == "Revised alpha and beta"
    assert conn.execute("SELECT summary FROM daily_summaries_superseded").fetchone()[0] == "Combined alpha and beta"
    conn.close()
    assert run(read, "current-session", env=first_env, cwd=cwd) == first
    assert run(write, "register-session", env=first_env, cwd=cwd) == first

print("PASS installed workflow: distinct identities, both summaries, exact counts, stale-write rejection, archive, isolated closure and resume")
