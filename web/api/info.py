"""GET /api/info — deploy metadata and data freshness."""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

from auth_helper import is_authenticated
from turso_helper import turso_query

# Evaluated at import time (cold start ≈ deploy time)
_BUILD_TIME = datetime.now(timezone.utc).strftime("%b %-d %H:%M UTC")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
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

        # Project count
        project_count = 0
        try:
            rows = turso_query(
                "SELECT COUNT(DISTINCT project) as cnt FROM daily_summaries"
            )
            if rows:
                project_count = int(rows[0].get("cnt", 0))
        except Exception:
            pass

        self.send_response(200)
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
