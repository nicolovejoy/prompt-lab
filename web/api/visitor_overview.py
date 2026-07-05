"""GET /api/visitor_overview — all-sites page-view traffic over time.

Reads the `page_views` table written directly by /api/beacon (issue #9).
Sites are hostnames (from the Origin header), not project names, so no
alias folding applies here — the mapping of site → project is a display
concern for later.

Query params:
  since=<YYYY-MM-DD> inclusive lower bound.
  until=<YYYY-MM-DD> inclusive upper bound.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import turso_query


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

        clauses, args = ["event = 'pageview'"], []
        if since:
            clauses.append("substr(ts, 1, 10) >= ?")
            args.append(since)
        if until:
            clauses.append("substr(ts, 1, 10) <= ?")
            args.append(until)
        where = " AND ".join(clauses)

        daily = turso_query(
            f"SELECT substr(ts, 1, 10) AS date, site, "
            f"       COUNT(*) AS views, COUNT(DISTINCT visitor_hash) AS uniques "
            f"FROM page_views WHERE {where} "
            f"GROUP BY date, site ORDER BY date, site",
            args,
        )
        paths = turso_query(
            f"SELECT site, path, COUNT(*) AS views "
            f"FROM page_views WHERE {where} "
            f"GROUP BY site, path ORDER BY views DESC LIMIT 300",
            args,
        )
        referrers = turso_query(
            f"SELECT site, referrer, COUNT(*) AS views "
            f"FROM page_views WHERE {where} AND referrer IS NOT NULL "
            f"GROUP BY site, referrer ORDER BY views DESC LIMIT 200",
            args,
        )
        countries = turso_query(
            f"SELECT country, COUNT(*) AS views, "
            f"       COUNT(DISTINCT visitor_hash) AS uniques "
            f"FROM page_views WHERE {where} AND country IS NOT NULL "
            f"GROUP BY country ORDER BY views DESC LIMIT 100",
            args,
        )

        def _ints(rows, keys):
            for r in rows:
                for k in keys:
                    r[k] = int(r[k] or 0)
            return rows

        payload = {
            "daily": _ints(daily, ["views", "uniques"]),
            "paths": _ints(paths, ["views"]),
            "referrers": _ints(referrers, ["views"]),
            "countries": _ints(countries, ["views", "uniques"]),
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
