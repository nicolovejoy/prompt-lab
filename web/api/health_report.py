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

Three kinds of check. `TARGETS` answers "is this URL up" by polling.
`HEARTBEATS` answers "did this recurring job run" by measuring the age of the
artifact the job produces (issue #45) — a URL check can never see a dead cron,
and that is the failure class that has actually bitten us. `_check_nightly_run`
adds a SECOND AXIS beside the heartbeats, never a replacement: it reads the
pipeline's own run record, which is a self-report and therefore exactly what
#45 says not to rely on alone, but which can say things an artifact age cannot
— which stage broke, and (by cross-checking its `claims` against Turso)
whether a missing row means "never produced" or "produced but never synced".

The same cron also archives yesterday's UptimeRobot ratios into `uptime_daily`
(_archive_uptime, phase 1 of docs/plan-2026-08-01-uptime-dashboard.md). It rides
this handler because Vercel Hobby crons are daily and one already exists here.

The joke: generated per-send with the Anthropic API (Haiku tier), falling back
to a canned rotation — the email must send even when the API doesn't.

Cron schedule (issue #48): `web/vercel.json`'s `"0 15 * * *"` is 8am Pacific
in summer and 7am in winter — Vercel crons are UTC-only and don't know about
DST. Decided 2026-08-22 (Nico): accept the drift rather than add a
month-based split, which would still be imprecise near the actual transition
dates and adds permanent complexity for a once-a-day informational email.
"""

import hmac
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from access_helper import resolve_access
from artifact_checks import ARTIFACT_CHECKS
from auth_helper import _sign, _unsign
from day_helper import lab_today
from turso_helper import turso_query

# (name, url, deep) — deep targets return JSON dependency detail and non-2xx
# on failure.
#
# This list and HTTP_MONITORS in scripts/uptimerobot.py are two declarations of
# one intent: the set of URLs worth watching. They serve different layers —
# UptimeRobot pages at 5-minute resolution, this reports a daily trend — but a
# URL in one and not the other is drift, not a decision. test_web_api.py pins
# that every url here also appears there; add to both or neither.
#
# `deep` mirrors the URL: `?db=1` asks the app to touch its dependencies, so
# there is a body worth parsing. bakerylouise and ibuild4you are shallow by
# their own repos' call (ISR-cached pages, and a plain path that already
# reports per-dependency detail).
TARGETS = [
    # Shallow since 2026-08-18, same failure as byside below: garm's Neon
    # database is on the free tier (5-minute autosuspend), and this list gets
    # re-polled on every #/health page load on top of UptimeRobot's 5-minute
    # cron — two sources of deep hits, neither letting compute sleep. Neon
    # reported garm's project over its 100 CU-hour monthly quota with 12+
    # days left before reset. See scripts/uptimerobot.py for the full
    # reasoning and the confirming numbers.
    ("garm", "https://garm.prompt-labs.org/api/health", False),
    ("prompt-labs.org", "https://prompt-labs.org/api/health?db=1", True),
    ("ibuild4you", "https://ibuild4you.com/api/health", True),
    # Shallow since 2026-08-14: byside's Neon free tier autosuspends after 5
    # minutes idle, and #/health re-polls every TARGET on each page load, so a
    # deep check here kept the compute permanently awake on top of the 5-minute
    # UptimeRobot poll. See scripts/uptimerobot.py for the full reasoning.
    ("byside", "https://by-side.net/api/health", False),
    ("pianohouse", "https://www.pianohouseproject.org/api/health?db=1", True),
    ("bakerylouise", "https://bakerylouise.com/api/health", False),
    # Direct Fly line paired with the www rewrite line below — deep+deep on
    # purpose (musicforge's 2026-08-16 decision; see scripts/uptimerobot.py
    # for the pair-reading table). Only-www-red means Vercel or the rewrite.
    ("musicforge-fly", "https://musicforge.fly.dev/api/health?db=1", True),
    ("musicforge", "https://www.musicforge.org/api/health?db=1", True),
    ("prntd", "https://prntd.org/api/health?db=1", True),
    # Two artifact checks behind one URL: collector freshness (Influx last
    # point vs the ~30s poll) and backup freshness (restic snapshot's own
    # timestamp). No ?db= param — the checks[] body carries the detail.
    ("span", "https://span.pianohouseproject.org/api/health", True),
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
#
# The first five entries are shared with nightly_pipeline.collect_claims —
# see web/artifact_checks.py for why they must not drift into two lists.
HEARTBEATS = ARTIFACT_CHECKS + [
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
            # The other shape the convention produces: a checks[] array of named
            # dependencies (ibuild4you, byside, pianohouse). Name only the failures
            # — a target with nine green checks would otherwise bury the one red
            # one under an unreadable line. Silence here means all passed.
            checks = data.get("checks")
            if isinstance(checks, list) and checks:
                bad = [c.get("name", "?") for c in checks
                       if isinstance(c, dict) and not c.get("ok")]
                bits.append(f"{len(checks) - len(bad)}/{len(checks)} checks ok"
                            + (f" — {', '.join(bad)} DOWN" if bad else ""))
            note = ", ".join(bits)
        except Exception:
            note = "unparseable health body"
    return {"name": name, "ok": 200 <= (status or 0) < 300, "status": status,
            "note": note, "ms": int((time.time() - t0) * 1000)}


def _check_targets():
    """Poll every target concurrently, in TARGETS order.

    Sequential polling cost the sum of the round trips, which was fine at two
    targets and is ~8s at eight — and `#/health` pays it on every page load,
    since a remembered "up" is a stale claim and the page is deliberately
    uncached. `_check_target` never raises and does nothing but wait on a
    socket, so a thread pool is the whole fix; `map` preserves order.
    """
    with ThreadPoolExecutor(max_workers=len(TARGETS)) as pool:
        return list(pool.map(lambda t: _check_target(*t), TARGETS))


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
    # Lab day, not UTC (#48): every artifact graded here has its `date` written
    # by a job on the mini's Pacific clock, so a UTC `today` reports each one a
    # day older than it is for the seven hours after 5pm PDT — enough to fire a
    # 2-day threshold on a perfectly healthy pipeline.
    today = lab_today()
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


# Max age in LAB DAYS for the nightly run itself. 2 matches the artifact
# thresholds: one missed night is quiet (a closed lid is normal and was
# accepted when the jobs moved to the laptop), two is a breach.
NIGHTLY_RUN_MAX_AGE_DAYS = 2

# Stage outcomes that mean the stage did not do its work. "not-due" is
# deliberately absent — the bi-monthly report reporting not-due is the healthy
# answer on 29 nights out of 30.
FAILED_OUTCOMES = ("failed", "timeout", "skipped")

NIGHTLY_RUN_SQL = (
    "SELECT run_id, host, started_at, lab_date, finished_at, status, "
    "stages, claims, exit_code FROM nightly_runs "
    "ORDER BY started_at DESC LIMIT 1"
)


def _decode_json_column(value, default):
    """`stages`/`claims` arrive as JSON text from Turso. Never raises."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, type(default)) else default


def _claims_vs_remote(claims, heartbeats):
    """Artifacts the run says it produced that Turso does not have.

    This is what makes the sync leg checkable. Without it, "local has it and
    the cloud does not" is indistinguishable from "the job never produced
    it" — different bugs with different fixes, and the health email has never
    been able to tell them apart.

    Only a claim STRICTLY NEWER than the remote value is a mismatch: the
    remote being ahead is normal after a later sync from another source, and
    flagging it would make the check cry wolf.

    An artifact whose own heartbeat could not be checked (ok is None) is
    SKIPPED, not flagged. Its `last` is None for want of an answer, not
    because Turso is empty — reading that as "claimed but missing" would turn
    one Turso outage into a fleet of invented publish failures.
    """
    by_name = {h["name"]: h for h in heartbeats if h.get("ok") is not None}
    out = []
    for label, claimed in (claims or {}).items():
        if label not in by_name:
            continue
        remote = by_name[label].get("last")
        if claimed and remote and str(claimed) > str(remote):
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": str(remote)})
        elif claimed and not remote:
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": None})
    return out


def _check_nightly_run(heartbeats=None):
    """The newest nightly pipeline run, graded and cross-checked.

    A SECOND AXIS, not a replacement. The artifact heartbeats above ask "did
    the output appear"; this asks "did the job run, and what did it say
    happened". Both are needed: a run record is a self-report, and #45 exists
    because self-reports are exactly what failed in all six incidents. Keep
    HEARTBEATS intact.

    Graded on `lab_date` — the day the run STARTED — never on arrival time.
    A catch-up push sends several days of backlog at once, and grading on
    arrival would make three dead nights look like they all happened at 2am
    today, silently undoing the mechanism.

    Fails loud (ok=None) when unreadable, like _check_heartbeats and unlike
    the pause lookup.
    """
    entry = {"lab_date": None, "host": None, "status": None,
             "age_days": None, "ok": None, "stages": [], "mismatches": [],
             "note": ""}
    try:
        rows = turso_query(NIGHTLY_RUN_SQL)
    except Exception as e:
        entry["note"] = f"could not check ({type(e).__name__})"
        print(f"health_report: nightly run unreadable: {e}"[:200])
        return entry

    if not rows:
        entry["ok"] = False
        entry["note"] = "no rows — never produced"
        return entry

    row = rows[0]
    entry["host"] = row.get("host")
    entry["status"] = row.get("status")
    entry["lab_date"] = str(row.get("lab_date") or "")[:10]
    try:
        last = datetime.strptime(entry["lab_date"], "%Y-%m-%d").date()
    except ValueError:
        entry["ok"] = False
        entry["note"] = f"unparseable lab_date {entry['lab_date']!r}"
        return entry

    entry["age_days"] = (lab_today() - last).days
    if entry["age_days"] > NIGHTLY_RUN_MAX_AGE_DAYS:
        entry["ok"] = False
        entry["note"] = (f"no run for {entry['age_days']} days — "
                         "host has been off")
        return entry

    entry["stages"] = _decode_json_column(row.get("stages"), [])
    bad = [s for s in entry["stages"] if s.get("outcome") in FAILED_OUTCOMES]
    if entry["status"] == "running":
        entry["ok"] = False
        entry["note"] = "started but never finished — died mid-run"
        return entry
    if bad:
        entry["ok"] = False
        entry["note"] = ", ".join(f"{s.get('name')}: {s['outcome']}"
                                  for s in bad)
        return entry

    entry["mismatches"] = _claims_vs_remote(
        _decode_json_column(row.get("claims"), {}), heartbeats or [])
    if entry["mismatches"]:
        entry["ok"] = False
        entry["note"] = ("claimed but not in Turso: "
                         + ", ".join(m["artifact"]
                                     for m in entry["mismatches"]))
        return entry

    entry["ok"] = True
    return entry


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

    # Lab day (#48). At the 15:00 UTC cron this is the same string UTC gives,
    # so no existing row shifts and the never-backfill invariant is untouched —
    # but a manual run after 5pm Pacific used to file under tomorrow, which the
    # chart then rendered as a gap in today.
    date = lab_today().isoformat()
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


def _nightly_run_headline(nr):
    """One line for the run record. Terse on a good night, by design."""
    if not nr.get("lab_date"):
        return f"nightly run: {nr.get('note') or 'could not check'}"
    where = f" on {nr['host']}" if nr.get("host") else ""
    head = f"nightly run: {nr['lab_date']} {nr.get('status') or '?'}{where}"
    if nr.get("ok"):
        return f"{head} — {len(nr.get('stages') or [])} stages"
    return f"{head} — {nr.get('note') or 'not ok'}"


def _nightly_run_details(nr):
    """The lines that only appear when something is wrong: which stage broke,
    and which artifact the run claims Turso is missing."""
    out = []
    for s in nr.get("stages") or []:
        if s.get("outcome") in FAILED_OUTCOMES:
            out.append(f"{s.get('name')}: {s.get('outcome')}"
                       + (f" — {s['detail']}" if s.get("detail") else ""))
    for m in nr.get("mismatches") or []:
        out.append(f"{m['artifact']}: run claimed {m['claimed']}, Turso has "
                   f"{m['remote'] or 'nothing'} — publish is dropping rows")
    return out


def _compose(results, joke, pause_url, heartbeats=None, uptime_rows=None,
             nightly_run=None):
    """Return (subject, text, html)."""
    heartbeats = heartbeats or []
    up = [r for r in results if r["ok"]]
    down = [r for r in results if not r["ok"]]
    stale = [h for h in heartbeats if h["ok"] is False]
    unknown = [h for h in heartbeats if h["ok"] is None]

    # The run record escalates the subject on the SAME axis as a stale or
    # unchecked heartbeat, rather than getting an escalation of its own. A red
    # line in the body under a green subject is this repo's signature failure
    # — the sensor works and the output goes nowhere — and shipping that
    # inside the mechanism built to detect it would be the joke of the year.
    # Kept out of `stale`/`unknown` themselves: those lists render the
    # heartbeats block, and the run record has its own line below it.
    run_ok = nightly_run.get("ok") if nightly_run else True
    stale_names = ([h["name"] for h in stale]
                   + (["nightly run"] if run_ok is False else []))
    unchecked = len(unknown) + (1 if run_ok is None else 0)

    if down:
        subject = (f"🔴 ecosystem health: {', '.join(r['name'] for r in down)} DOWN "
                   f"({len(up)}/{len(results)} up)")
    elif stale_names:
        subject = (f"🟡 ecosystem health: {len(up)}/{len(results)} up · "
                   f"{len(stale_names)} stale ({', '.join(stale_names)})")
    elif unchecked:
        subject = (f"🟡 ecosystem health: {len(up)}/{len(results)} up · "
                   f"{unchecked} unchecked")
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

    # The second axis (nightly run record). Sits under the heartbeats because
    # it answers the other half of the question they ask: they see whether the
    # artifact appeared, this sees whether the job ran and what it says
    # happened. Never a substitute for them — a self-report is exactly what
    # failed in every #45 incident.
    if nightly_run:
        lines.append("")
        lines.append(_nightly_run_headline(nightly_run))
        if not nightly_run.get("ok"):
            lines.extend(f"  {d}" for d in _nightly_run_details(nightly_run))

    # The archive result must reach the inbox: the JSON response is unread and
    # Vercel logs evaporate in ~an hour, so a 0-row pull is otherwise invisible.
    if uptime_rows is not None:
        lines.append("")
        lines.append(f"{uptime_rows} monitors archived" if uptime_rows
                     else "uptime archive: 0 rows written")

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

    if not nightly_run:
        run_html = ""
    elif nightly_run.get("ok"):
        run_html = (f"<p style='color:#2e7d32'>"
                    f"{escape(_nightly_run_headline(nightly_run))}</p>")
    else:
        details = "".join(f"<li>{escape(d)}</li>"
                          for d in _nightly_run_details(nightly_run))
        run_html = (f"<p style='color:#c62828;margin-bottom:4px'>"
                    f"{escape(_nightly_run_headline(nightly_run))}</p>"
                    + (f"<ul style='margin-top:0'>{details}</ul>"
                       if details else ""))

    if uptime_rows is None:
        archive_html = ""
    elif uptime_rows:
        archive_html = (f"<p style='color:#666'>{uptime_rows} monitors "
                        "archived</p>")
    else:
        archive_html = ("<p style='color:#c62828'><b>uptime archive: "
                        "0 rows written</b></p>")

    html = (
        "<div style='font-family:-apple-system,sans-serif;font-size:15px;color:#222'>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        f"{hb_html}"
        f"{run_html}"
        f"{archive_html}"
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

            results = _check_targets()
            # Heartbeats first: the run record's claims are graded AGAINST
            # them, so the comparison needs both halves and this order.
            heartbeats = _check_heartbeats()
            nightly_run = _check_nightly_run(heartbeats)

            if dry:
                self._json({"targets": results, "heartbeats": heartbeats,
                            "nightly_run": nightly_run,
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
            subject, text, html = _compose(results, _joke(), pause_url,
                                           heartbeats, uptime_rows,
                                           nightly_run)
            _send_email(subject, html, text)
            # Summarised here (tri-state ok) rather than returned whole, the
            # way `stale` reduces the heartbeats: the send path's JSON is a
            # problem summary. ?dry=1 above carries the full block for
            # #/health.
            self._json({"sent": True,
                        "down": [r["name"] for r in results if not r["ok"]],
                        "stale": [h["name"] for h in heartbeats if h["ok"] is False],
                        "nightly_run": nightly_run["ok"],
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

        Cron bypasses this entirely. Both axes are checked, and they answer
        different questions: the grant-set axis (`access.projects is not
        None`) is the same admin-only gate uptime/visitors use, so a Garm
        reader — filtered or not — never reaches health at all, and an
        unfiltered account under GARM_GATING=off keeps today's behaviour
        uniformly across all three admin-only surfaces. The role axis is
        layered on top of that and is what actually protects the SEND path:
        gating on projects alone would let a reader under GARM_GATING=off
        (role='reader', projects=None — indistinguishable from admin on that
        axis) trigger a real email send, which is the one thing the plan
        says only cron or admin may do.
        """
        if self._is_cron():
            return None
        access = resolve_access(self.headers)
        if access is None:
            return 401, {"error": "unauthorized"}
        if access.projects is not None:
            return 403, {"error": "admin required"}
        if not dry and access.role != "admin":
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
