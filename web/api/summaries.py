"""GET /api/summaries — daily summaries with optional filters."""

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
        since = params.get("since", [None])[0]
        until = params.get("until", [None])[0]
        limit = params.get("limit", [None])[0]

        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)
        if since:
            clauses.append("date >= ?")
            args.append(since)
        if until:
            clauses.append("date <= ?")
            args.append(until)

        sql = f"SELECT * FROM daily_summaries WHERE {' AND '.join(clauses)} ORDER BY date DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(int(limit))

        rows = turso_query(sql, args)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({"summaries": rows}).encode())
