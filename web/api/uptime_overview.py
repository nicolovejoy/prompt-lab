"""GET /api/uptime_overview — archived UptimeRobot uptime, per monitor.

Reads the `uptime_daily` rows the health cron writes (health_report.py's
_archive_uptime). UptimeRobot keeps 3 months; this archive keeps forever, which
is the whole reason it exists — prompt-lab still samples nothing itself.

Auth-gated like cost_overview: any authenticated role, 401 anonymous.

An empty response is the normal early state. The archive starts at zero rows
and fills one day at a time, and there is deliberately NO backfill: v2 exposes
rolling ratios, not per-day history, so anything written for a past date would
be invented data.

Query params:
  days=<N> window size in days, inclusive of today (UTC). Default 30, clamped
           to 1..3650; unparseable input falls back to the default (never 400s
           — a bad query string shouldn't break the page).
"""

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from access_helper import resolve_access
from day_helper import lab_window
from turso_helper import turso_query

DEFAULT_DAYS = 30
MIN_DAYS = 1
MAX_DAYS = 3650


def _parse_days(raw):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return max(MIN_DAYS, min(MAX_DAYS, n))


# Turso hands numeric columns back as JSON strings often enough that an explicit
# coalesce is load-bearing, not decorative (it has bitten chart math twice).
# NULL stays NULL: a monitor with no samples has an unknown latency, and 0 would
# be a lie the chart would happily draw.
def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        access = resolve_access(self.headers)
        if access is None:
            self._json({"error": "unauthorized"}, 401)
            return
        # Admin-only (decision 3): uptime has no project column to filter on
        # and maps everything Nico runs. Gate on the grant-set axis, not the
        # role string — an unfiltered account (admin, or a reader when
        # GARM_GATING=off) keeps today's behaviour.
        if access.projects is not None:
            self._json({"error": "admin required"}, 403)
            return

        params = parse_qs(urlparse(self.path).query)
        days = _parse_days(params.get("days", [None])[0])
        # Lab-day window (#48): uptime_daily.date is written on the lab's
        # clock by the 8am cron, so a UTC edge drops or adds a column.
        since = lab_window(days)

        unavailable = False
        try:
            rows = turso_query(
                "SELECT date, monitor, uptime_1d, uptime_7d, uptime_30d, "
                "       avg_response_ms, status "
                "FROM uptime_daily WHERE date >= ? ORDER BY date",
                [since],
            )
        except Exception as e:
            # Say so rather than rendering as "nothing collected yet" — absence
            # reading as fine is the #45 bug, and the archive legitimately holds
            # no rows on day one, so the two states must stay distinguishable.
            print(f"uptime_overview: archive unreadable: {e}"[:300])
            rows, unavailable = [], True

        monitors = {}
        for r in rows:
            name = r.get("monitor")
            entry = monitors.setdefault(name, {"name": name, "series": []})
            entry["series"].append({
                "date": r.get("date"),
                "uptime": _f(r.get("uptime_1d")),
                "ms": _i(r.get("avg_response_ms")),
            })
            # Rows arrive oldest-first, so the last one seen carries the
            # headline figures — the rolling ratios are only meaningful as of
            # the day they were sampled.
            entry.update(
                uptime_30d=_f(r.get("uptime_30d")),
                uptime_7d=_f(r.get("uptime_7d")),
                uptime_1d=_f(r.get("uptime_1d")),
                avg_response_ms=_i(r.get("avg_response_ms")),
                status=r.get("status"),
            )

        payload = {
            "days": days,
            "monitors": [
                {"name": m["name"], "uptime_30d": m.get("uptime_30d"),
                 "uptime_7d": m.get("uptime_7d"), "uptime_1d": m.get("uptime_1d"),
                 "avg_response_ms": m.get("avg_response_ms"),
                 "status": m.get("status"), "series": m["series"]}
                for m in sorted(monitors.values(), key=lambda m: m["name"] or "")
            ],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if unavailable:
            payload["unavailable"] = True

        self._json(payload)

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
