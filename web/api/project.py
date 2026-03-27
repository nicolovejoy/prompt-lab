"""GET /api/project?name=X — single project detail."""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import turso_query


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

        summaries = turso_query(
            "SELECT * FROM daily_summaries WHERE project = ? ORDER BY date DESC LIMIT 14",
            [name],
        )
        intentions = turso_query(
            "SELECT * FROM intentions WHERE project = ? AND status = ? ORDER BY last_seen DESC",
            [name, "active"],
        )
        snapshot = turso_query(
            "SELECT * FROM project_snapshots WHERE project = ? ORDER BY snapshot_date DESC LIMIT 1",
            [name],
        )
        rollups = turso_query(
            "SELECT * FROM weekly_rollups WHERE project = ? ORDER BY week_start DESC LIMIT 4",
            [name],
        )

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
        }).encode())
