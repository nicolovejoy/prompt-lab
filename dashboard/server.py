#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing and rating prompts."""

import sqlite3
import subprocess
from pathlib import Path
from flask import Flask, jsonify, request, send_file

SCRIPT_DIR = Path(__file__).parent
app = Flask(__name__)
DB_PATH = Path.home() / ".claude" / "prompt-history.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


@app.route("/api/prompts/<int:prompt_id>", methods=["PATCH"])
def update_prompt(prompt_id):
    data = request.json
    conn = get_db()

    updates = []
    params = []
    for field in ["tags", "notes"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field] if data[field] != "" else None)

    if updates:
        params.append(prompt_id)
        conn.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/projects")
def list_projects():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT project FROM prompts ORDER BY project").fetchall()
    conn.close()
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

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    sessions = [dict(row) for row in rows]

    # Attach commits to each session
    for session in sessions:
        commits = conn.execute(
            "SELECT hash, message FROM commits WHERE session_id = ? ORDER BY timestamp",
            (session['id'],)
        ).fetchall()
        session['commits'] = [dict(c) for c in commits]

    conn.close()

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
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
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
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
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
    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/stats/combined")
def combined_stats():
    conn = get_db()
    prompts_total = conn.execute("SELECT COUNT(*) as n FROM prompts").fetchone()["n"]
    sessions_total = conn.execute("SELECT COUNT(*) as n FROM sessions WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''").fetchone()["n"]
    daily_total = conn.execute("SELECT COUNT(*) as n FROM daily_summaries").fetchone()["n"]
    intentions_active = conn.execute("SELECT COUNT(*) as n FROM intentions WHERE status = 'active'").fetchone()["n"]
    themes_active = conn.execute("SELECT COUNT(*) as n FROM themes WHERE status = 'active'").fetchone()["n"]
    conn.close()
    return jsonify({
        "prompts": {"total": prompts_total},
        "sessions": {"total": sessions_total},
        "daily": {"total": daily_total},
        "intentions": {"active": intentions_active},
        "themes": {"active": themes_active}
    })


@app.route("/api/sessions/<int:session_id>", methods=["PATCH"])
def update_session(session_id):
    data = request.json
    conn = get_db()

    updates = []
    params = []
    for field in ["summary"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field] if data[field] != "" else None)

    if updates:
        params.append(session_id)
        conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
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
