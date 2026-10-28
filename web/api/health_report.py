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

Layout: the email leads with what needs attention. Above the separator is
one line per problem (`_problems`: a down target, a stale, never-produced or
unchecked heartbeat, each fact about a bad newest run, each older bad night,
a 0-row archive), prefixed NEW today, Day N or Ongoing; on a clean run it is
the single line "nothing needs attention", and the subject is that block in
one line. Below the separator is everything green or grey: the uptime table,
the heartbeat count, a good run's one line, recovered nights, the archive
count. Nothing red goes below, nothing green above. NEW comes from the
`reported_problems` key in `health_email_state`, which holds {problem key:
first lab day reported} for the problems in the last email SENT (read and
written on the send path only, written after the send returns). A failure on
the newest run row is also remembered under its night (`night:<lab_date>`),
so tomorrow, when that row is an older bad night, it is not NEW twice. Day N
is the Nth lab day the problem has existed, its first day being Day 1: a
stale artifact and a bad night date themselves (so they survive a lost
memory); every other problem counts from that remembered first sighting.

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
from datetime import datetime, timedelta
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
    # Shallow: Neon behind it autosuspends; see scripts/uptimerobot.py.
    ("songpath", "https://songpath.vercel.app/api/health", False),
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


# Max age in LAB DAYS for the nightly run itself. Two days of slack on a
# nightly job means a missed night is invisible until it has been missed
# twice, so this is 1. A HEALTHY night grades 0, not 1 — the job runs at 02:30
# and the email at 08:00 on the same lab day, so there is no scheduling offset
# to absorb. The one day of slack is what covers a night whose record could
# not be PUSHED (see the day-late escalation note in CLAUDE.md), which is why
# lowering this to 0 would false-alarm on exactly the outage it exists for.
NIGHTLY_RUN_MAX_AGE_DAYS = 1

# Stage outcomes that mean the stage did not do its work. "not-due" is
# deliberately absent — the bi-monthly report reporting not-due is the healthy
# answer on 29 nights out of 30.
FAILED_OUTCOMES = ("failed", "timeout", "skipped")

# How many lab days back to look for OTHER bad runs beside the newest one.
# This is what stops a backfilled failure from disappearing: the same missing
# network that fails a run also delays its own push, so its row lands in
# Turso days later via `push_runs`' catch-up, older than a newer healthy run
# and therefore never the newest row. Grading only the newest row lets that
# failure go ungraded forever — the catch-up mechanism and the grading
# mechanism cancel out. Widening the read to a window (not the write path;
# `push_runs` catch-up is unchanged) is what closes that gap.
NIGHTLY_RUN_WINDOW_DAYS = 7

# Which artifact heartbeat vouches for a stage's work. An OLDER bad night whose
# failed stages all have a heartbeat dated AFTER that night is "recovered": a
# later run redid the work (cost-pull resumes from its last successful pull,
# the synthesizer re-reads the day), so the red line was noise nobody can act
# on. This never softens the NEWEST row — a failure last night stands until a
# later run proves otherwise — and a stage with no artifact here (scrub, the
# two sync legs) is never recovered, because nothing can vouch for it. The
# heartbeat must be strictly newer than the bad night, not merely "fresh":
# with a 3-day threshold an artifact from the night BEFORE the failure is
# still fresh and proves nothing. Added 2026-10-17 after two transient
# cost-pull network failures stayed red for a week each.
STAGE_ARTIFACT = {
    "cost-pull": "cost pull + sync",
    "synthesizer": "synthesizer",
    "review": "review email",
    "report": "bi-monthly report",
}

NIGHTLY_RUN_SQL = (
    "SELECT run_id, host, started_at, lab_date, finished_at, status, "
    "stages, claims, exit_code FROM nightly_runs "
    "WHERE lab_date >= ? ORDER BY started_at DESC LIMIT 50"
)


def _decode_json_column(value, default):
    """`stages`/`claims` arrive as JSON text from Turso. Never raises.

    Validates the ELEMENTS of a list, not just the outer container: a stray
    `["a", "b"]` would otherwise decode cleanly and then blow up on
    `s.get("outcome")` downstream, escaping this function's caller into the
    handler's outer except — a 500 and NO EMAIL AT ALL. The second axis must
    never be able to silence the first, which is the whole reason it is a
    second axis. Malformed entries are dropped rather than rejecting the
    payload, so one bad stage does not hide the four good ones.
    """
    if value is None or value == "":
        return default
    decoded = value
    if not isinstance(decoded, (list, dict)):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return default
    if not isinstance(decoded, type(default)):
        return default
    if isinstance(decoded, list):
        return [item for item in decoded if isinstance(item, dict)]
    return decoded


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

    Returns (mismatches, unknown_labels, missing_labels).

    A claim naming an artifact this email does not grade at all is DRIFT and
    is reported, not dropped: the two lists match by construction today
    (web/artifact_checks.py is their one home), and if that ever stops being
    true the cross-check must complain rather than go quiet — going quiet is
    the anti-pattern this whole mechanism exists to kill.

    The opposite drift is the likelier one and gets the same treatment. A
    claims payload with entries MISSING — `{}` because the artifact_checks
    import failed, or short one label whose local query raised — used to
    produce zero mismatches and grade the run fully green, so a cross-check
    that had stopped checking anything read as health. Absence is not
    nothing.

    Only an absent KEY counts as missing. `collect_claims` writes every
    label it queries, with None for an artifact that does not exist locally
    yet, so a healthy run always carries all of them and a None value is a
    real answer rather than a gap — that is why this cannot fire nightly.
    """
    graded = {h["name"]: h for h in heartbeats if h.get("ok") is not None}
    unchecked = {h["name"] for h in heartbeats if h.get("ok") is None}
    claims = claims or {}
    missing = [label for label, _, _ in ARTIFACT_CHECKS if label not in claims]
    out, unknown = [], []
    for label, claimed in claims.items():
        if label in unchecked:
            continue
        if label not in graded:
            unknown.append(label)
            continue
        remote = graded[label].get("last")
        if claimed and remote and str(claimed) > str(remote):
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": str(remote)})
        elif claimed and not remote:
            out.append({"artifact": label, "claimed": str(claimed),
                        "remote": None})
    return out, sorted(unknown), sorted(missing)


def _one_liner(stages, status):
    """The `name: outcome` summary shared by the newest row and every
    `recent_bad` entry — one shape, so a backfilled night reads the same as
    tonight's would have."""
    bad = [s for s in stages if s.get("outcome") in FAILED_OUTCOMES]
    return (", ".join(f"{s.get('name')}: {s['outcome']}" for s in bad)
            or f"run reported {status or 'no status'}")


def _artifact_dates(heartbeats):
    """{heartbeat name: last date} for heartbeats that answered fresh.
    A heartbeat that is stale, never produced, or could not be checked
    vouches for nothing — recovery needs positive evidence."""
    out = {}
    for h in heartbeats or []:
        if h.get("ok") is True and h.get("last"):
            out[h["name"]] = str(h["last"])[:10]
    return out


def _recovered_note(bad, lab_date, artifacts):
    """The stage list as `name: outcome → <artifact> landed <date>`, or None
    when any failed stage lacks a strictly newer artifact. All-or-nothing:
    one unrecovered stage keeps the whole night red."""
    parts = []
    for s in bad:
        name = STAGE_ARTIFACT.get(s.get("name"))
        landed = artifacts.get(name) if name else None
        if not landed or not lab_date or landed <= lab_date:
            return None
        parts.append(f"{s.get('name')}: {s['outcome']} → {name} landed {landed}")
    return ", ".join(parts)


def _build_recent_bad(other_rows, heartbeats=None):
    """Every OTHER row in the window that is not a clean run, newest first,
    split into (still bad, recovered).

    This is the actual fix: a run that fails for lack of network also fails
    to push its own record on time, so it arrives via `push_runs`' catch-up
    days later — older than a run that DID complete that night, and
    therefore never the newest row `_check_nightly_run` grades. Without this,
    that failure is graded never. `other_rows` is already bounded to the
    window and ordered newest-first by NIGHTLY_RUN_SQL.

    A bad night whose failed stages ALL have an artifact heartbeat dated
    after it goes to the recovered list instead (see STAGE_ARTIFACT). A run
    that reported "failed" with no failed stage at all cannot be recovered:
    there is nothing an artifact could vouch for.
    """
    bad_out, recovered = [], []
    artifacts = _artifact_dates(heartbeats)
    for r in other_rows:
        stages = _decode_json_column(r.get("stages"), [])
        status = r.get("status")
        bad = [s for s in stages if s.get("outcome") in FAILED_OUTCOMES]
        if not bad and status == "ok":
            continue
        lab_date = str(r.get("lab_date") or "")[:10]
        # A backfilled row from a host that never stamped one renders straight
        # into the email, so the fallback is here rather than at each of the
        # render sites.
        row = {"lab_date": lab_date, "status": status,
               "host": r.get("host") or "unknown host"}
        note = _recovered_note(bad, lab_date, artifacts) if bad else None
        if note:
            recovered.append({**row, "note": note})
        else:
            bad_out.append({**row, "note": _one_liner(stages, status)})
    return bad_out, recovered


def _apply_recent_bad(entry):
    """Force the entry not-ok when any OTHER run in the window was bad, even
    though the newest row it was just graded on is fine.

    This is what makes a backfilled failure escalate the email: `_problems`
    builds the problem list (and so the subject) from `entry["ok"]` and the
    recent_bad facts, so nothing else needs to know a catch-up row ever
    existed."""
    if entry.get("recent_bad"):
        entry["ok"] = False
        count_note = (f"{len(entry['recent_bad'])} bad night(s) in the last "
                      f"{NIGHTLY_RUN_WINDOW_DAYS} days")
        entry["note"] = f"{entry['note']}; {count_note}" if entry["note"] else count_note
    return entry


def _check_nightly_run(heartbeats=None):
    """The newest nightly pipeline run, graded and cross-checked — plus every
    OTHER bad run in the last NIGHTLY_RUN_WINDOW_DAYS lab days.

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
             "exit_code": None, "note": "", "recent_bad": [], "recovered": []}
    cutoff = (lab_today() - timedelta(days=NIGHTLY_RUN_WINDOW_DAYS)).isoformat()
    try:
        rows = turso_query(NIGHTLY_RUN_SQL, [cutoff])
    except Exception as e:
        entry["note"] = f"could not check ({type(e).__name__})"
        print(f"health_report: nightly run unreadable: {e}"[:200])
        return entry

    if not rows:
        entry["ok"] = False
        entry["note"] = "no rows — never produced"
        return entry

    row = rows[0]
    entry["recent_bad"], entry["recovered"] = _build_recent_bad(rows[1:], heartbeats)
    entry["host"] = row.get("host")
    entry["status"] = row.get("status")
    entry["exit_code"] = row.get("exit_code")
    entry["lab_date"] = str(row.get("lab_date") or "")[:10]
    try:
        last = datetime.strptime(entry["lab_date"], "%Y-%m-%d").date()
    except ValueError:
        entry["ok"] = False
        entry["note"] = f"unparseable lab_date {entry['lab_date']!r}"
        return _apply_recent_bad(entry)

    entry["age_days"] = (lab_today() - last).days
    if entry["age_days"] > NIGHTLY_RUN_MAX_AGE_DAYS:
        entry["ok"] = False
        entry["note"] = (f"no run for {entry['age_days']} days — "
                         "host has been off")
        return _apply_recent_bad(entry)

    entry["stages"] = _decode_json_column(row.get("stages"), [])
    bad = [s for s in entry["stages"] if s.get("outcome") in FAILED_OUTCOMES]
    if entry["status"] == "running":
        entry["ok"] = False
        entry["note"] = "started but never finished — died mid-run"
        return _apply_recent_bad(entry)
    # The run's OWN verdict is graded, not just the stage list it carries.
    # nightly_pipeline.overall_status returns "failed" for an empty results
    # list, so a night that ran no stages at all lands here as
    # status="failed" with stages=[] — and grading on `bad` alone would
    # render that self-declared failure GREEN. A self-report that says
    # "failed" must never read as ok.
    if bad or entry["status"] != "ok":
        entry["ok"] = False
        entry["note"] = _one_liner(entry["stages"], entry["status"])
        return _apply_recent_bad(entry)

    entry["mismatches"], unknown, missing = _claims_vs_remote(
        _decode_json_column(row.get("claims"), {}), heartbeats or [])
    notes = []
    if entry["mismatches"]:
        notes.append("claimed but not in Turso: "
                     + ", ".join(m["artifact"] for m in entry["mismatches"]))
    if unknown:
        notes.append("claim names an artifact this email does not grade: "
                     + ", ".join(unknown))
    if missing:
        notes.append("run recorded no claim for: " + ", ".join(missing))
    if notes:
        entry["ok"] = False
        entry["note"] = "; ".join(notes)
        return _apply_recent_bad(entry)

    entry["ok"] = True
    return _apply_recent_bad(entry)


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


_SEVERITY_ORDER = {"down": 0, "stale": 1, "unchecked": 2}
_BAD_NIGHTS_FRAGMENT = " bad night(s) in the last "
_CLAIM_DRIFT_PREFIXES = ("claim names an artifact", "run recorded no claim for")


def _hosts_differ(nightly_run):
    """True when the newest row and the recent_bad/recovered rows name more
    than one distinct host. Hosts are noise on a one-laptop setup; they only
    earn a place in a line when they disambiguate."""
    nr = nightly_run or {}
    hosts = {nr.get("host")} if nr.get("host") else set()
    for r in (nr.get("recent_bad") or []) + (nr.get("recovered") or []):
        if r.get("host"):
            hosts.add(r["host"])
    return len(hosts) > 1


def _note_fragments(note):
    """The note split on '; ', minus the trailing bad-nights count that
    _apply_recent_bad appends (each bad night is its own line)."""
    return [f for f in (note or "").split("; ")
            if f and _BAD_NIGHTS_FRAGMENT not in f]


def _days_between(iso, today):
    try:
        return (today - datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return None


def _nightly_problems(nr, today):
    out = []

    def add(key, severity, text, short, age=None, since=None, alias=None):
        p = {"key": key, "severity": severity, "text": text,
             "short": short, "age_days": age, "since": since}
        if alias:
            p["alias"] = alias
        out.append(p)

    if nr.get("ok") is None:
        add("run:unchecked", "unchecked",
            f"could not check the nightly run ({nr.get('note')})",
            "nightly run unchecked")
        return out

    lab_date = nr.get("lab_date")
    on = f" on {nr['host']}" if nr.get("host") and _hosts_differ(nr) else ""
    frags = _note_fragments(nr.get("note"))

    # A failure OF the newest row is remembered under the night it belongs
    # to: once a newer run lands, `_build_recent_bad` carries this same row
    # as `night:<lab_date>`, and that must read as already reported. Set only
    # on the branches below that report the row's own failure, all of which
    # have a parseable lab_date; "no run for N days" is about absence and
    # mismatches/claims belong to an ok-status row recent_bad never carries.
    night = f"night:{lab_date}"

    if nr.get("ok") is False:
        age = nr.get("age_days")
        # `_check_nightly_run` leaves lab_date None only when there are no
        # rows at all; a row whose lab_date is NULL or junk arrives as a
        # string with no age, and exists, so it is "unreadable", not "never".
        if lab_date is None:
            note = "; ".join(frags) or "never produced"
            add("run:newest", "stale", f"nightly run: {note}", "nightly run never")
        elif age is None:
            add("run:newest", "stale",
                f"nightly run: {'; '.join(frags) or 'unreadable'}",
                "nightly run unreadable")
        elif age > NIGHTLY_RUN_MAX_AGE_DAYS:
            add("run:newest", "stale",
                f"no nightly run for {age} days (last {lab_date})",
                f"nightly run {age}d", age, lab_date)
        elif nr.get("status") == "running":
            add("run:newest", "stale",
                f"nightly run {lab_date}{on} started but never finished",
                "nightly run died", None, lab_date, night)
        else:
            failed = [s for s in nr.get("stages") or []
                      if s.get("outcome") in FAILED_OUTCOMES]
            for s in failed:
                text = f"nightly {lab_date}{on}: {s.get('name')} {s['outcome']}"
                if s.get("detail"):
                    text += f" — {s['detail']}"
                add(f"stage:{s.get('name')}", "stale", text,
                    f"{s.get('name')} {s['outcome']}", None, lab_date, night)
            if not failed and nr.get("status") != "ok":
                status = nr.get("status") or "no status"
                add("run:newest", "stale",
                    f"nightly {lab_date}{on}: run reported {status}",
                    f"nightly run {status}", None, lab_date, night)
            for m in nr.get("mismatches") or []:
                remote = m.get("remote")
                add(f"publish:{m['artifact']}", "stale",
                    f"{m['artifact']}: the run made {m['claimed']}, Turso has "
                    f"{remote or 'nothing'} — publish is dropping rows",
                    f"{m['artifact']} not published",
                    _days_between(remote, today) if remote else None,
                    remote or None)
            # One key, one problem: both drift fragments share `run:claims`,
            # and a duplicate key would collapse in the remembered state.
            drift = [f for f in frags if f.startswith(_CLAIM_DRIFT_PREFIXES)]
            if drift:
                add("run:claims", "stale", "; ".join(drift), "run claims drift")

    for r in nr.get("recent_bad") or []:
        d = r.get("lab_date")
        r_on = f" on {r['host']}" if r.get("host") and _hosts_differ(nr) else ""
        # The night itself is Day 1, so `age` here is days-since + 1: the
        # same N a stage line counting from first sighting reads when the
        # failure was first reported on its own night (see _mark_new).
        since_night = _days_between(d, today)
        add(f"night:{d}", "stale", f"nightly {d}{r_on} failed: {r.get('note')}",
            f"bad night {str(d)[5:10]}",
            since_night + 1 if since_night is not None else None, d)
    return out


def _problems(results, heartbeats, nightly_run, uptime_rows):
    """Everything the email should lead with, as a flat list of problems.
    Pure: grading was done by the _check_* functions; this only restates it."""
    today = lab_today()
    out = []
    for r in results or []:
        if not r.get("ok"):
            text = f"{r['name']} is down ({r.get('status') or 'unreachable'})"
            if r.get("note"):
                text += f" — {r['note']}"
            out.append({"key": f"target:{r['name']}", "severity": "down",
                        "text": text, "short": f"{r['name']} down",
                        "age_days": None, "since": None})
    for h in heartbeats or []:
        name, key = h.get("name"), f"heartbeat:{h.get('name')}"
        if h.get("ok") is None:
            out.append({"key": key, "severity": "unchecked",
                        "text": f"could not check {name} ({h.get('note')})",
                        "short": f"{name} unchecked", "age_days": None,
                        "since": None})
        elif h.get("ok") is False and h.get("last"):
            age = h.get("age_days")
            out.append({"key": key, "severity": "stale",
                        "text": f"{name} has not landed for {age} days "
                                f"(last {h['last']})",
                        "short": f"{name} {age}d", "age_days": age,
                        "since": h["last"]})
        elif h.get("ok") is False:
            out.append({"key": key, "severity": "stale",
                        "text": f"{name}: {h.get('note')}",
                        "short": f"{name} never", "age_days": None,
                        "since": None})
    if nightly_run:
        out.extend(_nightly_problems(nightly_run, today))
    if uptime_rows == 0:
        out.append({"key": "archive:zero", "severity": "stale",
                    "text": "uptime archive wrote 0 rows today",
                    "short": "uptime archive empty", "age_days": None,
                    "since": None})
    today_iso = today.isoformat()
    # stable sorts, least significant first: key, then since (newest first),
    # then severity
    out.sort(key=lambda p: p["key"])
    out.sort(key=lambda p: p["since"] or today_iso, reverse=True)
    out.sort(key=lambda p: _SEVERITY_ORDER[p["severity"]])
    return out


def _mark_new(problems, prior, today):
    """Stamp each problem with first_seen/is_new/day against the remembered
    state. Returns (problems, new_state); new_state holds current problems
    only, so a cleared problem that returns counts as new again. A second
    send on the same day still says NEW, deliberately.

    Identity: a problem is remembered under its key, except one carrying an
    `alias` (a failure of the newest run row: `night:<lab_date>`), which is
    remembered under the alias and takes first_seen from it alone. Tomorrow
    that row is an older bad night keyed `night:<lab_date>` and must not read
    NEW twice; and `stage:review` failing again on a NEW night is a new
    failure, so the stable `stage:` key must not vouch for it. new_state
    records both the key and the alias; problems sharing an alias keep the
    earliest date.

    Day N (one rule): the Nth lab day the problem has existed, its first day
    being Day 1. A problem that dates itself carries that N in `age_days` (a
    stale artifact: days since it last landed; a bad night: days since the
    night + 1); every other problem counts from first_seen, so first reported
    today is Day 1 (shown as NEW). For a failure reported on its own night
    the two give the same N on every later day."""
    marked, new_state = [], {}
    today_iso = today.isoformat()

    def remember(key, first):
        if key not in new_state or first < new_state[key]:
            new_state[key] = first

    for p in problems:
        q = dict(p)
        alias = p.get("alias")
        if prior is None:
            q["first_seen"], q["is_new"], q["day"] = None, False, p.get("age_days")
        else:
            first = prior.get(alias or p["key"]) or today_iso
            q["first_seen"] = first
            q["is_new"] = first == today_iso
            if p.get("age_days") is not None:
                q["day"] = p["age_days"]
            else:
                q["day"] = _days_between(first, today)
                q["day"] = q["day"] + 1 if q["day"] is not None else None
        remember(p["key"], q["first_seen"] or today_iso)
        if alias:
            remember(alias, q["first_seen"] or today_iso)
        marked.append(q)
    return marked, new_state


def _prefix(p):
    if p.get("is_new"):
        return "NEW today"
    if p.get("day") is not None:
        return f"Day {p['day']}"
    return "Ongoing"


def _get_problem_state():
    """{key: first_seen_iso} as last stored; {} when nothing is stored yet
    (first email ever: everything is NEW); None when the read failed."""
    try:
        rows = turso_query(
            "SELECT value FROM health_email_state WHERE key = 'reported_problems'"
        )
        if not rows:
            return {}
        state = json.loads(rows[0]["value"])
        if not isinstance(state, dict):
            raise ValueError("stored problem state is not an object")
        return state
    except Exception as e:
        print(f"health_report: problem state read failed: {e}"[:200])
        return None


def _set_problem_state(state):
    """Remember today's problems. Never raises: the email must send."""
    try:
        turso_query(
            "INSERT INTO health_email_state (key, value, updated_at) "
            "VALUES ('reported_problems', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            [json.dumps(state, sort_keys=True), _utc()],
        )
    except Exception as e:
        print(f"health_report: problem state write failed: {e}"[:200])


# Colours. Red is for what is broken and amber for what could not be checked,
# and both are used ONLY above the separator: a red line under a "working"
# heading is the same lie as a red line under a green subject.
_RED = "#c62828"
_AMBER = "#b26a00"
_GREEN = "#2e7d32"
_MUTED = "#666"

# Problem keys that describe the NEWEST run row (Task 1's key scheme). When
# none of them is present the newest row was a good run, even if an older
# bad night has forced `nightly_run["ok"]` False.
_NEWEST_ROW_KEYS = ("run:", "stage:", "publish:")

STATE_READ_FAILED_LINE = (
    "could not read yesterday's problems, so nothing is marked new")


def _subject(problems, results):
    """The subject is the attention block in one line: a count, how many are
    new, and the first three by name. Green only when there is nothing."""
    up = sum(1 for r in results if r["ok"])
    if not problems:
        return f"✅ nothing needs attention · {up}/{len(results)} up"
    emoji = "🔴" if any(p["severity"] == "down" for p in problems) else "🟡"
    n = len(problems)
    new = sum(1 for p in problems if p.get("is_new"))
    subject = f"{emoji} {n} problem{'' if n == 1 else 's'}"
    if new:
        subject += f" ({new} new)"
    subject += ": " + ", ".join(p["short"] for p in problems[:3])
    if n > 3:
        subject += f" +{n - 3} more"
    return subject


def _newest_run_clean(nr, problems):
    """True when the newest run row itself was good, so its one green line
    belongs below the separator. A clean newest row beside an older bad night
    still counts: the bad night is its own problem above."""
    if nr.get("ok") is True:
        return True
    if nr.get("ok") is None or not nr.get("lab_date"):
        return False
    return not any(p["key"].startswith(_NEWEST_ROW_KEYS) for p in problems)


def _working_lines(heartbeats, nightly_run, uptime_rows, problems):
    """(text, colour) lines for below the separator: green and grey only.
    Every failure these could name is already a problem line above."""
    out = []
    if heartbeats:
        fresh = sum(1 for h in heartbeats if h.get("ok") is True)
        if fresh == len(heartbeats):
            out.append((f"heartbeats: all {len(heartbeats)} artifacts fresh",
                        _GREEN))
        else:
            out.append((f"heartbeats: {fresh}/{len(heartbeats)} fresh", _MUTED))
    nr = nightly_run or {}
    show_host = _hosts_differ(nr)
    if nr and _newest_run_clean(nr, problems):
        on = f" on {nr['host']}" if show_host and nr.get("host") else ""
        out.append((f"nightly run {nr['lab_date']}{on}: ok, "
                    f"{len(nr.get('stages') or [])} stages", _GREEN))
    # Recovered nights never escalate, but they still appear: a failure that
    # silently vanished would be "absence recorded as nothing" again.
    for rc in nr.get("recovered") or []:
        on = f" on {rc['host']}" if show_host and rc.get("host") else ""
        out.append((f"recovered {rc['lab_date']}{on}: {rc['note']}", _MUTED))
    # A zero count is a problem above; only a real count lands here.
    if uptime_rows:
        out.append((f"{uptime_rows} monitors archived", _MUTED))
    return out


def _compose(results, joke, pause_url, heartbeats=None, uptime_rows=None,
             nightly_run=None, problems=None, state_read_failed=False):
    """Return (subject, text, html).

    `problems` is the list `_mark_new` returns. When None it is computed here
    and marked with no memory (nothing NEW), so a caller without state still
    gets the same layout. `state_read_failed` adds the muted line saying the
    NEW markers are missing for a reason, not because nothing is new.
    """
    heartbeats = heartbeats or []
    if problems is None:
        problems, _ = _mark_new(
            _problems(results, heartbeats, nightly_run, uptime_rows),
            None, lab_today())
    subject = _subject(problems, results)
    working = _working_lines(heartbeats, nightly_run, uptime_rows, problems)
    if state_read_failed:
        working.append((STATE_READ_FAILED_LINE, _MUTED))

    lines = ["What needs attention"]
    lines.extend([f"{_prefix(p)}: {p['text']}" for p in problems]
                 or ["nothing needs attention"])
    lines += ["", "--- working ---"]
    for r in results:
        mark = "up" if r["ok"] else "DOWN"
        status = r["status"] if r["status"] is not None else "—"
        note = f" — {r['note']}" if r["note"] else ""
        lines.append(f"{r['name']}: {mark} ({status}, {r['ms']}ms){note}")
    if working:
        lines.append("")
        lines.extend(t for t, _ in working)

    text = "\n".join(lines) + (
        "\n\n--\n"
        f"Pause these emails for a week: {pause_url}\n\n"
        f"To tune this email, tell the prompt-lab agent:\n\"{TUNE_PROMPT}\"\n\n"
        f"{joke}\n"
    )

    def problem_html(p):
        colour = _AMBER if p["severity"] == "unchecked" else _RED
        line = escape(f"{_prefix(p)}: {p['text']}")
        if p.get("is_new"):
            line = f"<b>{line}</b>"
        return f"<div style='color:{colour};padding:2px 0'>{line}</div>"

    attention = ("".join(problem_html(p) for p in problems)
                 or f"<div style='color:{_MUTED}'>nothing needs attention</div>")
    # The DOWN cell is bold, not red: the down target is already a red line
    # above, and the table is the full roster, not the alarm.
    rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'><b>{escape(r['name'])}</b></td>"
        "<td style='padding:4px 12px 4px 0'>"
        + (f"<span style='color:{_GREEN}'>up</span>" if r["ok"] else "<b>DOWN</b>")
        + "</td>"
        f"<td style='padding:4px 12px 4px 0'>{r['status'] if r['status'] is not None else '—'}"
        f" · {r['ms']}ms</td>"
        f"<td style='padding:4px 0'>{escape(r['note'] or '')}</td></tr>"
        for r in results
    )
    working_html = "".join(
        f"<p style='color:{colour};margin:4px 0'>{escape(t)}</p>"
        for t, colour in working)
    heading = "margin:0 0 8px;font-size:16px"

    html = (
        "<div style='font-family:-apple-system,sans-serif;font-size:15px;color:#222'>"
        f"<h3 style='{heading}'>What needs attention</h3>"
        f"{attention}"
        "<hr style='border:none;border-top:1px solid #ddd;margin:16px 0'>"
        f"<h3 style='{heading};color:{_MUTED}'>Working</h3>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        f"{working_html}"
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

            # The problem memory is read only here, past both the dry return
            # and the pause check: a dry run is a reader's view and a paused
            # run sends nothing, so neither may move what "NEW" means. A
            # failed read (None) still sends, with no NEW markers.
            prior = _get_problem_state()
            problems, new_state = _mark_new(
                _problems(results, heartbeats, nightly_run, uptime_rows),
                prior, lab_today())

            pause_url = ("https://prompt-labs.org/api/health_report"
                         f"?action=pause&token={_make_pause_token()}")
            subject, text, html = _compose(results, _joke(), pause_url,
                                           heartbeats, uptime_rows,
                                           nightly_run, problems,
                                           state_read_failed=prior is None)
            _send_email(subject, html, text)
            # Only after the send returns: a problem remembered but never
            # delivered would read as Day 2 tomorrow when it was never NEW.
            # Skipped when the read failed: new_state then dates every
            # problem today, and writing it would wipe each real first_seen
            # the moment Turso answered again.
            if prior is not None:
                _set_problem_state(new_state)
            # Summarised here (tri-state ok) rather than returned whole, the
            # way `stale` reduces the heartbeats: the send path's JSON is a
            # problem summary. ?dry=1 above carries the full block for
            # #/health.
            self._json({"sent": True,
                        "down": [r["name"] for r in results if not r["ok"]],
                        "stale": [h["name"] for h in heartbeats if h["ok"] is False],
                        "nightly_run": nightly_run["ok"],
                        "uptime_rows": uptime_rows,
                        "problems": [p["key"] for p in problems]})
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
