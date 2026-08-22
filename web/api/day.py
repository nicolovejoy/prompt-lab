"""GET /api/day?date=<YYYY-MM-DD> — everything known about one calendar day.

Backs the `#/day/<date>` route, which is where a tap on any activity bar lands.

Why a page and not a popup: an overlay is positioned against the *layout*
viewport, so on a pinch-zoomed phone a "fixed" panel can render off-screen —
the same way the below-chart readout it replaced did. A navigation resets the
viewport and needs no positioning at all, works identically on phone and web
off one code path, and makes a day a thing you can link to.

That last part is why this endpoint exists rather than the page reading the
`overview` payload the app already holds: overview only carries the recent
window, so a cold-opened link to a day in March would render empty. A day page
whose URL only works if you arrived from the chart is not really a page.

Reads `daily_summaries`, `api_costs`, `page_views` and `uptime_daily` — Turso
has no raw `prompts`/`sessions`/`commits` tables at all, by design (see CLAUDE.md
invariants), so no prompt text, commit message, hostname or local path is
reachable from here. Counts, spend and already-written summary prose are the
whole surface.

Everything past the summaries read is best-effort: one unavailable table degrades
to a missing section, not a dead page. The summaries read is deliberately not —
a day page with no day in it is not a page, so that one 503s.

Alias folding matches every other reader: two rows under an old and a new
project name collapse into one canonical entry with their counts re-summed.

Unknown/quiet day → 200 with zeroed totals and an empty `projects` list, never
a 404. A day with no work is a fact about the day, not a missing resource.
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from access_helper import filter_rows, resolve_access
from day_helper import lab_today
from turso_helper import turso_query

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _alias_to_canonical():
    try:
        rows = turso_query("SELECT alias, canonical FROM project_aliases")
    except Exception:
        return {}
    return {r["alias"]: r["canonical"] for r in rows}


def _tidy(raw):
    """key_decisions is stored as a JSON array; tolerate anything else."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        access = resolve_access(self.headers)
        if access is None:
            self._json({"error": "unauthorized"}, 401)
            return

        params = parse_qs(urlparse(self.path).query)
        date = (params.get("date", [""])[0] or "").strip()
        # Shape-checked before it reaches the query. It is a bound parameter, so
        # this is not the injection guard — it is so a typo'd URL says what is
        # wrong instead of quietly returning an empty day.
        if not ISO_DATE.match(date):
            self._json({"error": "date must be YYYY-MM-DD"}, 400)
            return

        try:
            rows = turso_query(
                "SELECT project, summary, key_decisions, "
                "       COALESCE(prompt_count, 0) AS prompts, "
                "       COALESCE(session_count, 0) AS sessions, "
                "       COALESCE(commit_count, 0) AS commits "
                "FROM daily_summaries WHERE date = ?",
                [date],
            )
        except Exception as e:
            self._json({"error": "temporarily unavailable", "detail": str(e)}, 503)
            return

        a2c = _alias_to_canonical()
        rows = filter_rows(access, rows, canon=lambda n: a2c.get(n, n))
        folded = {}
        for r in rows:
            proj = a2c.get(r["project"], r["project"])
            agg = folded.setdefault(proj, {
                "project": proj, "prompts": 0, "sessions": 0, "commits": 0,
                "summary": "", "key_decisions": [],
            })
            for metric in ("prompts", "sessions", "commits"):
                # Turso hands back COALESCE/SUM results as strings — int() here
                # is load-bearing or the totals below concatenate.
                agg[metric] += int(r.get(metric) or 0)
            # Two aliased rows can each carry prose. Keep the longer one rather
            # than gluing them together: they describe the same day's work from
            # the same source, so the longer is the fuller telling, and a
            # concatenation would read as a contradiction.
            text = (r.get("summary") or "").strip()
            if len(text) > len(agg["summary"]):
                agg["summary"] = text
                agg["key_decisions"] = _tidy(r.get("key_decisions"))

        projects = sorted(folded.values(),
                          key=lambda p: (-p["prompts"], p["project"]))
        totals = {m: sum(p[m] for p in projects)
                  for m in ("prompts", "sessions", "commits")}

        # visitors (site) and uptime (monitor) are admin-only per the Garm plan
        # (decision 3: no project column to filter on, and they map everything
        # Nico runs) — a filtered reader gets neither section at all, not a
        # filtered one.
        admin_only = access.projects is not None

        self._json({
            "date": date,
            "totals": totals,
            "projects": projects,
            "spend": self._spend(date, a2c, access),
            "visitors": None if admin_only else self._visitors(date),
            "uptime": None if admin_only else self._uptime(date),
            # Today's row is written by /handoff or the nightly synthesizer, so
            # until one runs it under-reports — and a chart can't tell a quiet
            # day from an unsummarized one. Say which this is rather than let a
            # partial number read as a final one.
            "provisional": date == lab_today().isoformat(),
        }, access=access)

    # Each of these is best-effort: a day page must still render if one table is
    # unavailable. The main daily_summaries read above is NOT — that one 503s,
    # because a day page with no day in it is not a page.
    def _soft(self, sql, args):
        try:
            return turso_query(sql, args)
        except Exception as e:
            print(f"day: {sql.split()[3] if len(sql.split()) > 3 else '?'} "
                  f"unreadable: {e}"[:200])
            return None

    def _spend(self, date, a2c, access):
        rows = self._soft(
            "SELECT project, SUM(cost_reported_usd) AS usd FROM api_costs "
            "WHERE date = ? GROUP BY project", [date])
        if rows is None:
            return None
        rows = filter_rows(access, rows, canon=lambda n: a2c.get(n, n))
        by = {}
        for r in rows:
            p = a2c.get(r["project"], r["project"]) or "unattributed"
            by[p] = by.get(p, 0.0) + float(r.get("usd") or 0)
        return {
            "total_usd": round(sum(by.values()), 4),
            "by_project": [{"project": p, "usd": round(v, 4)}
                           for p, v in sorted(by.items(), key=lambda kv: -kv[1])],
        }

    def _visitors(self, date):
        # ts is a UTC instant; the lab day is Pacific (#48). SQLite has no tz
        # database, so the shift is explicit — and it is -7 only during PDT,
        # which is why this is a range on the raw ts rather than a date() call
        # that would silently be wrong for half the year.
        rows = self._soft(
            "SELECT site, COUNT(*) AS views FROM page_views "
            "WHERE event = 'pageview' AND agent = 0 "
            "AND ts >= datetime(?, '+7 hours') "
            "AND ts < datetime(?, '+1 day', '+7 hours') GROUP BY site",
            [date, date])
        if rows is None:
            return None
        by = sorted(({"site": r["site"] or "?", "views": int(r.get("views") or 0)}
                     for r in rows), key=lambda s: -s["views"])
        return {"views": sum(s["views"] for s in by), "by_site": by}

    def _uptime(self, date):
        rows = self._soft(
            "SELECT monitor, uptime_1d, status FROM uptime_daily WHERE date = ? "
            "ORDER BY monitor", [date])
        if rows is None:
            return None
        return [{"monitor": r["monitor"],
                 "uptime_1d": None if r.get("uptime_1d") is None else float(r["uptime_1d"]),
                 "status": r.get("status")} for r in rows]

    def _json(self, payload, status=200, access=None):
        self.send_response(status)
        if access and access.set_cookie:
            self.send_header("Set-Cookie", access.set_cookie)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
