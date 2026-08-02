"""GET /api/health_report — daily ecosystem health summary email (issue #34).

prompt-lab owns health REPORTING for the ecosystem (garm handoff 2026-07-29):
a Vercel cron hits this endpoint daily, it polls each target's health endpoint
(convention: docs/health-convention.md) and emails a summary via Resend.
Immediate alerting is deliberately NOT here — UptimeRobot on independent infra
is the pager; this is the trend layer, and it dies with the shared stack.

Auth: two levels. `?dry=1` (poll targets, return JSON, send nothing) is open to
ANY authenticated role — that's what the `#/health` page reads, so readers see
status. Triggering a send is cron-or-admin: the cron authenticates with
`Authorization: Bearer $CRON_SECRET` (Vercel attaches it automatically when the
env var is set) and an admin cookie also works for manual runs. An authenticated
reader asking for a send gets 403, not 401 — the distinction is deliberate
("you're logged in but may not trigger this"). Anonymous gets 401, and is
rejected before any target is polled.

Pause: each email carries an HMAC-signed link (`?action=pause&token=…`) that
suppresses sends for 7 days — state in the Turso `health_email_state` table
(cloud-direct, no local copy, no sync leg — same class as page_views). The
pause check fails open: if Turso is unreachable the email still sends.

Two kinds of check. `TARGETS` answers "is this URL up" by polling. `HEARTBEATS`
answers "did this recurring job run" by measuring the age of the artifact the
job produces (issue #45) — a URL check can never see a dead cron, and that is
the failure class that has actually bitten us.

The same cron also archives yesterday's UptimeRobot ratios into `uptime_daily`
(_archive_uptime, phase 1 of docs/plan-2026-08-01-uptime-dashboard.md). It rides
this handler because Vercel Hobby crons are daily and one already exists here.

The joke: generated per-send with the Anthropic API (Haiku tier), falling back
to a canned rotation — the email must send even when the API doesn't.
"""

import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from auth_helper import _sign, _unsign, get_role
from turso_helper import turso_query

# (name, url, deep) — deep targets return JSON dependency detail and non-2xx
# on failure. Grow this list as apps adopt docs/health-convention.md.
TARGETS = [
    ("garm", "https://garm.prompt-labs.org/api/health?db=1", True),
    ("prompt-labs.org", "https://prompt-labs.org/api/health?db=1", True),
]

# (label, sql, max_age_days) — artifact freshness, issue #45.
#
# "Alarm on the artifact, not the job's exit status." Every one of the six
# incidents behind #45 was a job that kept running while its output stopped,
# and in each the job's own reporting was what failed. So this checks the real
# output rather than a side-channel claim that the job ran: a synthetic ping
# can succeed while the artifact is missing, a max(date) cannot.
#
# The check lives outside the jobs it watches — they run on launchd on the
# mini and write through the Turso sync; this runs on Vercel and reads. If the
# mini dies entirely, these stop advancing and the email says so.
#
# Thresholds are DAYS, not hours: every artifact here is date-granular, so an
# hours figure would imply precision that doesn't exist. "2" means one missed
# night is quiet and two is a breach — #45's stated bar was catching the review
# email on night two rather than night sixty.
HEARTBEATS = [
    ("review email", "SELECT max(date) AS d FROM review_snapshots "
                     "WHERE review_type IN ('daily_email', 'weekly_email')", 2),
    ("synthesizer", "SELECT max(date) AS d FROM daily_summaries", 2),
    ("weekly rollups", "SELECT max(week_start) AS d FROM weekly_rollups", 10),
    # Anthropic's Admin API reports a day behind, so yesterday is the normal
    # newest row — 2 would alarm on a healthy pipeline.
    ("cost pull + sync", "SELECT max(date) AS d FROM api_costs", 3),
    ("bi-monthly report", "SELECT max(date) AS d FROM review_snapshots "
                          "WHERE review_type = 'monthly_report'", 20),
    # Added 2026-08-02 after the archive wrote on Aug 1 and not Aug 2, and
    # nothing said so for two days. READ THE LIMIT BEFORE TRUSTING THIS ONE:
    # unlike every entry above, the watcher is not outside the watched job —
    # this same request writes uptime_daily and then reports on it. So it
    # catches "cron alive, pull broken" and CANNOT catch "cron dead", which
    # degrades to "no email arrived" — the weakest signal in the system and the
    # one that hid the review email for sixty nights. Closing that properly
    # needs a check on infrastructure that fails independently of Vercel's
    # scheduler; UptimeRobot's HEARTBEAT type is paid-only, which is what sent
    # #45 down the artifact-freshness route in the first place.
    ("uptime archive", "SELECT max(date) AS d FROM uptime_daily", 2),
]

# --- uptime archive ---------------------------------------------------------
# v3 provisions monitors (scripts/uptimerobot.py) but has NO history endpoints:
# /logs, /response-times and /uptimes all 404 and lastDayUptimes comes back
# empty. Legacy v2 is the only source of history and works on the free plan
# (probed live 2026-07-31 — the published docs are thin and partly wrong).
UPTIMEROBOT_API = "https://api.uptimerobot.com/v2/getMonitors"
UPTIME_RATIO_WINDOWS = "1-7-30"  # days, and the order they come back in
UPTIME_STATUS = {0: "PAUSED", 1: "PENDING", 2: "UP", 8: "SEEMS_DOWN", 9: "DOWN"}

UPTIME_UPSERT_SQL = (
    "INSERT INTO uptime_daily "
    "(date, monitor, uptime_1d, uptime_7d, uptime_30d, avg_response_ms, status) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(date, monitor) DO UPDATE SET "
    "uptime_1d = excluded.uptime_1d, uptime_7d = excluded.uptime_7d, "
    "uptime_30d = excluded.uptime_30d, "
    "avg_response_ms = excluded.avg_response_ms, status = excluded.status"
)

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


def _check_heartbeats():
    """Freshness of each declared artifact. Never raises.

    ok is tri-state and the distinction is the point:
      True  — fresh
      False — stale, or never produced at all
      None  — could not check

    A failed query must NOT report fresh. The pause check above deliberately
    fails open (a Turso outage shouldn't block an email); this one must fail
    *loud*, because "absence recorded as nothing" is the exact bug #45 exists
    to kill. A freshness check that goes quiet when it can't see is worse than
    no check, since it manufactures confidence.
    """
    today = datetime.now(timezone.utc).date()
    out = []
    for name, sql, max_age in HEARTBEATS:
        entry = {"name": name, "max_age_days": max_age, "last": None,
                 "age_days": None, "ok": None, "note": ""}
        try:
            rows = turso_query(sql)
        except Exception as e:
            entry["note"] = f"could not check ({type(e).__name__})"
            print(f"health_report: heartbeat {name} unreadable: {e}"[:200])
            out.append(entry)
            continue
        raw = rows[0].get("d") if rows else None
        if not raw:
            entry["ok"] = False
            entry["note"] = "no rows — never produced"
            out.append(entry)
            continue
        try:
            last = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            entry["note"] = f"unparseable date {str(raw)[:20]!r}"
            out.append(entry)
            continue
        age = (today - last).days
        entry.update(last=last.isoformat(), age_days=age, ok=age < max_age)
        if not entry["ok"]:
            entry["note"] = f"{age}d old, expected within {max_age}d"
        out.append(entry)
    return out


def _fetch_uptime_monitors(api_key):
    """One v2 getMonitors call. Module-level so tests can replace it."""
    payload = json.dumps({
        "api_key": api_key,
        "format": "json",
        "custom_uptime_ratios": UPTIME_RATIO_WINDOWS,
        "response_times": 1,
    }).encode()
    req = urllib.request.Request(
        UPTIMEROBOT_API,
        data=payload,
        headers={"Content-Type": "application/json",
                 "User-Agent": "prompt-lab-health/1.0"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        data = json.loads(resp.read())
    # v2 answers 200 with stat="fail" on an auth or quota error, so the HTTP
    # status alone would read as success.
    if data.get("stat") != "ok":
        raise RuntimeError(f"uptimerobot returned {str(data)[:200]}")
    return data.get("monitors") or []


def _split_ratios(raw):
    """`custom_uptime_ratio` is a STRING — "100.000-99.980-99.990" — in the
    order requested by custom_uptime_ratios (1d-7d-30d). Same trap class as
    Turso handing back aggregates as strings: left untouched these "numbers"
    are text and every average downstream is nonsense. Returns three floats,
    None for anything unparseable."""
    out = []
    for part in str(raw or "").split("-")[:3]:
        try:
            out.append(float(part))
        except ValueError:
            out.append(None)
    return out + [None] * (3 - len(out))


def _avg_ms(samples):
    """Collapse the response-time samples to one daily average.

    Deliberately an average, not the raw 5-minute series: that would be ~2,600
    rows per monitor per day for percentiles no one has asked for yet
    (decision 1 in the plan). None when there are no samples — an unknown
    latency, which 0 would misreport as instant."""
    values = []
    for s in samples or []:
        try:
            values.append(float(s.get("value")))
        except (AttributeError, TypeError, ValueError):
            continue
    return int(round(sum(values) / len(values))) if values else None


def _uptime_row(monitor, date):
    """Map one v2 monitor object to an `uptime_daily` row."""
    u1, u7, u30 = _split_ratios(monitor.get("custom_uptime_ratio"))
    try:
        status = UPTIME_STATUS.get(int(monitor.get("status")), "UNKNOWN")
    except (TypeError, ValueError):
        status = "UNKNOWN"
    return {
        "date": date,
        "monitor": monitor.get("friendly_name") or monitor.get("url") or "unnamed",
        "uptime_1d": u1,
        "uptime_7d": u7,
        "uptime_30d": u30,
        "avg_response_ms": _avg_ms(monitor.get("response_times")),
        "status": status,
    }


def _archive_uptime():
    """Archive today's UptimeRobot ratios into `uptime_daily`. Never raises.

    UptimeRobot keeps 3 months of history and we want forever — that gap is the
    only reason this exists. prompt-lab still samples nothing itself.

    Wrapped the way record_login is in callback.py: swallow, log, continue. The
    email is the more important artifact, and a monitoring side-quest must never
    be able to kill it. Returns the number of rows written.
    """
    api_key = os.environ.get("UPTIMEROBOT_API_KEY")
    if not api_key:
        print("health_report: UPTIMEROBOT_API_KEY unset — uptime archive skipped")
        return 0
    try:
        monitors = _fetch_uptime_monitors(api_key)
    except Exception as e:
        print(f"health_report: uptime pull failed: {e}"[:300])
        return 0

    date = _utc()[:10]
    written = 0
    for m in monitors:
        row = _uptime_row(m, date)
        try:
            turso_query(UPTIME_UPSERT_SQL, [
                row["date"], row["monitor"], row["uptime_1d"], row["uptime_7d"],
                row["uptime_30d"], row["avg_response_ms"], row["status"],
            ])
            written += 1
        except Exception as e:
            # Per monitor, so one bad row doesn't strand the rest.
            print(f"health_report: uptime write failed for "
                  f"{row['monitor']}: {e}"[:300])
    return written


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


def _compose(results, joke, pause_url, heartbeats=None):
    """Return (subject, text, html)."""
    heartbeats = heartbeats or []
    up = [r for r in results if r["ok"]]
    down = [r for r in results if not r["ok"]]
    stale = [h for h in heartbeats if h["ok"] is False]
    unknown = [h for h in heartbeats if h["ok"] is None]

    if down:
        subject = (f"🔴 ecosystem health: {', '.join(r['name'] for r in down)} DOWN "
                   f"({len(up)}/{len(results)} up)")
    elif stale:
        subject = (f"🟡 ecosystem health: {len(up)}/{len(results)} up · "
                   f"{len(stale)} stale ({', '.join(h['name'] for h in stale)})")
    elif unknown:
        subject = (f"🟡 ecosystem health: {len(up)}/{len(results)} up · "
                   f"{len(unknown)} unchecked")
    else:
        subject = f"✅ ecosystem health: {len(up)}/{len(results)} up"

    lines = []
    for r in results:
        mark = "up" if r["ok"] else "DOWN"
        status = r["status"] if r["status"] is not None else "—"
        note = f" — {r['note']}" if r["note"] else ""
        lines.append(f"{r['name']}: {mark} ({status}, {r['ms']}ms){note}")

    # Silent when everything is fresh — one line, so the email stays glanceable.
    if heartbeats:
        lines.append("")
        if not stale and not unknown:
            lines.append(f"heartbeats: all {len(heartbeats)} artifacts fresh")
        else:
            lines.append("heartbeats:")
            for h in stale + unknown:
                lines.append(f"  {h['name']}: {h['note']}"
                             + (f" (last {h['last']})" if h["last"] else ""))

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
    if not heartbeats:
        hb_html = ""
    elif not stale and not unknown:
        hb_html = ("<p style='color:#2e7d32'>heartbeats: all "
                   f"{len(heartbeats)} artifacts fresh</p>")
    else:
        items = "".join(
            f"<li><b>{escape(h['name'])}</b> — {escape(h['note'])}"
            + (f" (last {escape(str(h['last']))})" if h["last"] else "") + "</li>"
            for h in stale + unknown
        )
        hb_html = (f"<p style='color:#c62828;margin-bottom:4px'>heartbeats: "
                   f"{len(stale)} stale, {len(unknown)} unchecked</p>"
                   f"<ul style='margin-top:0'>{items}</ul>")

    html = (
        "<div style='font-family:-apple-system,sans-serif;font-size:15px;color:#222'>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        f"{hb_html}"
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

            dry = "dry" in qs
            denial = self._denial(dry)
            if denial:
                # Before any _check_target call: an unauthorized caller must not
                # be able to make us do the polling work.
                self._json(denial[1], denial[0])
                return

            paused_until = _get_paused_until()
            paused = bool(paused_until and paused_until > _utc())

            results = [_check_target(n, u, d) for n, u, d in TARGETS]
            heartbeats = _check_heartbeats()

            if dry:
                self._json({"targets": results, "heartbeats": heartbeats,
                            "paused_until": paused_until,
                            "would_send": not paused})
                return

            # Send path only: ?dry=1 is open to any authenticated role (it is
            # what #/health reads), so writing there would let a reader trigger
            # a write. Ahead of the pause check on purpose — pausing the EMAIL
            # for a week must not punch a week-long hole in the archive.
            #
            # Deliberately AFTER _check_heartbeats above: the "uptime archive"
            # heartbeat must report the archive as it stood when this run began.
            # Move the write earlier and it would refresh the very row it is
            # about to grade, reporting fresh on every run forever.
            uptime_rows = _archive_uptime()

            if paused:
                self._json({"skipped": "paused", "paused_until": paused_until,
                            "uptime_rows": uptime_rows})
                return

            pause_url = ("https://prompt-labs.org/api/health_report"
                         f"?action=pause&token={_make_pause_token()}")
            subject, text, html = _compose(results, _joke(), pause_url, heartbeats)
            _send_email(subject, html, text)
            self._json({"sent": True,
                        "down": [r["name"] for r in results if not r["ok"]],
                        "stale": [h["name"] for h in heartbeats if h["ok"] is False],
                        "uptime_rows": uptime_rows})
        except Exception as e:
            print(f"health_report error: {e}"[:300])
            self._json({"error": str(e)}, 500)

    def _is_cron(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("authorization", "") or self.headers.get("Authorization", "")
        return bool(secret) and hmac.compare_digest(auth, f"Bearer {secret}")

    def _denial(self, dry):
        """(status, body) to refuse this caller, or None if it may proceed.

        Read-only dry runs: any authenticated role. Sends: cron or admin only.
        """
        if self._is_cron():
            return None
        role = get_role(self.headers)
        if role is None:
            return 401, {"error": "unauthorized"}
        if not dry and role != "admin":
            return 403, {"error": "forbidden", "detail": "sending requires admin"}
        return None

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
