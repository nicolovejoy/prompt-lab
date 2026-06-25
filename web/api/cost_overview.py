"""GET /api/cost_overview — all-projects API spend over time.

Groups `api_costs` by (date, project, model) across every project (no project
filter), folds raw project names into their canonical name via project_aliases,
and re-sums so two aliased rows on the same day collapse into one. The frontend
builds the stacked-by-project chart, per-project legend, and per-model
breakdown from these rows.

Only API spend is here. Claude Code (subscription) usage is NOT attributable
per project (`claude_code_usage` is actor/org-level, no `project` column), so
projects worked on mostly via the subscription read ~$0. The page states this.

Query params:
  since=<YYYY-MM-DD> inclusive lower bound on date.
  until=<YYYY-MM-DD> inclusive upper bound on date.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import turso_query


def _alias_to_canonical():
    try:
        rows = turso_query("SELECT alias, canonical FROM project_aliases")
    except Exception:
        return {}
    return {r["alias"]: r["canonical"] for r in rows}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        params = parse_qs(urlparse(self.path).query)
        since = params.get("since", [None])[0]
        until = params.get("until", [None])[0]

        clauses, args = ["1=1"], []
        if since:
            clauses.append("date >= ?")
            args.append(since)
        if until:
            clauses.append("date <= ?")
            args.append(until)

        sql = (
            f"SELECT date, project, COALESCE(model, '_unknown_') AS model, "
            f"       SUM(cost_reported_usd) AS cost_usd "
            f"FROM api_costs WHERE {' AND '.join(clauses)} "
            f"GROUP BY date, project, model"
        )
        raw = turso_query(sql, args)

        # Fold raw project names into canonical, re-summing collisions on the
        # same (date, canonical, model).
        a2c = _alias_to_canonical()
        folded = {}
        for r in raw:
            proj = a2c.get(r["project"], r["project"])
            key = (r["date"], proj, r["model"])
            folded[key] = folded.get(key, 0.0) + (float(r["cost_usd"] or 0.0))

        rows = [
            {"date": d, "project": p, "model": m, "cost_usd": round(c, 6)}
            for (d, p, m), c in folded.items()
        ]
        rows.sort(key=lambda r: (r["date"], r["project"], r["model"]))

        payload = {"rows": rows}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
