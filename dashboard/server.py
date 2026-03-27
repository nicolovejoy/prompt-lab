#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing prompts."""

import json
import subprocess
import sys
import time
from pathlib import Path
from flask import Flask, jsonify, request, send_file

# Import shared todo scanner
sys.path.insert(0, str(Path(__file__).parent.parent))
from todos import _scan_todos
from store import get_store

SCRIPT_DIR = Path(__file__).parent
app = Flask(__name__)
CONFIG_PATH = Path.home() / ".claude" / "ground-control.json"
TODOS_CACHE_TTL = 300

_todos_cache = {"data": None, "timestamp": 0}


def _load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _get_cached_todos():
    now = time.time()
    if _todos_cache["data"] is None or (now - _todos_cache["timestamp"]) > TODOS_CACHE_TTL:
        _todos_cache["data"] = _scan_todos()
        _todos_cache["timestamp"] = now
    return _todos_cache["data"]


# ---------------------------------------------------------------------------
# Migration system (for tables not managed by the store)
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
    "004_add_token_count": "ALTER TABLE sessions ADD COLUMN token_count INTEGER;",
    "005_add_hostname": """
        ALTER TABLE prompts ADD COLUMN hostname TEXT;
        ALTER TABLE sessions ADD COLUMN hostname TEXT;
    """,
}


def run_migrations():
    """Run dashboard-specific migrations (projects table, etc.)."""
    store = get_store()
    conn = store.conn
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

    # Also run store migrations (new tables)
    store.migrate()
    store.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_file(SCRIPT_DIR / "index.html")


@app.route("/api/prompts")
def list_prompts():
    project = request.args.get("project")
    with get_store() as store:
        rows = store.get_prompts(project=project)
    return jsonify(rows)


@app.route("/api/prompts/<int:prompt_id>", methods=["PATCH"])
def update_prompt(prompt_id):
    data = request.json
    fields = {f: data[f] for f in ["tags", "notes"] if f in data}
    if fields:
        with get_store() as store:
            store.update_prompt(prompt_id, **fields)
    return jsonify({"ok": True})


@app.route("/api/projects")
def list_projects():
    with get_store() as store:
        rows = store.get_prompts()
    projects = sorted({r["project"] for r in rows if r.get("project")})
    return jsonify(projects)


@app.route("/api/projects/all")
def all_projects():
    """Return all distinct project names across all tables + todos."""
    with get_store() as store:
        db_projects = store.get_all_project_names()
    for t in _get_cached_todos():
        db_projects.add(t["project"])
    return jsonify(sorted(db_projects))


@app.route("/api/project/<path:name>")
def project_detail(name):
    """Single-project detail data."""
    with get_store() as store:
        detail = store.get_project_detail(name)

    todos = _get_cached_todos()
    project_todos = [t for t in todos if t["project"] == name]
    detail["todo_count"] = len(project_todos)
    detail["next_steps"] = [t["text"] for t in project_todos if t["section"] == "next_steps"][:5]

    return jsonify(detail)


@app.route("/api/projects/<path:name>", methods=["PATCH"])
def update_project(name):
    data = request.json
    fields = {f: data[f] for f in ["status", "category", "notes"] if f in data}
    if fields:
        with get_store() as store:
            store.update_project(name, **fields)
    return jsonify({"ok": True})


@app.route("/api/sessions")
def list_sessions():
    project = request.args.get("project")
    with get_store() as store:
        sessions = store.get_sessions_with_commits(project=project)
    return jsonify(sessions)


@app.route("/api/daily-summaries")
def list_daily_summaries():
    project = request.args.get("project")
    with get_store() as store:
        rows = store.get_daily_summaries(project=project)
    return jsonify(rows)


@app.route("/api/intentions")
def list_intentions():
    project = request.args.get("project")
    status = request.args.get("status", "active")
    with get_store() as store:
        rows = store.get_intentions(project=project, status=status)
    return jsonify(rows)


@app.route("/api/todos")
def list_todos():
    force = request.args.get("force") == "1"
    project = request.args.get("project")

    if force:
        _todos_cache["data"] = None

    todos = _get_cached_todos()

    with get_store() as store:
        non_active = store.get_non_active_projects()
    todos = [t for t in todos if t["project"] not in non_active]

    if project:
        todos = [t for t in todos if t["project"] == project]

    return jsonify(todos)


@app.route("/api/sessions/<int:session_id>", methods=["PATCH"])
def update_session(session_id):
    data = request.json
    fields = {f: data[f] for f in ["summary"] if f in data}
    if fields:
        with get_store() as store:
            store.update_session(session_id, **fields)
    return jsonify({"ok": True})


@app.route("/api/overview")
def overview():
    """Per-project cards data for the overview."""
    with get_store() as store:
        overview_data = store.get_overview()
        db_projects = store.get_all_project_names()

    session_data = overview_data["session_data"]
    last_sessions = overview_data["last_sessions"]
    intentions_by_project = overview_data["intentions_by_project"]
    intention_last_seen = overview_data["intention_last_seen"]
    project_statuses = overview_data["project_statuses"]

    # Todos (file-based, outside the store)
    todos = _get_cached_todos()
    todos_by_project = {}
    for t in todos:
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
            "avg_tokens": sd.get("avg_tokens"),
            "peak_tokens": sd.get("peak_tokens"),
        })

    projects.sort(key=lambda p: p["last_activity"] or "", reverse=True)

    return jsonify({
        "week": overview_data["week"],
        "projects": projects,
    })


@app.route("/api/status")
def status():
    """Return synthesizer last-run status."""
    with get_store() as store:
        result = store.get_synthesis_status()
    if result:
        return jsonify(result)
    return jsonify({"last_run": None, "status": None, "error_message": None})


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
    from store.sqlite_store import DEFAULT_DB_PATH
    print(f"Using database: {DEFAULT_DB_PATH}")
    print("Open http://localhost:5111")
    run_migrations()
    app.run(port=5111, debug=True)
