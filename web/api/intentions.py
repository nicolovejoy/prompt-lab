"""GET /api/intentions — intentions with optional project/status filters."""

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
        project = params.get("project", [None])[0]
        status = params.get("status", ["active"])[0]

        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)
        if status and status != "all":
            clauses.append("status = ?")
            args.append(status)

        rows = turso_query(
            f"SELECT * FROM intentions WHERE {' AND '.join(clauses)} ORDER BY last_seen DESC",
            args,
        )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({"intentions": rows}).encode())
