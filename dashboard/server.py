#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing prompts."""

import re
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, jsonify, request, send_file

SCRIPT_DIR = Path(__file__).parent
app = Flask(__name__)
DB_PATH = Path.home() / ".claude" / "prompt-history.db"
SRC_DIR = Path.home() / "src"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
TODOS_CACHE_TTL = 300

_todos_cache = {"data": None, "timestamp": 0}

# Section header patterns (case-insensitive)
_SECTION_PATTERNS = [
    (re.compile(r"^##\s+(Next\s+Steps|Current\s+Next\s+Steps|What'?s\s+Next|Next\s+Session\s+TODO)\s*$", re.IGNORECASE), "next_steps"),
    (re.compile(r"^##\s+Backlog\s*$", re.IGNORECASE), "backlog"),
    (re.compile(r"^##\s+Planned\s+Features\s*$", re.IGNORECASE), "planned"),
]


def _parse_todo_sections(text):
    """Parse markdown text for todo sections, returning list of {section, text}."""
    results = []
    current_section = None

    for line in text.splitlines():
        stripped = line.strip()

        # Check if this line is a section header
        if stripped.startswith("## "):
            current_section = None
            for pattern, section_name in _SECTION_PATTERNS:
                if pattern.match(stripped):
                    current_section = section_name
                    break
            continue

        # If we're in a tracked section, collect items
        if current_section and stripped:
            # Match list items: "- item" or "1. item"
            m = re.match(r"^(?:-|\d+\.)\s+(.+)$", stripped)
            if m:
                item_text = m.group(1)
                # Skip done/shipped items
                if re.match(r"^(DONE|SHIPPED)\b", item_text, re.IGNORECASE):
                    continue
                results.append({"section": current_section, "text": item_text})

    return results


def _scan_todos():
    """Scan CLAUDE.md and MEMORY.md files for todo items."""
    todos = []

    # Scan ~/src/*/CLAUDE.md
    for claude_md in sorted(SRC_DIR.glob("*/CLAUDE.md")):
        project = claude_md.parent.name
        try:
            text = claude_md.read_text()
        except OSError:
            continue
        for item in _parse_todo_sections(text):
            todos.append({
                "project": project,
                "section": item["section"],
                "text": item["text"],
                "source": "CLAUDE.md",
            })

    # Scan ~/.claude/projects/*/memory/MEMORY.md
    for memory_md in sorted(CLAUDE_PROJECTS_DIR.glob("*/memory/MEMORY.md")):
        # Extract project from path like -Users-nico-src-<project>
        dir_name = memory_md.parent.parent.name
        m = re.search(r"-Users-\w+-src-(.+)$", dir_name)
        project = m.group(1) if m else dir_name
        try:
            text = memory_md.read_text()
        except OSError:
            continue
        for item in _parse_todo_sections(text):
            todos.append({
                "project": project,
                "section": item["section"],
                "text": item["text"],
                "source": "MEMORY.md",
            })

    return todos


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@app.route("/")
def index():
    return send_file(SCRIPT_DIR / "index.html")


@app.route("/about")
def about():
    return send_file(SCRIPT_DIR / "about.html")


@app.route("/api/prompts")
def list_prompts():
    project = request.args.get("project")

    query = "SELECT * FROM prompts WHERE 1=1"
    params = []

    if project:
        query += " AND project = ?"
        params.append(project)

    query += " ORDER BY timestamp DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify([dict(row) for row in rows])


@app.route("/api/prompts/<int:prompt_id>", methods=["PATCH"])
def update_prompt(prompt_id):
    data = request.json

    updates = []
    params = []
    for field in ["tags", "notes"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field] if data[field] != "" else None)

    if updates:
        params.append(prompt_id)
        with get_db() as conn:
            conn.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return jsonify({"ok": True})


@app.route("/api/projects")
def list_projects():
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT project FROM prompts ORDER BY project").fetchall()
    return jsonify([row["project"] for row in rows])


@app.route("/api/sessions")
def list_sessions():
    project = request.args.get("project")

    # Only show sessions that have summaries
    query = "SELECT * FROM sessions WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''"
    params = []

    if project:
        query += " AND project = ?"
        params.append(project)

    query += " ORDER BY started_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        sessions = [dict(row) for row in rows]

        if sessions:
            session_ids = [s['id'] for s in sessions]
            placeholders = ','.join('?' * len(session_ids))
            commits = conn.execute(
                f"SELECT session_id, hash, message FROM commits WHERE session_id IN ({placeholders}) ORDER BY timestamp",
                session_ids
            ).fetchall()

            commits_by_session = {}
            for c in commits:
                commits_by_session.setdefault(c['session_id'], []).append(
                    {'hash': c['hash'], 'message': c['message']}
                )

            for session in sessions:
                session['commits'] = commits_by_session.get(session['id'], [])

    return jsonify(sessions)


@app.route("/api/daily-summaries")
def list_daily_summaries():
    project = request.args.get("project")
    query = "SELECT * FROM daily_summaries WHERE 1=1"
    params = []
    if project:
        query += " AND project = ?"
        params.append(project)
    query += " ORDER BY date DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/intentions")
def list_intentions():
    project = request.args.get("project")
    status = request.args.get("status", "active")
    query = "SELECT * FROM intentions WHERE 1=1"
    params = []
    if project:
        query += " AND project = ?"
        params.append(project)
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY last_seen DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/themes")
def list_themes():
    status = request.args.get("status", "active")
    query = "SELECT * FROM themes WHERE 1=1"
    params = []
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY last_seen DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return jsonify([dict(row) for row in rows])


# TODO: Consolidate into a single query with subselects
@app.route("/api/stats/combined")
def combined_stats():
    with get_db() as conn:
        prompts_total = conn.execute("SELECT COUNT(*) as n FROM prompts").fetchone()["n"]
        sessions_total = conn.execute("SELECT COUNT(*) as n FROM sessions WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''").fetchone()["n"]
        daily_total = conn.execute("SELECT COUNT(*) as n FROM daily_summaries").fetchone()["n"]
        intentions_active = conn.execute("SELECT COUNT(*) as n FROM intentions WHERE status = 'active'").fetchone()["n"]
        themes_active = conn.execute("SELECT COUNT(*) as n FROM themes WHERE status = 'active'").fetchone()["n"]
    # Todos count (use cache if fresh, don't force scan)
    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now
    todos_total = len(_todos_cache["data"])

    return jsonify({
        "prompts": {"total": prompts_total},
        "sessions": {"total": sessions_total},
        "daily": {"total": daily_total},
        "intentions": {"active": intentions_active},
        "themes": {"active": themes_active},
        "todos": {"total": todos_total}
    })


@app.route("/api/todos")
def list_todos():
    force = request.args.get("force") == "1"
    project = request.args.get("project")

    now = time.time()
    if force or _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now

    todos = _todos_cache["data"]
    if project:
        todos = [t for t in todos if t["project"] == project]

    return jsonify(todos)


@app.route("/api/sessions/<int:session_id>", methods=["PATCH"])
def update_session(session_id):
    data = request.json

    updates = []
    params = []
    for field in ["summary"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field] if data[field] != "" else None)

    if updates:
        params.append(session_id)
        with get_db() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return jsonify({"ok": True})


@app.route("/api/info")
def info():
    """Return app info including last commit date."""
    repo_dir = SCRIPT_DIR.parent
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        commit_date = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        commit_date = None
    return jsonify({"commit_date": commit_date})


if __name__ == "__main__":
    print(f"Using database: {DB_PATH}")
    print("Open http://localhost:5111")
    app.run(port=5111, debug=True)
