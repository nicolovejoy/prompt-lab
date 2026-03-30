"""GET /api/project?name=X — single project detail."""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import turso_query, resolve_project_names


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        params = parse_qs(urlparse(self.path).query)
        name = params.get("name", [""])[0]
        if not name:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "name parameter required"}).encode())
            return

        # Resolve aliases: combine data from canonical + aliased project names
        names = resolve_project_names(name)
        placeholders = ", ".join("?" for _ in names)

        summaries = turso_query(
            f"SELECT * FROM daily_summaries WHERE project IN ({placeholders}) ORDER BY date DESC LIMIT 30",
            names,
        )
        intentions = turso_query(
            f"SELECT * FROM intentions WHERE project IN ({placeholders}) AND status = ? ORDER BY last_seen DESC",
            names + ["active"],
        )
        snapshot = turso_query(
            f"SELECT * FROM project_snapshots WHERE project IN ({placeholders}) ORDER BY snapshot_date DESC LIMIT 1",
            names,
        )
        rollups = turso_query(
            f"SELECT * FROM weekly_rollups WHERE project IN ({placeholders}) ORDER BY week_start DESC LIMIT 8",
            names,
        )

        # Activity heatmap: all daily summaries for this project (up to 12 months)
        activity = turso_query(
            f"SELECT date, SUM(prompt_count) as prompt_count, SUM(session_count) as session_count, "
            f"SUM(commit_count) as commit_count "
            f"FROM daily_summaries WHERE project IN ({placeholders}) GROUP BY date ORDER BY date ASC",
            names,
        )

        # Inception date: earliest daily summary
        inception = activity[0]["date"] if activity else None

        snapshot_data = None
        if snapshot:
            try:
                snapshot_data = json.loads(snapshot[0].get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                snapshot_data = None

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({
            "name": name,
            "summaries": summaries,
            "intentions": intentions,
            "rollups": rollups,
            "snapshot": snapshot_data,
            "activity": activity,
            "inception": inception,
        }).encode())
