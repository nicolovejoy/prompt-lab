"""GET /api/private_history — Tier 1 collaborator metrics, service-key gated.

The consumer (selected-projects) owns end-user identity and asks Garm for
authorization; on `allowed` it calls this endpoint server-to-server with a
shared service key. prompt-lab never learns the end user's email — PII surface
stays zero. Design: docs/history.md § "selected-projects tiered disclosure".

**Tier 1 is integers and dates only.** Every value served here is a count or an
ISO date, so this endpoint is structurally incapable of leaking prose. That is
the whole safety argument, and it depends on the SQL below selecting numeric
columns only — never narrative/highlights/summary. Tier 2 (private weekly
narratives, opt-in per project) is NOT built; `sessions` is always [] and
`rollups` rows always carry `public_summary: null`.

Why daily_summaries and weekly_rollups: Turso holds no `prompts`, `sessions` or
`commits` tables at all and never will (the strongest guarantee in the system).
The all-time totals are therefore summed from the per-day counts that already
sync. Do not "fix" this by adding a sync leg.

Envelope: the public_history keys keep their exact names and shapes; the values
are the corrected all-time ones (public_history counts only *published*
sessions, which is materially wrong). `activity` and `total_commits` are new.

Unknown project → empty 200 with the same envelope, never 500/403.
"""

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from turso_helper import resolve_project_names, turso_query

SERVICE_KEY_ENV = "SERVICE_HISTORY_KEY"

# The repo's week bucketing, copied verbatim from
# store/sqlite_store.py:get_weeks_without_rollups so that activity[].week_of
# lines up with the week_start values already stored in weekly_rollups. Do not
# "correct" it here in isolation — the two must agree. ('weekday 0','-6 days'
# = the containing week's Monday; 'weekday N' is next-or-SAME, which is why
# 'weekday 1','-7 days' filed Mondays a week back.)
WEEK_EXPR = "date(date, 'weekday 0', '-6 days')"


def _int_or(value, default=0):
    """Turso returns SUM()/COUNT() aggregates as JSON strings — coerce or the
    consumer's arithmetic concatenates instead of adding."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get(SERVICE_KEY_ENV, "")
        if not secret:
            # Never fail open: with no key configured there is no way to
            # authenticate the caller, so the endpoint is simply unavailable.
            return self._send(503, {"error": "service key not configured"})

        auth = (self.headers.get("authorization", "")
                or self.headers.get("Authorization", ""))
        if not hmac.compare_digest(auth, f"Bearer {secret}"):
            return self._send(401, {"error": "unauthorized"})

        params = parse_qs(urlparse(self.path).query)
        project = (params.get("project", [None])[0] or "").strip()
        if not project:
            return self._send(400, {"error": "project required"})

        names = resolve_project_names(project)
        ph = ",".join("?" * len(names))

        # NUMERIC + DATE COLUMNS ONLY below. See module docstring.
        agg_rows = turso_query(
            f"SELECT MIN(date) AS first_at, MAX(date) AS last_at, "
            f"SUM(session_count) AS sessions, SUM(commit_count) AS commits, "
            f"SUM(prompt_count) AS prompts "
            f"FROM daily_summaries WHERE project IN ({ph})",
            names,
        )
        agg = agg_rows[0] if agg_rows else {}

        activity_rows = turso_query(
            f"SELECT {WEEK_EXPR} AS week_of, "
            f"SUM(session_count) AS session_count, "
            f"SUM(commit_count) AS commit_count, "
            f"SUM(prompt_count) AS prompt_count "
            f"FROM daily_summaries WHERE project IN ({ph}) "
            f"GROUP BY week_of ORDER BY week_of ASC",
            names,
        )
        activity = [
            {
                "week_of": r.get("week_of"),
                "session_count": _int_or(r.get("session_count")),
                "commit_count": _int_or(r.get("commit_count")),
                "prompt_count": _int_or(r.get("prompt_count")),
            }
            for r in activity_rows
            if r.get("week_of")
        ]

        rollup_rows = turso_query(
            f"SELECT week_start, session_count, commit_count "
            f"FROM weekly_rollups WHERE project IN ({ph}) "
            f"ORDER BY week_start DESC",
            names,
        )
        rollups = [
            {
                "week_of": r.get("week_start"),
                "public_summary": None,  # Tier 2 not built — never prose here.
                "session_count": _int_or(r.get("session_count")),
                "commit_count": _int_or(r.get("commit_count")),
            }
            for r in rollup_rows
            if r.get("week_start")
        ]

        self._send(200, {
            "project": project,
            "first_activity_at": agg.get("first_at"),
            "last_activity_at": agg.get("last_at"),
            "total_sessions": _int_or(agg.get("sessions")),
            "total_commits": _int_or(agg.get("commits")),
            "total_prompts": _int_or(agg.get("prompts")),
            "activity": activity,
            "rollups": rollups,
            "sessions": [],  # Tier 2 only; Tier 1 never serves session prose.
        })

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
