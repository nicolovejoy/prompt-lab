"""GET /api/activity_timeline — all-projects session/prompt/commit counts over time.

Groups `daily_summaries` by (date, project) across every project (no project
filter), folds raw project names into their canonical name via project_aliases,
and re-sums so two aliased rows on the same day collapse into one. The frontend
builds the stacked-by-project chart and per-project table for `#/activity` from
these rows.

Every row carries all three metrics, so the metric switch (sessions | prompts |
commits) is a client-side toggle off one fetch. Counts are always ints, never
null — a missing/NULL source column reads as 0.

Deliberately its own endpoint rather than a param on `/api/overview`:
overview's payload is SWR-cached to paint the home page, so it stays lean.

Query params:
  days=<N> window size in days, inclusive of today (UTC). Default 30, clamped
           to 1..3650; unparseable input falls back to the default (never 400s
           — a bad query string shouldn't break the page).
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from access_helper import filter_rows, resolve_access
from day_helper import lab_window
from turso_helper import turso_query

DEFAULT_DAYS = 30
MIN_DAYS = 1
MAX_DAYS = 3650  # ~10y; the table starts 2026-01, so this is effectively all-time.


def _alias_to_canonical():
    try:
        rows = turso_query("SELECT alias, canonical FROM project_aliases")
    except Exception:
        return {}
    return {r["alias"]: r["canonical"] for r in rows}


def _parse_days(raw):
    """Clamp `days` into [MIN_DAYS, MAX_DAYS]; fall back to the default."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, n))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        access = resolve_access(self.headers)
        if access is None:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        params = parse_qs(urlparse(self.path).query)
        days = _parse_days(params.get("days", [None])[0])

        # Inclusive of today on the LAB's clock, not UTC (#48): `date` here is a
        # Pacific calendar day, so a UTC window opens a day early after 5pm PDT
        # and the chart grows an empty column for a day that hasn't happened.
        since = lab_window(days)

        sql = (
            "SELECT date, project, "
            "       SUM(COALESCE(session_count, 0)) AS sessions, "
            "       SUM(COALESCE(prompt_count, 0)) AS prompts, "
            "       SUM(COALESCE(commit_count, 0)) AS commits "
            "FROM daily_summaries WHERE date >= ? "
            "GROUP BY date, project"
        )
        raw = turso_query(sql, [since])

        # Fold raw project names into canonical, re-summing collisions on the
        # same (date, canonical).
        a2c = _alias_to_canonical()
        folded = {}
        for r in raw:
            proj = a2c.get(r["project"], r["project"])
            key = (r["date"], proj)
            agg = folded.setdefault(key, {"sessions": 0, "prompts": 0, "commits": 0})
            for metric in ("sessions", "prompts", "commits"):
                agg[metric] += int(r.get(metric) or 0)

        rows = [
            {"date": d, "project": p, **agg}
            for (d, p), agg in folded.items()
        ]
        rows.sort(key=lambda r: (r["date"], r["project"]))
        rows = filter_rows(access, rows)  # already canonical, so default identity canon

        payload = {"rows": rows, "days": days}

        self.send_response(200)
        if access.set_cookie:
            self.send_header("Set-Cookie", access.set_cookie)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
