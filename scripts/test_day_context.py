"""Behavior tests for the whole-day /handoff synthesis context."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
HELPER = ROOT / "workflow" / "bin" / "_gc_day_context.py"
spec = importlib.util.spec_from_file_location("gc_day_context", HELPER)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)

from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

failures = []


def check(label, condition):
    print(("PASS  " if condition else "FAIL  ") + label)
    if not condition:
        failures.append(label)


check(
    "Pacific date remains the prior day just before Pacific midnight",
    module.lab_date(datetime(2026, 9, 14, 6, 59, tzinfo=timezone.utc)) == "2026-09-13",
)
check(
    "Pacific date advances at Pacific midnight",
    module.lab_date(datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)) == "2026-09-14",
)

# Deliberately disagree with Pacific: the helper must not use host localtime.
os.environ["TZ"] = "Asia/Tokyo"
if hasattr(time, "tzset"):
    time.tzset()

with tempfile.TemporaryDirectory(prefix="day-context-") as tmp:
    store = SqliteKnowledgeStore(Path(tmp) / "history.db")
    store.migrate()
    conn = store.conn
    conn.executescript("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
            started_at TEXT, ended_at TEXT, summary TEXT, utility INTEGER,
            hostname TEXT
        );
        CREATE TABLE prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, project TEXT,
            prompt TEXT NOT NULL, outcome TEXT, utility INTEGER, tags TEXT,
            context TEXT, hostname TEXT, session_id INTEGER
        );
        CREATE TABLE commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT, message TEXT,
            timestamp TEXT, prompt_id INTEGER, session_id INTEGER
        );
    """)
    sessions = [
        ("prompt-lab", "2026-09-14 06:30:00", "Claude completed alpha", "mini"),
        ("prompt-lab", "2026-09-14 06:45:00", "Codex completed beta", "laptop"),
    ]
    conn.executemany(
        "INSERT INTO sessions(project, started_at, summary, hostname) VALUES(?,?,?,?)",
        sessions,
    )
    session_ids = [r[0] for r in conn.execute("SELECT id FROM sessions ORDER BY id")]
    prompts = [
        ("2026-09-14 06:40:00", "prompt-lab", f"prompt {i} " + "x" * 600,
         session_ids[i % 2])
        for i in range(60)
    ]
    conn.executemany(
        "INSERT INTO prompts(timestamp, project, prompt, session_id) VALUES(?,?,?,?)",
        prompts,
    )
    commits = [
        (f"hash{i}", f"commit {i}", "2026-09-14 06:50:00", session_ids[i % 2])
        for i in range(3)
    ]
    conn.executemany(
        "INSERT INTO commits(hash, message, timestamp, session_id) VALUES(?,?,?,?)",
        commits,
    )
    conn.commit()

    result = module.build_context(store, "prompt-lab", "2026-09-13")
    check("whole-day context contains both agent session summaries",
          [s["summary"] for s in result["sessions"]]
          == ["Claude completed alpha", "Codex completed beta"])
    check("counts include every row despite bounded prompt output",
          result["counts"] == {"prompts": 60, "sessions": 2, "commits": 3})
    check("prompt output is bounded", len(result["prompts"]) == module.MAX_PROMPTS)
    check("row truncation is reported honestly",
          result["truncation"]["prompts_omitted"] == 10)
    check("text clipping is reported honestly",
          result["truncation"]["prompts_clipped"] == module.MAX_PROMPTS)
    check("all session summaries are prioritized",
          result["truncation"]["session_summaries_omitted"] == 0)
    # A second copy of one commit must not inflate the count.
    conn.execute("INSERT INTO commits(hash,message,timestamp,session_id) VALUES(?,?,?,?)",
                 ("hash0", "duplicate", "2026-09-14 06:50:00", session_ids[0]))
    conn.execute("INSERT INTO sessions(project,started_at,summary) VALUES(?,?,?)",
                 ("prompt-lab", "2026-09-13 06:00:00", "Work spanning midnight"))
    crossing = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO prompts(timestamp,project,prompt,session_id) VALUES(?,?,?,?)",
                 ("2026-09-13 07:00:00", "prompt-lab", "start boundary", crossing))
    conn.execute("INSERT INTO prompts(timestamp,project,prompt,session_id) VALUES(?,?,?,?)",
                 ("2026-09-14 07:00:00", "prompt-lab", "next day", crossing))
    conn.execute("INSERT INTO sessions(project,started_at,summary) VALUES(?,?,?)",
                 ("unrelated", "2026-09-14 06:00:00", "Must not appear"))
    conn.commit()
    result = module.build_context(store, "prompt-lab", "2026-09-13")
    check("commit hashes are counted once", result["counts"]["commits"] == 3)
    check("Pacific bounds include start and exclude end on a Tokyo host",
          result["counts"]["prompts"] == 61)
    check("prior-day session with today's activity contributes its summary",
          any(s["summary"] == "Work spanning midnight" for s in result["sessions"]))
    check("unrelated projects excluded", result["counts"]["sessions"] == 3)

    def payload(context, summary):
        return dict(project=context["project"], date=context["date"], summary=summary,
                    context_revision=context["context_revision"], model="codex",
                    key_decisions=["Preserve both agents' work"],
                    prompt_count=context["counts"]["prompts"],
                    session_count=context["counts"]["sessions"],
                    commit_count=context["counts"]["commits"])

    first = payload(result, "Claude alpha, Codex beta, and earlier work")
    module.save_summary(store, "prompt-lab", first)
    try:
        module.save_summary(store, "prompt-lab", payload(result, "Stale second writer"))
    except module.StaleContextError:
        check("a stale parallel writer cannot overwrite newer daily prose", True)
    else:
        check("a stale parallel writer cannot overwrite newer daily prose", False)
    refreshed = module.build_context(store, "prompt-lab", "2026-09-13")
    check("refresh includes the previous daily account",
          refreshed["existing_daily"][0]["summary"] == first["summary"])
    wrong_counts = payload(refreshed, "Bad counts")
    wrong_counts["prompt_count"] = 1
    try:
        module.save_summary(store, "prompt-lab", wrong_counts)
    except ValueError:
        check("clipped-context counts cannot replace exact counts", True)
    else:
        check("clipped-context counts cannot replace exact counts", False)
    module.save_summary(store, "prompt-lab", payload(refreshed, "Combined revised account"))
    archived = conn.execute("SELECT summary FROM daily_summaries_superseded").fetchall()
    check("replaced prose is archived", [r[0] for r in archived] == [first["summary"]])
    changed = module.build_context(store, "prompt-lab", "2026-09-13")
    conn.execute("UPDATE sessions SET summary='Additional Claude work' WHERE id=?",
                 (session_ids[0],))
    conn.commit()
    try:
        module.save_summary(store, "prompt-lab", payload(changed, "Missing latest session work"))
    except module.StaleContextError:
        check("new session work invalidates pending synthesis", True)
    else:
        check("new session work invalidates pending synthesis", False)
    conn.execute("INSERT INTO sessions(project,started_at,summary) VALUES(?,?,?)",
                 ("prompt-lab", "2026-09-14T06:30:00Z", None))
    conn.execute("INSERT INTO sessions(project,started_at,summary) VALUES(?,?,?)",
                 ("prompt-lab", "2026-09-13T23:45:00-07:00", "Offset timestamp"))
    conn.commit()
    normalized = module.build_context(store, "prompt-lab", "2026-09-13")
    check("ISO timestamps are normalized before date bucketing",
          normalized["counts"]["sessions"] == 5)
    check("unsummarized sessions remain explicit in context",
          len(normalized["sessions"]) == 5 and
          any(s["summary"] == "" for s in normalized["sessions"]))
    conn.execute("INSERT INTO sessions(project,started_at,summary) VALUES(?,?,?)",
                 ("prompt-lab", "2026-09-13 06:00:00", "Codex conversation after midnight"))
    overnight_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    overnight = module.build_context(store, "prompt-lab", "2026-09-13", overnight_id)
    check("validated overnight caller contributes without a prompt hook",
          overnight["counts"]["sessions"] == 6 and
          any(s["id"] == overnight_id for s in overnight["sessions"]))
    overnight_draft = payload(overnight, "All six sessions including overnight Codex")
    overnight_draft["synthesis_session_id"] = overnight_id
    module.save_summary(store, "prompt-lab", overnight_draft)
    check("overnight caller counts round-trip through guarded save", True)
    locked_context = module.build_context(store, "prompt-lab", "2026-09-13")
    original_build = module.build_context
    competitor = sqlite3.connect(Path(tmp) / "history.db", timeout=0)

    def probe_locked_context(*args, **kwargs):
        result = original_build(*args, **kwargs)
        try:
            competitor.execute("UPDATE sessions SET summary='racing change' WHERE id=?",
                               (session_ids[0],))
            competitor.commit()
        except sqlite3.OperationalError as exc:
            competitor.rollback()
            check("competing write is blocked throughout revision check and save",
                  "locked" in str(exc))
        else:
            check("competing write is blocked throughout revision check and save", False)
        return result

    module.build_context = probe_locked_context
    try:
        module.save_summary(store, "prompt-lab", payload(locked_context, "Serialized save"))
    finally:
        module.build_context = original_build
        competitor.close()
    store.close()

check("spring DST day spans 23 hours", module.day_bounds("2026-03-08") ==
      ("2026-03-08 08:00:00", "2026-03-09 07:00:00"))
check("fall DST day spans 25 hours", module.day_bounds("2026-11-01") ==
      ("2026-11-01 07:00:00", "2026-11-02 08:00:00"))

if failures:
    raise SystemExit(f"{len(failures)} failure(s): {failures}")
print("All day-context tests passed.")
