"""GET /api/cost_timeline — daily API cost + token usage for a project.

Returns one row per (date, model) summing `cost_reported_usd` from api_costs
and token totals from api_usage. Optional `?include=claude_code` adds Claude
Code activity metrics on the same daily grain.

Query params:
  project=<name>     filter by project (alias-expanded). Default: all projects.
  since=<YYYY-MM-DD> inclusive lower bound on date.
  until=<YYYY-MM-DD> inclusive upper bound on date.
  include=claude_code  also return per-day Claude Code activity rows.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import resolve_project_names, turso_query


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        params = parse_qs(urlparse(self.path).query)
        project = params.get("project", [None])[0]
        since = params.get("since", [None])[0]
        until = params.get("until", [None])[0]
        include = params.get("include", [""])[0]

        cost_clauses, cost_args = ["1=1"], []
        usage_clauses, usage_args = ["1=1"], []
        if project:
            names = resolve_project_names(project)
            placeholders = ",".join("?" * len(names))
            cost_clauses.append(f"project IN ({placeholders})")
            cost_args.extend(names)
            usage_clauses.append(f"project IN ({placeholders})")
            usage_args.extend(names)
        if since:
            cost_clauses.append("date >= ?")
            cost_args.append(since)
            usage_clauses.append("date >= ?")
            usage_args.append(since)
        if until:
            cost_clauses.append("date <= ?")
            cost_args.append(until)
            usage_clauses.append("date <= ?")
            usage_args.append(until)

        # Aggregate USD per (date, model). cost_report has multiple rows per
        # (date, workspace, model) — one per token_type — so SUM them.
        cost_sql = (
            f"SELECT date, COALESCE(model, '_unknown_') AS model, "
            f"       SUM(cost_reported_usd) AS cost_usd "
            f"FROM api_costs WHERE {' AND '.join(cost_clauses)} "
            f"GROUP BY date, model ORDER BY date DESC, model"
        )
        cost_rows = turso_query(cost_sql, cost_args)

        usage_sql = (
            f"SELECT date, model, "
            f"       SUM(input_tokens) AS input_tokens, "
            f"       SUM(cached_input_tokens) AS cached_input_tokens, "
            f"       SUM(cache_creation_tokens) AS cache_creation_tokens, "
            f"       SUM(output_tokens) AS output_tokens, "
            f"       SUM(cost_computed_usd) AS cost_computed_usd "
            f"FROM api_usage WHERE {' AND '.join(usage_clauses)} "
            f"GROUP BY date, model ORDER BY date DESC, model"
        )
        usage_rows = turso_query(usage_sql, usage_args)

        payload = {"costs": cost_rows, "usage": usage_rows}

        if include == "claude_code":
            cc_clauses, cc_args = ["1=1"], []
            if since:
                cc_clauses.append("date >= ?")
                cc_args.append(since)
            if until:
                cc_clauses.append("date <= ?")
                cc_args.append(until)
            cc_sql = (
                f"SELECT date, customer_type, model, "
                f"       SUM(sessions) AS sessions, "
                f"       SUM(lines_added) AS lines_added, "
                f"       SUM(lines_removed) AS lines_removed, "
                f"       SUM(commits) AS commits, "
                f"       SUM(prs) AS prs, "
                f"       SUM(input_tokens) AS input_tokens, "
                f"       SUM(output_tokens) AS output_tokens, "
                f"       SUM(estimated_cost_cents) / 100.0 AS estimated_cost_usd "
                f"FROM claude_code_usage WHERE {' AND '.join(cc_clauses)} "
                f"GROUP BY date, customer_type, model "
                f"ORDER BY date DESC, customer_type, model"
            )
            payload["claude_code"] = turso_query(cc_sql, cc_args)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
