"""Shared page-view row building + insertion for the beacon (issues #9, #10).

Lives outside api/ so two handlers can share it: `api/beacon.py` (the public
POST collector) and `api/callback.py` (which records a server-side `login`
event on a successful Google sign-in). Listed in vercel.json's
`functions.includeFiles` — that list is what makes a non-api module reachable
from a serverless function at all.

Privacy by construction (see docs/measurement-policy.md): no cookies, raw IP
never stored, `visitor_hash` = sha256(BEACON_SALT | UTC date | ip | UA)
truncated, so uniques forget themselves daily. BEACON_SALT is the only salt of
record — unset means the hit is DROPPED, never salted with AUTH_SECRET or
anything else (shipped invariant, Phase 2 §2.3).

`login` rows carry the ROLE only (`path = /login/<role>`), never the email:
the row records that *an admin* signed in, not *which person*.

Calls turso_query through the module (`turso_helper.turso_query(...)`) rather
than a from-import so tests can patch the one binding.
"""

import hashlib
import json
import os
import re
import time
from urllib.parse import urlsplit

import turso_helper

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
ALLOWED_EVENTS = {"pageview", "login"}

# Fallback `site` for server-side events when the request carries no usable
# Host header. page_views.site is NOT NULL.
DEFAULT_SITE = "prompt-labs.org"

LOGIN_ROLES = ("admin", "reader")

INSERT_SQL = (
    "INSERT INTO page_views "
    "(ts, site, path, referrer, country, device, event, visitor_hash) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


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


def insert_row(row):
    """Write one page_views row. Raises on DB failure — callers decide."""
    turso_helper.turso_query(
        INSERT_SQL,
        [row["ts"], row["site"], row["path"], row["referrer"], row["country"],
         row["device"], row["event"], row["visitor_hash"]],
    )


def _self_site(headers):
    """The dashboard's own hostname, from the Host header. Previews therefore
    record under their preview domain, which is useful signal."""
    host = (headers.get("host", "") or "").split(",")[0].strip()
    site = _hostname("https://" + host) if host else None
    if not site or not HOST_OK.match(site):
        return DEFAULT_SITE
    return site


def record_login(headers, role):
    """Best-effort: record that someone with `role` signed in. Returns True if
    a row was written.

    NEVER raises — authentication must not depend on a metrics write. A user
    locked out because a stats row failed is far worse than a missing row.

    Only the role reaches the DB. `role` is validated against LOGIN_ROLES so no
    caller-supplied string (an email, say) can end up in `path`; anything else
    is recorded as `unknown`. No bot-UA gate here: the caller only reaches this
    after a real, allowlisted OAuth sign-in, which is not a crawler.
    """
    try:
        ua = headers.get("user-agent", "") or ""
        visitor_hash = _visitor_hash(_client_ip(headers), ua)
        if visitor_hash is None:
            return bool(_drop("no-beacon-salt", "login"))
        insert_row({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "site": _self_site(headers),
            "path": f"/login/{role if role in LOGIN_ROLES else 'unknown'}",
            "referrer": None,
            "country": headers.get("x-vercel-ip-country", "") or None,
            "device": _device(ua) if ua else None,
            "event": "login",
            "visitor_hash": visitor_hash,
        })
        return True
    except Exception as e:  # never break sign-in
        print(f"login beacon error: {e}"[:200])
        return False
