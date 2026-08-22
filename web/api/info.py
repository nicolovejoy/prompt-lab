"""GET /api/info — deploy metadata and data freshness."""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

from access_helper import filter_rows, resolve_access
from turso_helper import turso_query

# Evaluated at import time (cold start ≈ deploy time). Sent as ISO 8601;
# the client formats in the user's preferred timezone (currently Pacific).
_BUILD_TIME = datetime.now(timezone.utc).isoformat()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        access = resolve_access(self.headers)
        if access is None:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        commit_sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7]
        vercel_env = os.environ.get("VERCEL_ENV", "development")

        # Data freshness: most recent daily summary date
        data_freshness = None
        try:
            rows = turso_query("SELECT MAX(date) as latest FROM daily_summaries")
            if rows and rows[0].get("latest"):
                data_freshness = rows[0]["latest"]
        except Exception:
            pass

        # Project count — for a reader this counts only their granted
        # projects, since daily_summaries has no per-row visibility of its
        # own and a raw DISTINCT count would leak the ecosystem's size.
        project_count = 0
        try:
            rows = turso_query("SELECT DISTINCT project FROM daily_summaries")
            project_count = len(filter_rows(access, rows))
        except Exception:
            pass

        self.send_response(200)
        if access.set_cookie:
            self.send_header("Set-Cookie", access.set_cookie)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps({
            "commit_sha": commit_sha,
            "vercel_env": vercel_env,
            "data_freshness": data_freshness,
            "project_count": project_count,
            "build_time": _BUILD_TIME,
        }).encode())
