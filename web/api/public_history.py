"""GET /api/public_history — unauthenticated portfolio-safe history by project.

Serves rows from public_session_summaries + public_weekly_rollups for ANY
project. These two tables are safe-by-construction: they are written ONLY by
the hand-authored scripts/backfill_public_*.py with scrubbed, de-identified
text — never by the synthesizer or the raw-data sync. There is deliberately no
read-time allowlist; curation of which projects appear publicly lives in the
consumer (the selected-projects MDX manifest), which is the single source of
truth for the public site.

Invariant to preserve: never write un-scrubbed text into the public_* tables.
An unknown project (or one with no rows) simply returns empty arrays.

Read-time counts projection: for a project whose project_metadata.public_counts
flag is set, the weekly rollup array is backfilled with counts-only rows
(public_summary=null) projected from the PRIVATE weekly_rollups table for weeks
that have no published prose row. This gives consumers a fresh weekly
session/commit cadence without a nightly writer into the public tables (the
no-automated-writer invariant stays intact). Prose can never leak this way: the
projection query selects numeric columns ONLY (week_start, session_count,
commit_count) — never narrative/highlights — pinned by a test. Published prose
rows always win for their week; counts are per-machine-synthesized and merged
last-writer-wins upstream, so cross-machine weeks may undercount (cadence, not
exact totals).
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from turso_helper import resolve_project_names, turso_query

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

        # No allowlist: the public_* tables are scrubbed-by-construction, so we
        # serve whatever exists. Alias resolution still merges renamed projects;
        # an unknown project just yields empty result sets below.
        names = resolve_project_names(project)

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

        # Counts projection (opt-in). Overlay counts-only rows from the private
        # weekly_rollups for any week without a published prose row above.
        if self._counts_opted_in(names):
            published_weeks = {r["week_of"] for r in rollups}
            # NUMERIC COLUMNS ONLY — never select narrative/highlights here.
            # This is the structural prose-safety guarantee (pinned by a test).
            count_rows = turso_query(
                f"SELECT week_start, session_count, commit_count "
                f"FROM weekly_rollups "
                f"WHERE project IN ({ph}) ORDER BY week_start DESC",
                names,
            )
            for r in count_rows:
                week = r.get("week_start")
                if not week or week in published_weeks:
                    continue
                published_weeks.add(week)
                rollups.append({
                    "week_of": week,
                    "public_summary": None,
                    "session_count": _int_or(r.get("session_count"), 0),
                    "commit_count": _int_or(r.get("commit_count"), 0),
                })
            rollups.sort(key=lambda x: x["week_of"] or "", reverse=True)

        self._send(200, {
            "project": project,
            "sessions": sessions,
            "rollups": rollups,
            "first_activity_at": agg.get("first_at"),
            "last_activity_at": agg.get("last_at"),
            "total_sessions": _int_or(agg.get("n"), 0),
        })

    def _counts_opted_in(self, names):
        """True if any resolved name has project_metadata.public_counts set.

        Best-effort: a missing table or query error yields False so the public
        endpoint never 500s on the projection path.
        """
        ph = ",".join("?" * len(names))
        try:
            rows = turso_query(
                f"SELECT public_counts FROM project_metadata "
                f"WHERE project IN ({ph})",
                names,
            )
        except Exception:
            return False
        return any(_int_or(r.get("public_counts"), 0) for r in rows)

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
