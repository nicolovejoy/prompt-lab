"""GET /api/health — liveness per docs/health-convention.md.

Shallow: 200 {"ok": true}. Deep (?db=1) checks Turso and returns 503 with
{"ok": false, "db": false} when it's unreachable. No auth, no secrets in the
body, no side effects — cheap enough for a 5-minute monitor.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from turso_helper import turso_query


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        deep = parse_qs(urlparse(self.path).query).get("db", [""])[0] == "1"
        status, body = 200, {"ok": True}
        if deep:
            try:
                turso_query("SELECT 1")
                body["db"] = True
            except Exception:
                status, body = 503, {"ok": False, "db": False}
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
