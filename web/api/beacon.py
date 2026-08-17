"""POST /api/beacon — public page-view collector (issue #9).

Every ecosystem site loads /beacon.js, which POSTs one small JSON body per
page view. Rows go straight into the Turso `page_views` table the dashboard
reads — deliberately no local-SQLite leg and no sync step (the cost pipeline's
pull/sync split drifted for a month; this path can't).

Row building, validation, hashing and the INSERT all live in
`web/beacon_helper.py`, shared with `api/callback.py` (which records the
server-side `login` event, issue #10). The names re-exported below are part of
this module's tested surface — keep them importable here.

Privacy by construction: no cookies, raw IP never stored. `visitor_hash` is
sha256(BEACON_SALT | UTC date | ip | user-agent) truncated — approximate
uniques that forget themselves daily. Query strings and referrer paths are
stripped before storage.

The salt is BEACON_SALT, set independently of AUTH_SECRET (the transitional
fallback was removed in Phase 2 §2.3 once BEACON_SALT was deployed to every
environment). If BEACON_SALT is unset, the hit is dropped rather than salted
with anything else — no accidental dependency on AUTH_SECRET, and no
traceback: the endpoint stays an opaque 204 on every path.

Browser automation (issue #52) is LABELLED rather than dropped: `agent = 1` on
the row when the hit carries navigator.webdriver, the beacon's localStorage
kill-switch, or an `X-Test-Agent` header. Visitor-facing reads filter
`agent = 0`. Declared bot user-agents are still dropped outright — a crawler
never becomes a row at all.

Abuse posture: `site` is derived server-side from the Origin header (never
client-supplied), obvious bot user-agents and localhost origins are dropped,
body is capped at 2 KB, and every outcome — stored or dropped — returns an
opaque 204 so probes learn nothing. Drops are print()-logged to Vercel logs.
"""

from http.server import BaseHTTPRequestHandler

from beacon_helper import (  # noqa: F401  (re-exported: tested surface)
    AGENT_HEADER,
    ALLOWED_EVENTS,
    BOT_UA,
    HOST_OK,
    MAX_BODY,
    MAX_HOST,
    MAX_PATH,
    _agent_flag,
    _device,
    _hostname,
    _visitor_hash,
    insert_row,
    parse_event,
)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = min(int(self.headers.get("content-length", 0) or 0), MAX_BODY)
            body_bytes = self.rfile.read(length) if length > 0 else b""
            row = parse_event(self.headers, body_bytes)
            if row:
                insert_row(row)
        except Exception as e:  # never bubble errors to the caller
            print(f"beacon error: {e}"[:200])
        self._done()

    def do_OPTIONS(self):
        self._done()

    def do_GET(self):
        self._done()

    def _done(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
