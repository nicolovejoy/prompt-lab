#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing prompts."""

import json
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, jsonify, request, send_file

# Import shared todo scanner
sys.path.insert(0, str(Path(__file__).parent.parent))
from todos import _scan_todos

SCRIPT_DIR = Path(__file__).parent
app = Flask(__name__)
DB_PATH = Path.home() / ".claude" / "prompt-history.db"
CONFIG_PATH = Path.home() / ".claude" / "ground-control.json"
TODOS_CACHE_TTL = 300

_todos_cache = {"data": None, "timestamp": 0}


def _load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Migration system
# ---------------------------------------------------------------------------

def _seed_from_config(conn):
    """One-time: seed ignored projects from ground-control.json hidden_projects."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        for name in cfg.get("hidden_projects", []):
            conn.execute(
                "INSERT OR IGNORE INTO projects (name, status) VALUES (?, 'ignored')",
                [name]
            )
    except (OSError, json.JSONDecodeError):
        pass


MIGRATIONS = {
    "001_add_projects": """
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            category    TEXT,
            path        TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
    """,
    "002_seed_from_config": _seed_from_config,
    "003_rename_muted_to_ignored": "UPDATE projects SET status = 'ignored' WHERE status = 'muted';",
}


def run_migrations():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id         TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        applied = {row["id"] for row in conn.execute("SELECT id FROM migrations").fetchall()}

        for mid, action in sorted(MIGRATIONS.items()):
            if mid in applied:
                continue
            if callable(action):
                action(conn)
            else:
                conn.executescript(action)
            conn.execute("INSERT INTO migrations (id) VALUES (?)", [mid])
            conn.commit()


# ---------------------------------------------------------------------------
# DB context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_file(SCRIPT_DIR / "index.html")


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


@app.route("/api/projects/all")
def all_projects():
    """Return all distinct project names across all tables + todos."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT project FROM (
                SELECT DISTINCT project FROM prompts
                UNION SELECT DISTINCT project FROM sessions WHERE project IS NOT NULL
                UNION SELECT DISTINCT project FROM intentions WHERE project IS NOT NULL
            ) ORDER BY project
        """).fetchall()
    db_projects = {row["project"] for row in rows}

    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now
    for t in _todos_cache["data"]:
        db_projects.add(t["project"])

    return jsonify(sorted(db_projects))


@app.route("/api/project/<path:name>")
def project_detail(name):
    """Single-project detail data."""
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", [name])
        conn.commit()

        project_row = conn.execute(
            "SELECT * FROM projects WHERE name = ?", [name]
        ).fetchone()

        session_count = conn.execute("""
            SELECT COUNT(*) as n FROM sessions
            WHERE project = ? AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
        """, [name]).fetchone()["n"]

        last_session_row = conn.execute("""
            SELECT summary, started_at FROM sessions
            WHERE project = ? AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
            ORDER BY started_at DESC LIMIT 1
        """, [name]).fetchone()

        intention_rows = conn.execute("""
            SELECT intention FROM intentions
            WHERE project = ? AND status = 'active'
            ORDER BY last_seen DESC LIMIT 3
        """, [name]).fetchall()

    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now

    project_todos = [t for t in _todos_cache["data"] if t["project"] == name]
    todo_count = len(project_todos)
    next_steps = [t["text"] for t in project_todos if t["section"] == "next_steps"][:5]

    return jsonify({
        "name": name,
        "status": project_row["status"] if project_row else "active",
        "category": project_row["category"] if project_row else None,
        "notes": project_row["notes"] if project_row else None,
        "created_at": project_row["created_at"] if project_row else None,
        "session_count": session_count,
        "todo_count": todo_count,
        "last_session": dict(last_session_row) if last_session_row else None,
        "intentions": [row["intention"] for row in intention_rows],
        "next_steps": next_steps,
    })


@app.route("/api/projects/<path:name>", methods=["PATCH"])
def update_project(name):
    data = request.json

    updates = []
    params = []
    for field in ["status", "category", "notes"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])

    if updates:
        params.append(name)
        with get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", [name])
            conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE name = ?", params)
            conn.commit()

    return jsonify({"ok": True})


@app.route("/api/sessions")
def list_sessions():
    project = request.args.get("project")

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


@app.route("/api/todos")
def list_todos():
    force = request.args.get("force") == "1"
    project = request.args.get("project")

    now = time.time()
    if force or _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now

    todos = _todos_cache["data"]

    # Filter out ignored/archived projects
    with get_db() as conn:
        non_active = {row["name"] for row in conn.execute(
            "SELECT name FROM projects WHERE status != 'active'"
        ).fetchall()}
    todos = [t for t in todos if t["project"] not in non_active]

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


@app.route("/api/overview")
def overview():
    """Per-project cards data for the overview."""
    with get_db() as conn:
        week_prompts = conn.execute(
            "SELECT COUNT(*) as n FROM prompts WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]
        week_sessions = conn.execute(
            "SELECT COUNT(*) as n FROM sessions WHERE started_at >= datetime('now', '-7 days') AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''"
        ).fetchone()["n"]
        week_commits = conn.execute(
            "SELECT COUNT(*) as n FROM commits WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]

        # All projects from DB
        project_rows = conn.execute("""
            SELECT DISTINCT project FROM (
                SELECT DISTINCT project FROM prompts
                UNION SELECT DISTINCT project FROM sessions WHERE project IS NOT NULL
                UNION SELECT DISTINCT project FROM intentions WHERE project IS NOT NULL
            ) ORDER BY project
        """).fetchall()
        db_projects = {row["project"] for row in project_rows}

        # Project statuses from projects table
        project_statuses = {}
        for row in conn.execute("SELECT name, status FROM projects").fetchall():
            project_statuses[row["name"]] = row["status"]

        # Per-project: session count + last_started
        session_data = {}
        for row in conn.execute("""
            SELECT project,
                   COUNT(*) as session_count,
                   MAX(started_at) as last_started
            FROM sessions
            WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
            GROUP BY project
        """).fetchall():
            session_data[row["project"]] = {
                "session_count": row["session_count"],
                "last_started": row["last_started"],
            }

        # Last session summary per project
        last_sessions = {}
        for row in conn.execute("""
            SELECT s.project, s.summary, s.started_at
            FROM sessions s
            INNER JOIN (
                SELECT project, MAX(started_at) as max_start
                FROM sessions
                WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
                GROUP BY project
            ) latest ON s.project = latest.project AND s.started_at = latest.max_start
            WHERE s.ended_at IS NOT NULL AND s.summary IS NOT NULL AND s.summary != ''
        """).fetchall():
            last_sessions[row["project"]] = {
                "summary": row["summary"],
                "started_at": row["started_at"],
            }

        # Active intentions per project
        intentions_by_project = {}
        for row in conn.execute(
            "SELECT project, intention FROM intentions WHERE status = 'active' ORDER BY last_seen DESC"
        ).fetchall():
            intentions_by_project.setdefault(row["project"], []).append(row["intention"])

        # Last intention seen per project
        intention_last_seen = {}
        for row in conn.execute(
            "SELECT project, MAX(last_seen) as last_seen FROM intentions WHERE status = 'active' GROUP BY project"
        ).fetchall():
            intention_last_seen[row["project"]] = row["last_seen"]

    # Todos
    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now

    todos_by_project = {}
    for t in _todos_cache["data"]:
        todos_by_project[t["project"]] = todos_by_project.get(t["project"], 0) + 1
        db_projects.add(t["project"])

    # Build project cards
    projects = []
    for name in db_projects:
        sd = session_data.get(name, {})
        ls = last_sessions.get(name)
        intents = intentions_by_project.get(name, [])
        todo_count = todos_by_project.get(name, 0)
        session_count = sd.get("session_count", 0)

        if session_count == 0 and todo_count == 0:
            continue

        if name.startswith("/"):
            continue

        candidates = []
        if sd.get("last_started"):
            candidates.append(sd["last_started"])
        if intention_last_seen.get(name):
            candidates.append(intention_last_seen[name])
        last_activity = max(candidates) if candidates else None

        status = project_statuses.get(name, "active")

        projects.append({
            "name": name,
            "status": status,
            "last_session": ls,
            "session_count": session_count,
            "todo_count": todo_count,
            "intentions": intents[:3],
            "last_activity": last_activity,
        })

    # Sort by last_activity DESC (None last)
    projects.sort(key=lambda p: p["last_activity"] or "", reverse=True)

    return jsonify({
        "week": {"sessions": week_sessions, "prompts": week_prompts, "commits": week_commits},
        "projects": projects,
    })


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


@app.route("/api/settings")
def get_settings():
    return jsonify(_load_config())


if __name__ == "__main__":
    print(f"Using database: {DB_PATH}")
    print("Open http://localhost:5111")
    run_migrations()
    app.run(port=5111, debug=True)
