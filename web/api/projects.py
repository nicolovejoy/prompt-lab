"""GET /api/projects — all known project names."""

import json
from http.server import BaseHTTPRequestHandler

from _auth import is_authenticated
from _turso import turso_query


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        rows = turso_query("""
            SELECT DISTINCT project FROM (
                SELECT DISTINCT project FROM daily_summaries
                UNION SELECT DISTINCT project FROM intentions
                UNION SELECT DISTINCT project FROM weekly_rollups
            ) ORDER BY project
        """)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({
            "projects": [r["project"] for r in rows]
        }).encode())
