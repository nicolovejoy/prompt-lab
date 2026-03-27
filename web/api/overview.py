"""GET /api/overview — week stats, project cards, intentions."""

import json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler

from _auth import is_authenticated, unauthorized_response
from _turso import turso_query


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        summaries = turso_query(
            "SELECT * FROM daily_summaries WHERE date >= ? ORDER BY date DESC",
            [week_ago],
        )
        intentions = turso_query(
            "SELECT * FROM intentions WHERE status = ? ORDER BY last_seen DESC",
            ["active"],
        )
        snapshots = turso_query(
            "SELECT * FROM project_snapshots ORDER BY snapshot_date DESC"
        )

        # Aggregate week stats
        week = {"prompts": 0, "sessions": 0, "commits": 0}
        by_project = {}
        for s in summaries:
            p = s["project"]
            week["prompts"] += int(s.get("prompt_count") or 0)
            week["sessions"] += int(s.get("session_count") or 0)
            week["commits"] += int(s.get("commit_count") or 0)
            if p not in by_project:
                by_project[p] = {"summaries": [], "days": 0}
            by_project[p]["summaries"].append(s)
            by_project[p]["days"] += 1

        intentions_by_project = {}
        for i in intentions:
            intentions_by_project.setdefault(i["project"], []).append(i)

        latest_snapshots = {}
        for s in snapshots:
            if s["project"] not in latest_snapshots:
                latest_snapshots[s["project"]] = s

        # All known projects
        all_projects = sorted(
            set(by_project) | set(intentions_by_project)
        )

        self._json({
            "week": week,
            "by_project": by_project,
            "intentions_by_project": {
                p: [{"intention": i["intention"], "status": i["status"],
                     "first_seen": i["first_seen"], "last_seen": i["last_seen"]}
                    for i in items]
                for p, items in intentions_by_project.items()
            },
            "latest_snapshots": {
                p: s.get("data") for p, s in latest_snapshots.items()
            },
            "all_projects": all_projects,
        })

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
