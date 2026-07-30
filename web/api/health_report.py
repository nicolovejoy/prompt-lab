"""GET /api/health_report — daily ecosystem health summary email (issue #34).

prompt-lab owns health REPORTING for the ecosystem (garm handoff 2026-07-29):
a Vercel cron hits this endpoint daily, it polls each target's health endpoint
(convention: docs/health-convention.md) and emails a summary via Resend.
Immediate alerting is deliberately NOT here — UptimeRobot on independent infra
is the pager; this is the trend layer, and it dies with the shared stack.

Auth: the cron authenticates with `Authorization: Bearer $CRON_SECRET` (Vercel
attaches it automatically when the env var is set); an admin cookie also works
for manual runs. `?dry=1` polls targets and returns JSON without sending.

Pause: each email carries an HMAC-signed link (`?action=pause&token=…`) that
suppresses sends for 7 days — state in the Turso `health_email_state` table
(cloud-direct, no local copy, no sync leg — same class as page_views). The
pause check fails open: if Turso is unreachable the email still sends.

The joke: generated per-send with the Anthropic API (Haiku tier), falling back
to a canned rotation — the email must send even when the API doesn't.
"""

import hmac
import json
import os
import time
import urllib.error
import urllib.request
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from auth_helper import _sign, _unsign, get_role
from turso_helper import turso_query

# (name, url, deep) — deep targets return JSON dependency detail and non-2xx
# on failure. Grow this list as apps adopt docs/health-convention.md.
TARGETS = [
    ("garm", "https://garm.prompt-labs.org/api/health?db=1", True),
    ("prompt-labs.org", "https://prompt-labs.org/api/info", False),
]

PAUSE_DAYS = 7
PAUSE_TOKEN_MAX_AGE = 45 * 86400  # links in old emails keep working ~45 days
FETCH_TIMEOUT = 8
JOKE_MODEL = "claude-haiku-4-5-20251001"

CANNED_JOKES = [
    "I told my uptime monitor a joke. It didn't laugh — no response at all. Filing that as an incident.",
    "A TCP packet walks into a bar and says: 'I'd like a beer.' Bartender: 'You'd like a beer?' 'Yes, a beer.'",
    "There are two hard problems in computing: cache invalidation, naming things, and off-by-one errors.",
    "My health check returns 200 OK but honestly it's been under a lot of pressure lately.",
    "Why do programmers confuse Halloween and Christmas? Because OCT 31 == DEC 25.",
    "The cron job and I have a lot in common: we both show up once a day and immediately email someone about our problems.",
]


def _utc(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _get_paused_until():
    """ISO timestamp the emails are paused until, or None. Fails open."""
    try:
        rows = turso_query(
            "SELECT value FROM health_email_state WHERE key = 'paused_until'"
        )
        return rows[0]["value"] if rows else None
    except Exception as e:
        print(f"health_report: pause check failed open: {e}"[:200])
        return None


def _set_paused_until(iso):
    turso_query(
        "INSERT INTO health_email_state (key, value, updated_at) "
        "VALUES ('paused_until', ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        [iso, _utc()],
    )


def _make_pause_token():
    return _sign({"exp": int(time.time()) + PAUSE_TOKEN_MAX_AGE, "act": "pause-health"})


def _verify_pause_token(token):
    payload = _unsign(token)
    if not payload or payload.get("act") != "pause-health":
        return False
    return payload.get("exp", 0) > time.time()


def _check_target(name, url, deep=False):
    """Poll one health endpoint. Never raises."""
    t0 = time.time()
    status, body = None, b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "prompt-lab-health/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            status = resp.status
            body = resp.read(4096)
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read(4096)
        except Exception:
            body = b""
    except Exception as e:
        return {"name": name, "ok": False, "status": None,
                "note": f"unreachable ({type(e).__name__})",
                "ms": int((time.time() - t0) * 1000)}
    note = ""
    if deep:
        try:
            data = json.loads(body.decode())
            bits = []
            if "db" in data:
                bits.append("db ok" if data["db"] else "db DOWN")
            howl = data.get("howl") or {}
            if "ageSeconds" in howl:
                state = "STALE" if howl.get("stale") else "ok"
                bits.append(f"howl cron {state} ({howl['ageSeconds'] / 3600:.1f}h ago)")
            note = ", ".join(bits)
        except Exception:
            note = "unparseable health body"
    return {"name": name, "ok": 200 <= (status or 0) < 300, "status": status,
            "note": note, "ms": int((time.time() - t0) * 1000)}


def _joke():
    try:
        from anthropic import Anthropic

        resp = Anthropic().messages.create(
            model=JOKE_MODEL,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"Today is {_utc()[:10]}. Tell one short, original, genuinely "
                    "funny joke about software, infrastructure, or monitoring — "
                    "the closer for a daily systems-health email. Just the joke, "
                    "no preamble, no quotation marks."
                ),
            }],
        )
        joke = resp.content[0].text.strip()
        if joke:
            return joke
    except Exception as e:
        print(f"health_report: joke API failed, using canned: {e}"[:200])
    return CANNED_JOKES[int(time.time() // 86400) % len(CANNED_JOKES)]


TUNE_PROMPT = (
    "Tune the daily health email (web/api/health_report.py, issue #34): "
    "<what you want changed>"
)


def _compose(results, joke, pause_url):
    """Return (subject, text, html)."""
    up = [r for r in results if r["ok"]]
    down = [r for r in results if not r["ok"]]
    if down:
        subject = (f"🔴 ecosystem health: {', '.join(r['name'] for r in down)} DOWN "
                   f"({len(up)}/{len(results)} up)")
    else:
        subject = f"✅ ecosystem health: {len(up)}/{len(results)} up"

    lines = []
    for r in results:
        mark = "up" if r["ok"] else "DOWN"
        status = r["status"] if r["status"] is not None else "—"
        note = f" — {r['note']}" if r["note"] else ""
        lines.append(f"{r['name']}: {mark} ({status}, {r['ms']}ms){note}")

    text = "\n".join(lines) + (
        "\n\n--\n"
        f"Pause these emails for a week: {pause_url}\n\n"
        f"To tune this email, tell the prompt-lab agent:\n\"{TUNE_PROMPT}\"\n\n"
        f"{joke}\n"
    )

    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'><b>{escape(r['name'])}</b></td>"
        f"<td style='padding:4px 12px 4px 0;color:{'#2e7d32' if r['ok'] else '#c62828'}'>"
        f"{'up' if r['ok'] else 'DOWN'}</td>"
        f"<td style='padding:4px 12px 4px 0'>{r['status'] if r['status'] is not None else '—'}"
        f" · {r['ms']}ms</td>"
        f"<td style='padding:4px 0'>{escape(r['note'] or '')}</td></tr>"
        for r in results
    )
    html = (
        "<div style='font-family:-apple-system,sans-serif;font-size:15px;color:#222'>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        f"<p><a href='{escape(pause_url, quote=True)}'>Pause these emails for a week</a></p>"
        "<p style='color:#666'>To tune this email, tell the prompt-lab agent:<br>"
        f"<code>{escape(TUNE_PROMPT)}</code></p>"
        f"<p style='font-style:italic'>{escape(joke)}</p>"
        "</div>"
    )
    return subject, text, html


def _send_email(subject, html, text):
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("HEALTH_TO_EMAIL")
    if not api_key or not to_email:
        raise RuntimeError("RESEND_API_KEY and HEALTH_TO_EMAIL must be set")
    from_email = os.environ.get(
        "HEALTH_FROM_EMAIL", "Prompt Lab Health <health@prompt-labs.org>"
    )
    payload = json.dumps({
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "prompt-lab/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlsplit(self.path).query)
            if (qs.get("action") or [""])[0] == "pause":
                self._handle_pause(qs)
                return

            if not self._authorized():
                self._json({"error": "unauthorized"}, 401)
                return

            paused_until = _get_paused_until()
            paused = bool(paused_until and paused_until > _utc())

            results = [_check_target(n, u, d) for n, u, d in TARGETS]

            if "dry" in qs:
                self._json({"targets": results, "paused_until": paused_until,
                            "would_send": not paused})
                return
            if paused:
                self._json({"skipped": "paused", "paused_until": paused_until})
                return

            pause_url = ("https://prompt-labs.org/api/health_report"
                         f"?action=pause&token={_make_pause_token()}")
            subject, text, html = _compose(results, _joke(), pause_url)
            _send_email(subject, html, text)
            self._json({"sent": True,
                        "down": [r["name"] for r in results if not r["ok"]]})
        except Exception as e:
            print(f"health_report error: {e}"[:300])
            self._json({"error": str(e)}, 500)

    def _authorized(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("authorization", "") or self.headers.get("Authorization", "")
        if secret and hmac.compare_digest(auth, f"Bearer {secret}"):
            return True
        return get_role(self.headers) == "admin"

    def _handle_pause(self, qs):
        token = (qs.get("token") or [""])[0]
        if not _verify_pause_token(token):
            self._html("Invalid or expired pause link.", 403)
            return
        until = _utc(time.time() + PAUSE_DAYS * 86400)
        _set_paused_until(until)
        self._html(f"Health emails paused until {until[:10]}. "
                   "They resume automatically after that.")

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, message, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(
            f"<html><body style='font-family:-apple-system,sans-serif;"
            f"margin:3rem'><p>{escape(message)}</p></body></html>".encode()
        )
