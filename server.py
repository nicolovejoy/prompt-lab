#!/usr/bin/env python3
"""Prompt history dashboard - local web UI for reviewing and rating prompts."""

import sqlite3
import json
from pathlib import Path
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
DB_PATH = Path.home() / ".claude" / "prompt-history.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/api/prompts")
def list_prompts():
    project = request.args.get("project")
    rated = request.args.get("rated")  # "true", "false", or None for all

    query = "SELECT * FROM prompts WHERE 1=1"
    params = []

    if project:
        query += " AND project = ?"
        params.append(project)
    if rated == "true":
        query += " AND utility IS NOT NULL"
    elif rated == "false":
        query += " AND utility IS NULL"

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
    for field in ["utility", "tags", "notes"]:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field] if data[field] != "" else None)

    if updates:
        params.append(prompt_id)
        conn.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/prompts/bulk", methods=["DELETE"])
def delete_prompts():
    data = request.json
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"ok": False, "error": "No ids provided"}), 400

    conn = get_db()
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM prompts WHERE id IN ({placeholders})", ids)
    conn.commit()
    deleted = conn.total_changes
    conn.close()
    return jsonify({"ok": True, "deleted": deleted})


@app.route("/api/projects")
def list_projects():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT project FROM prompts ORDER BY project").fetchall()
    conn.close()
    return jsonify([row["project"] for row in rows])


@app.route("/api/stats")
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as n FROM prompts").fetchone()["n"]
    rated = conn.execute("SELECT COUNT(*) as n FROM prompts WHERE utility IS NOT NULL").fetchone()["n"]
    by_project = conn.execute(
        "SELECT project, COUNT(*) as count FROM prompts GROUP BY project"
    ).fetchall()
    conn.close()

    return jsonify({
        "total": total,
        "rated": rated,
        "unrated": total - rated,
        "by_project": {row["project"]: row["count"] for row in by_project}
    })


if __name__ == "__main__":
    print(f"Using database: {DB_PATH}")
    print("Open http://localhost:5111")
    app.run(port=5111, debug=True)
