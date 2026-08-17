"""GET /api/visitor_overview — all-sites page-view traffic over time.

Reads the `page_views` table written directly by /api/beacon (issue #9).
Sites are hostnames (from the Origin header), not project names, so no
alias folding applies here — the mapping of site → project is a display
concern for later.

The four traffic queries all pin `event = 'pageview'`, so `login` rows
(issue #10) can never inflate a view count — which also means they are
invisible unless asked for separately. Hence the `logins` block, built from two
`event = 'login'` queries. Role comes from the path (`/login/admin`); the row
holds no identity at all, by design (docs/measurement-policy.md).

Query params:
  since=<YYYY-MM-DD> inclusive lower bound.
  until=<YYYY-MM-DD> inclusive upper bound.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import is_authenticated
from turso_helper import turso_query

LOGIN_ROLES = ("admin", "reader")


def _login_role(path):
    """`/login/admin` -> "admin". Anything unrecognised -> "unknown" — an
    allowlist, not a parse, so no unexpected path text ever lands in the
    payload."""
    parts = (path or "").strip("/").split("/")
    if len(parts) == 2 and parts[0] == "login" and parts[1] in LOGIN_ROLES:
        return parts[1]
    return "unknown"


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

        bounds, args = [], []
        if since:
            bounds.append("substr(ts, 1, 10) >= ?")
            args.append(since)
        if until:
            bounds.append("substr(ts, 1, 10) <= ?")
            args.append(until)
        # `agent = 0` excludes browser-automation traffic (issue #52). It is a
        # filter on a WRITE-TIME label, not a read-time exclusion list — the
        # thing this repo deleted twice for drifting. There is no fallback: if
        # the column is missing the query fails loudly, because a read that
        # silently degraded to unfiltered would rebuild the bug it fixes.
        where = " AND ".join(["event = 'pageview'", "agent = 0"] + bounds)
        login_where = " AND ".join(["event = 'login'", "agent = 0"] + bounds)

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

        login_days = turso_query(
            f"SELECT substr(ts, 1, 10) AS date, COUNT(*) AS count "
            f"FROM page_views WHERE {login_where} "
            f"GROUP BY date ORDER BY date",
            args,
        )
        login_paths = turso_query(
            f"SELECT path, COUNT(*) AS count "
            f"FROM page_views WHERE {login_where} "
            f"GROUP BY path",
            args,
        )

        def _ints(rows, keys):
            for r in rows:
                for k in keys:
                    r[k] = int(r[k] or 0)
            return rows

        # Turso hands back COUNT(*) as a JSON string — every count is coerced.
        by_day = [{"date": r["date"], "count": int(r["count"] or 0)}
                  for r in login_days]
        by_role = {}
        for r in login_paths:
            role = _login_role(r.get("path"))
            by_role[role] = by_role.get(role, 0) + int(r["count"] or 0)

        payload = {
            "daily": _ints(daily, ["views", "uniques"]),
            "paths": _ints(paths, ["views"]),
            "referrers": _ints(referrers, ["views"]),
            "countries": _ints(countries, ["views", "uniques"]),
            "logins": {
                "by_day": by_day,
                "by_role": [{"role": k, "count": v} for k, v in
                            sorted(by_role.items(), key=lambda kv: (-kv[1], kv[0]))],
                "total": sum(r["count"] for r in by_day),
            },
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
