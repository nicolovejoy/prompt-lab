"""GET /api/overview — week stats, project cards, activity."""

import json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler

from auth_helper import is_authenticated
from turso_helper import turso_query


def _load_alias_map():
    """Build alias→canonical and canonical→[aliases] maps."""
    try:
        rows = turso_query("SELECT alias, canonical FROM project_aliases")
    except Exception:
        return {}, {}
    alias_to_canonical = {r["alias"]: r["canonical"] for r in rows}
    canonical_to_aliases = {}
    for r in rows:
        canonical_to_aliases.setdefault(r["canonical"], []).append(r["alias"])
    return alias_to_canonical, canonical_to_aliases


def _resolve(name, alias_to_canonical):
    """Return canonical name for a project."""
    return alias_to_canonical.get(name, name)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Load aliases
        alias_to_canonical, canonical_to_aliases = _load_alias_map()

        summaries = turso_query(
            "SELECT * FROM daily_summaries WHERE date >= ? ORDER BY date DESC",
            [week_ago],
        )

        # Activity data for last 30 days (dates + prompt counts for heat coloring)
        activity_rows = turso_query(
            "SELECT project, date, prompt_count FROM daily_summaries WHERE date >= ? ORDER BY date",
            [month_ago],
        )
        activity_by_project = {}
        for row in activity_rows:
            p = _resolve(row["project"], alias_to_canonical)
            activity_by_project.setdefault(p, []).append(
                {"date": row["date"], "prompts": int(row.get("prompt_count") or 0)}
            )
        snapshots = turso_query(
            "SELECT * FROM project_snapshots ORDER BY snapshot_date DESC"
        )

        # Aggregate week stats — resolve aliases
        week = {"prompts": 0, "sessions": 0, "commits": 0}
        by_project = {}
        for s in summaries:
            p = _resolve(s["project"], alias_to_canonical)
            week["prompts"] += int(s.get("prompt_count") or 0)
            week["sessions"] += int(s.get("session_count") or 0)
            week["commits"] += int(s.get("commit_count") or 0)
            if p not in by_project:
                by_project[p] = {"summaries": [], "days": 0}
            by_project[p]["summaries"].append(s)
            by_project[p]["days"] += 1

        latest_snapshots = {}
        for s in snapshots:
            p = _resolve(s["project"], alias_to_canonical)
            if p not in latest_snapshots:
                latest_snapshots[p] = s

        # All known projects (excluding aliases) — week-active plus any project
        # that has ever been snapshotted, so the dormant toggle still populates.
        all_projects = sorted(set(by_project) | set(latest_snapshots))

        self._json({
            "week": week,
            "by_project": by_project,
            "latest_snapshots": {
                p: s.get("data") for p, s in latest_snapshots.items()
            },
            "activity_by_project": activity_by_project,
            "all_projects": all_projects,
        })

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
