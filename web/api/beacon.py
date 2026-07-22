"""POST /api/beacon — public page-view collector (issue #9).

Every ecosystem site loads /beacon.js, which POSTs one small JSON body per
page view. Rows go straight into the Turso `page_views` table the dashboard
reads — deliberately no local-SQLite leg and no sync step (the cost pipeline's
pull/sync split drifted for a month; this path can't).

Privacy by construction: no cookies, raw IP never stored. `visitor_hash` is
sha256(BEACON_SALT | UTC date | ip | user-agent) truncated — approximate
uniques that forget themselves daily. Query strings and referrer paths are
stripped before storage.

The salt is BEACON_SALT, set independently of AUTH_SECRET (the transitional
fallback was removed in Phase 2 §2.3 once BEACON_SALT was deployed to every
environment). If BEACON_SALT is unset, the hit is dropped rather than salted
with anything else — no accidental dependency on AUTH_SECRET, and no
traceback: the endpoint stays an opaque 204 on every path.

Abuse posture: `site` is derived server-side from the Origin header (never
client-supplied), obvious bot user-agents and localhost origins are dropped,
body is capped at 2 KB, and every outcome — stored or dropped — returns an
opaque 204 so probes learn nothing. Drops are print()-logged to Vercel logs.
"""

import hashlib
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from turso_helper import turso_query

MAX_BODY = 2048
MAX_PATH = 300
MAX_HOST = 100

BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor"
    r"|prerender|scrape|python|curl|wget|httpx|libwww|java/|go-http"
    r"|phantom|selenium|playwright|puppeteer|facebookexternalhit|preview",
    re.IGNORECASE,
)
HOST_OK = re.compile(r"^[a-z0-9][a-z0-9.-]{0,99}$")
ALLOWED_EVENTS = {"pageview"}  # future: "login" for issue #10


def _client_ip(headers):
    fwd = headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return headers.get("x-real-ip", "")


def _hostname(url_or_origin):
    """Lowercased hostname without a leading www., or None."""
    try:
        host = urlsplit(url_or_origin).hostname or ""
    except ValueError:
        return None
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _device(ua):
    low = ua.lower()
    if "ipad" in low or "tablet" in low:
        return "tablet"
    if "mobile" in low or "android" in low:
        return "mobile"
    return "desktop"


def _visitor_hash(ip, ua):
    # BEACON_SALT is the only salt of record (no AUTH_SECRET fallback, §2.3).
    # Unset -> None, and the caller drops the hit rather than hash with
    # nothing / another secret.
    secret = os.environ.get("BEACON_SALT")
    if not secret:
        return None
    day = time.strftime("%Y-%m-%d", time.gmtime())
    raw = f"{secret}|{day}|{ip}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _drop(reason, detail=""):
    print(f"beacon drop: {reason} {detail}"[:200])
    return None


def parse_event(headers, body_bytes):
    """Validate one beacon hit. Returns a row dict to insert, or None to drop."""
    ua = headers.get("user-agent", "")
    if not ua or BOT_UA.search(ua):
        return _drop("bot-ua", ua[:80])

    origin = headers.get("origin", "") or headers.get("referer", "")
    site = _hostname(origin)
    if not site or not HOST_OK.match(site):
        return _drop("bad-origin", origin[:80])
    if site in ("localhost",) or site.startswith("127.") or site.endswith(".local"):
        return _drop("local-origin", site)

    try:
        body = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _drop("bad-json")
    if not isinstance(body, dict):
        return _drop("bad-json")

    event = body.get("event", "pageview")
    if event not in ALLOWED_EVENTS:
        return _drop("bad-event", str(event)[:40])

    path = body.get("path", "")
    if not isinstance(path, str) or not path.startswith("/"):
        return _drop("bad-path")
    path = path.split("?")[0].split("#")[0][:MAX_PATH]

    referrer = None
    ref = body.get("ref", "")
    if isinstance(ref, str) and ref:
        ref_host = _hostname(ref)
        if ref_host and ref_host != site:
            referrer = ref_host[:MAX_HOST]

    country = headers.get("x-vercel-ip-country", "") or None
    ip = _client_ip(headers)

    visitor_hash = _visitor_hash(ip, ua)
    if visitor_hash is None:
        return _drop("no-beacon-salt")

    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "site": site,
        "path": path,
        "referrer": referrer,
        "country": country,
        "device": _device(ua),
        "event": event,
        "visitor_hash": visitor_hash,
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = min(int(self.headers.get("content-length", 0) or 0), MAX_BODY)
            body_bytes = self.rfile.read(length) if length > 0 else b""
            row = parse_event(self.headers, body_bytes)
            if row:
                turso_query(
                    "INSERT INTO page_views "
                    "(ts, site, path, referrer, country, device, event, visitor_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [row["ts"], row["site"], row["path"], row["referrer"],
                     row["country"], row["device"], row["event"],
                     row["visitor_hash"]],
                )
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
