#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing prompts."""

import json
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
CONFIG_PATH = Path.home() / ".claude" / "ground-control.json"
SRC_DIR = Path.home() / "src"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
TODOS_CACHE_TTL = 300

_todos_cache = {"data": None, "timestamp": 0}


def _load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def _get_hidden_projects():
    return set(_load_config().get("hidden_projects", []))

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

    # Add todo projects from cache
    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now
    for t in _todos_cache["data"]:
        db_projects.add(t["project"])

    return jsonify(sorted(db_projects))


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


@app.route("/api/stats/weekly")
def weekly_stats():
    """Return everything the overview briefing needs in one request."""
    with get_db() as conn:
        # Week counts
        week_prompts = conn.execute(
            "SELECT COUNT(*) as n FROM prompts WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]
        week_sessions = conn.execute(
            "SELECT COUNT(*) as n FROM sessions WHERE started_at >= datetime('now', '-7 days') AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''"
        ).fetchone()["n"]
        week_commits = conn.execute(
            "SELECT COUNT(*) as n FROM commits WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]

        # Active projects (from sessions this week)
        active_rows = conn.execute(
            "SELECT DISTINCT project FROM sessions WHERE started_at >= datetime('now', '-7 days') AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != '' ORDER BY project"
        ).fetchall()
        active_projects = [r["project"] for r in active_rows]

        # Recent sessions (last 3)
        recent_rows = conn.execute(
            "SELECT id, project, started_at, summary FROM sessions WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != '' ORDER BY started_at DESC LIMIT 3"
        ).fetchall()
        recent_sessions = [dict(r) for r in recent_rows]

        # Active intentions (limit 3)
        intention_rows = conn.execute(
            "SELECT project, intention FROM intentions WHERE status = 'active' ORDER BY last_seen DESC LIMIT 3"
        ).fetchall()
        intentions = [dict(r) for r in intention_rows]

        # Total active intentions count
        intentions_total = conn.execute(
            "SELECT COUNT(*) as n FROM intentions WHERE status = 'active'"
        ).fetchone()["n"]

        # Active themes (limit 3)
        theme_rows = conn.execute(
            "SELECT theme, projects FROM themes WHERE status = 'active' ORDER BY last_seen DESC LIMIT 3"
        ).fetchall()
        themes = [dict(r) for r in theme_rows]

        # Total active themes count
        themes_total = conn.execute(
            "SELECT COUNT(*) as n FROM themes WHERE status = 'active'"
        ).fetchone()["n"]

    # Todos (use cache)
    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now

    todos_raw = _todos_cache["data"]
    todos_counts = {}
    for t in todos_raw:
        todos_counts[t["project"]] = todos_counts.get(t["project"], 0) + 1

    return jsonify({
        "week": {"sessions": week_sessions, "prompts": week_prompts, "commits": week_commits},
        "active_projects": active_projects,
        "recent_sessions": recent_sessions,
        "intentions": intentions,
        "intentions_total": intentions_total,
        "themes": themes,
        "themes_total": themes_total,
        "todos": todos_counts,
        "todos_total": len(todos_raw),
    })


@app.route("/api/overview")
def overview():
    """Per-project cards data for the overview."""
    with get_db() as conn:
        # Week counts
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

        # Per-project: last session (summary + started_at), session count
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

        # Skip projects with no sessions and no todos (noise)
        if session_count == 0 and todo_count == 0:
            continue

        # Skip full-path project names (duplicates from old data)
        if name.startswith("/"):
            continue

        # Determine last_activity as max of last session or last intention
        candidates = []
        if sd.get("last_started"):
            candidates.append(sd["last_started"])
        if intention_last_seen.get(name):
            candidates.append(intention_last_seen[name])
        last_activity = max(candidates) if candidates else None

        projects.append({
            "name": name,
            "last_session": ls,
            "session_count": session_count,
            "todo_count": todo_count,
            "intentions": intents[:3],
            "last_activity": last_activity,
        })

    # Filter out server-side hidden projects
    hidden = _get_hidden_projects()
    projects = [p for p in projects if p["name"] not in hidden]

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


@app.route("/api/settings", methods=["PATCH"])
def update_settings():
    data = request.json
    cfg = _load_config()
    if "hidden_projects" in data:
        cfg["hidden_projects"] = sorted(set(data["hidden_projects"]))
    _save_config(cfg)
    return jsonify(cfg)


if __name__ == "__main__":
    print(f"Using database: {DB_PATH}")
    print("Open http://localhost:5111")
    app.run(port=5111, debug=True)
