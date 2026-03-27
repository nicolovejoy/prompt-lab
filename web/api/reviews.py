"""GET /api/reviews — review snapshots."""

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
        review_type = params.get("type", [None])[0]
        limit = params.get("limit", ["10"])[0]

        clauses, args = ["1=1"], []
        if review_type:
            clauses.append("review_type = ?")
            args.append(review_type)

        sql = f"""SELECT id, review_type, date, subject, content_text,
                  content_markdown, model FROM review_snapshots
                  WHERE {' AND '.join(clauses)}
                  ORDER BY created_at DESC LIMIT ?"""
        args.append(int(limit))

        rows = turso_query(sql, args)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({"reviews": rows}).encode())
