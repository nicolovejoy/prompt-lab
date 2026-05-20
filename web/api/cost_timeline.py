"""GET /api/cost_timeline — daily API cost + token usage for a project.

Returns one row per (date, model) summing `cost_reported_usd` from api_costs
and token totals from api_usage. Optional `?include=claude_code` adds Claude
Code activity metrics on the same daily grain. Optional `?detail=1` adds
ungrouped per-(date, model, token_type, …) rows for drill-down views.

Query params:
  project=<name>     filter by project (alias-expanded). Default: all projects.
  since=<YYYY-MM-DD> inclusive lower bound on date.
  until=<YYYY-MM-DD> inclusive upper bound on date.
  include=claude_code  also return per-day Claude Code activity rows.
  detail=1           also return ungrouped api_costs rows for drill-down.
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
        detail = params.get("detail", ["0"])[0] in ("1", "true", "yes")

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

        if detail:
            # Ungrouped api_costs rows — one per row in the underlying table.
            # SUM still applied at (date, workspace_id, description, dimensions)
            # so multiple workspaces collapsing into one project come through
            # as a single row; if the dashboard ever wants per-workspace
            # split it would need a separate endpoint.
            detail_sql = (
                f"SELECT date, "
                f"       COALESCE(model, '_unknown_') AS model, "
                f"       COALESCE(token_type, '') AS token_type, "
                f"       COALESCE(service_tier, '') AS service_tier, "
                f"       COALESCE(context_window, '') AS context_window, "
                f"       COALESCE(cost_type, '') AS cost_type, "
                f"       COALESCE(inference_geo, '') AS inference_geo, "
                f"       SUM(cost_reported_usd) AS cost_usd "
                f"FROM api_costs WHERE {' AND '.join(cost_clauses)} "
                f"GROUP BY date, model, token_type, service_tier, "
                f"         context_window, cost_type, inference_geo "
                f"ORDER BY date DESC, cost_usd DESC"
            )
            payload["detail"] = turso_query(detail_sql, cost_args)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
