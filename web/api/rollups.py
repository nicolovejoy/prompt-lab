"""GET /api/rollups — weekly rollups with optional project filter."""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

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

        params = parse_qs(urlparse(self.path).query)
        project = params.get("project", [None])[0]
        limit = params.get("limit", ["20"])[0]

        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)

        sql = f"SELECT * FROM weekly_rollups WHERE {' AND '.join(clauses)} ORDER BY week_start DESC LIMIT ?"
        args.append(int(limit))

        rows = turso_query(sql, args)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({"rollups": rows}).encode())
