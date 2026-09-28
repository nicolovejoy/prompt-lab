"""GET /api/visitor_overview — all-sites page-view traffic over time.

Reads the `page_views` table written directly by /api/beacon (issue #9).
Sites are hostnames (from the Origin header), not project names, so no
alias folding applies here. One fold does: preview deployments
(`*.vercel.app`, `preview.*`) collapse into a single `previews` site, because
each branch deploy gets its own hostname and a dozen one-view "sites" bury
the real ones. It is a rule on the hostname's shape, not a list of names.

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

from access_helper import resolve_access
from turso_helper import turso_query

LOGIN_ROLES = ("admin", "reader")

PREVIEWS = "previews"


def _site_label(host):
    """A preview deployment's hostname -> "previews"; anything else unchanged."""
    h = (host or "").lower()
    if h.endswith(".vercel.app") or h.startswith("preview."):
        return PREVIEWS
    return host


def _fold(rows, keys, sums):
    """Relabel each row's site, then merge rows that now share `keys`,
    adding up `sums`. Counts must already be ints. Summed uniques can count
    one visitor twice across two preview hosts — accepted: the hash is
    per-site-per-day by design, so there is nothing to dedupe on."""
    out, seen = [], {}
    for row in rows:
        row = dict(row)
        row["site"] = _site_label(row.get("site"))
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            for s in sums:
                seen[key][s] += row[s]
        else:
            seen[key] = row
            out.append(row)
    return out


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
        access = resolve_access(self.headers)
        if access is None:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return
        # Admin-only (decision 3): visitors has no project column to filter
        # on and maps traffic across every site. Gate on the grant-set axis,
        # not the role string — an unfiltered account (admin, or a reader
        # when GARM_GATING=off) keeps today's behaviour.
        if access.projects is not None:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "admin required"}).encode())
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

        daily = _ints(daily, ["views", "uniques"])
        preview_hosts = len({r["site"] for r in daily
                             if _site_label(r["site"]) == PREVIEWS})

        def by_views(r):
            return -r["views"]

        folded_paths = sorted(_fold(_ints(paths, ["views"]), ["site", "path"], ["views"]),
                              key=by_views)
        folded_referrers = sorted(
            _fold(_ints(referrers, ["views"]), ["site", "referrer"], ["views"]),
            key=by_views)

        payload = {
            "daily": _fold(daily, ["date", "site"], ["views", "uniques"]),
            "paths": folded_paths,
            "referrers": folded_referrers,
            "countries": _ints(countries, ["views", "uniques"]),
            "preview_hosts": preview_hosts,
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
