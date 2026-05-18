"""GET /api/public_history — unauthenticated portfolio-safe history by project.

Serves rows from public_session_summaries + public_weekly_rollups for
allowlisted projects only. Consumed by other projects' About pages
(first consumer: offer-builder).

Adding a project to PUBLIC_PROJECTS is the moment its data becomes public —
do that deliberately, after reviewing the rows in SQLite.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from turso_helper import resolve_project_names, turso_query

# Canonical project names whose data may be served publicly. After a rename,
# update this set to the new canonical name; requests using the old alias
# still work because we resolve to canonical before this check.
PUBLIC_PROJECTS = {
    "byside",
    # selected-projects (pianohouseproject.org) consumes these via /projects/[slug]
    "selected-projects",
    "musicforge",
    "prntd",
    "showcase",
    "ibuild4you",
    "prompt-lab",
    "am-i-an-ai",
}

DEFAULT_SESSION_LIMIT = 20
MAX_SESSION_LIMIT = 100


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        project = (params.get("project", [None])[0] or "").strip()

        if not project:
            return self._send(400, {"error": "project required"})

        names = resolve_project_names(project)
        canonical = names[0]
        if canonical not in PUBLIC_PROJECTS:
            return self._send(404, {"error": "not found"})

        limit = _int_or(params.get("limit", [None])[0], DEFAULT_SESSION_LIMIT)
        limit = max(1, min(limit, MAX_SESSION_LIMIT))

        ph = ",".join("?" * len(names))
        session_rows = turso_query(
            f"SELECT session_id, started_at, public_summary "
            f"FROM public_session_summaries "
            f"WHERE project IN ({ph}) ORDER BY started_at DESC LIMIT ?",
            [*names, limit],
        )
        rollup_rows = turso_query(
            f"SELECT week_of, public_summary, session_count, commit_count "
            f"FROM public_weekly_rollups "
            f"WHERE project IN ({ph}) ORDER BY week_of DESC",
            names,
        )
        agg_rows = turso_query(
            f"SELECT MIN(started_at) AS first_at, MAX(started_at) AS last_at, "
            f"COUNT(*) AS n "
            f"FROM public_session_summaries "
            f"WHERE project IN ({ph})",
            names,
        )
        agg = agg_rows[0] if agg_rows else {}

        sessions = [
            {
                "session_id": _int_or(r.get("session_id"), 0),
                "started_at": r.get("started_at"),
                "public_summary": r.get("public_summary"),
            }
            for r in session_rows
        ]
        rollups = [
            {
                "week_of": r.get("week_of"),
                "public_summary": r.get("public_summary"),
                "session_count": _int_or(r.get("session_count"), 0),
                "commit_count": _int_or(r.get("commit_count"), 0),
            }
            for r in rollup_rows
        ]

        self._send(200, {
            "project": project,
            "sessions": sessions,
            "rollups": rollups,
            "first_activity_at": agg.get("first_at"),
            "last_activity_at": agg.get("last_at"),
            "total_sessions": _int_or(agg.get("n"), 0),
        })

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 200:
            self.send_header(
                "Cache-Control",
                "public, max-age=3600, stale-while-revalidate=86400",
            )
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
