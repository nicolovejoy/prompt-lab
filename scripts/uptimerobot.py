#!/usr/bin/env python3
"""Reconcile UptimeRobot monitors with the state this repo declares (issue #45).

    .venv/bin/python scripts/uptimerobot.py list
    .venv/bin/python scripts/uptimerobot.py sync            # dry run (default)
    .venv/bin/python scripts/uptimerobot.py sync --apply

UptimeRobot is the ecosystem's sensor layer: it polls on independent infra at
5-minute resolution and keeps 3 months, which is why prompt-lab does not sample
anything itself (docs/health-convention.md). This script owns the *declaration*
of what should be watched, so the monitor set is reviewable in git rather than
existing only as clicks in someone's phone.

Two kinds of monitor:

- HTTP — "is this URL answering." Point these at `/api/health` wherever an app
  implements the convention; a homepage check passes while the backend is dead.
- HEARTBEAT — "did this recurring job run." UptimeRobot hands back a ping URL;
  the job curls it on success (heartbeat.py) and UptimeRobot alarms when the
  pings stop. The check must live outside the job — that is the entire point of
  #45, since a job that dies never reaches its own error handling.

Dry run is the default and prints the exact diff. Nothing is created, updated,
or deleted without --apply. Deletion is not implemented at all: an unrecognised
monitor is reported, never removed, because this file is not the only thing
allowed to add monitors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_api import load_env  # noqa: E402

API = "https://api.uptimerobot.com/v3"
HOUR = 3600
DAY = 24 * HOUR
MIN_CALL_INTERVAL = 6.5  # free tier: 10 req/min, and it 429s rather than queues
RATE_LIMIT_BACKOFF = 65  # a full window, since the limit is per rolling minute

# --- Desired HTTP monitors -------------------------------------------------
# url is the source of truth; a monitor found under the same friendlyName with
# a different url gets updated. Prefer a deep health URL over a homepage.
HTTP_MONITORS = [
    # Shallow since 2026-08-18, same failure as byside (f0391c3): garm's
    # database is Neon on the free tier, autosuspend after 5 minutes idle —
    # the same interval this monitor polls at, so the deep check never let it
    # sleep. Flagged by prompt-lab on the garm handoff channel: Neon reported
    # garm's project at 100% of its 100 CU-hour monthly quota with 12+ days
    # left before reset, confirmed via `neonctl` (~101.6 CU-hours from
    # active_time alone). Consumers fail closed on a garm outage, so a
    # Neon-enforced suspension here risks an ecosystem-wide lockout, not just
    # a bill — friendlyName kept as-is (it's the URL) to match by existing
    # monitor rather than create a duplicate.
    ("garm.prompt-labs.org/api/health?db=1",
     "https://garm.prompt-labs.org/api/health"),
    ("prompt-labs", "https://prompt-labs.org/api/health?db=1"),
    # ibuild4you implements the convention with per-dependency detail; its
    # monitor pointed at the homepage until 2026-07-31.
    ("ibuild4you", "https://ibuild4you.com/api/health"),
    # Deep URLs, not the bare path: the shallow variant answers 200 while the
    # database behind it is down, which is the state the homepage check already
    # passed on. Adopted 2026-07-31 (byside PR #125, selected-projects PR #24).
    #
    # byside is the exception, shallow since 2026-08-14. Its database is Neon on
    # the free tier, which autosuspends after 5 minutes idle — the same interval
    # we poll at. So the deep check was measuring a condition it created: it
    # proved a permanently-warm database answers, which was guaranteed, while
    # saying nothing about the cold start a real first visitor actually hits.
    # It also consumed 80 of byside's 100 monthly CU-hours by mid-August purely
    # by never letting the compute sleep. A check that keeps a database awake to
    # prove it is awake is not coverage, it is a bill.
    # Deep coverage here needs a longer interval than the suspend window, not a
    # deeper URL — revisit if byside ever moves off the free tier.
    ("byside", "https://by-side.net/api/health"),
    # www, not the apex: the apex 307s to www (domain canonical), and a monitor
    # that depends on redirect-following is one setting away from a false DOWN.
    ("pianohouse", "https://www.pianohouseproject.org/api/health?db=1"),
    # Shallow on purpose: pages are ISR-cached, so a Sanity blip isn't a site
    # outage and a deep variant would false-alarm (their 2026-08-02 handoff).
    ("bakerylouise", "https://bakerylouise.com/api/health"),
    # www.musicforge.org, not musicforge.app: the health rewrite to the Fly
    # backend only exists on the .org deployment (.app 404s on the path).
    ("musicforge", "https://www.musicforge.org/api/health?db=1"),
    # recountly was dropped 2026-08-02: it became Raconte, a native iOS app, so
    # there is nothing left to poll and the monitor would have false-alarmed the
    # day the deployment came down. This script never deletes — the monitor
    # itself must be removed by hand in the UptimeRobot UI.
    # Was entirely unmonitored until 2026-07-31. Note .org, not .com.
    ("prntd", "https://prntd.org/api/health?db=1"),
    # Deep since 2026-08-13 (was homepage for a few hours): checks[] with two
    # artifact checks — Influx last-point age for the ~30s collector loop, and
    # restic last-snapshot age (the snapshot's own timestamp, so it asserts the
    # artifact exists, not that the job exited 0). Real 503 on failure, and
    # unknown /api/* paths 404 — no SPA catch-all false-UP risk (verified).
    # Data endpoints are unauthenticated by Nico's explicit choice
    # (2026-08-13): public but unadvertised beats logging in to read his own
    # power meter.
    ("span", "https://span.pianohouseproject.org/api/health"),
]

# --- Desired alert contacts -------------------------------------------------
# Declared by email value, not id: the id is account state, the address is the
# intent. Resolved against /alert-contacts at run time, and a declared address
# the account doesn't have is a hard error rather than a silent no-op.
#
# Why this exists: until 2026-08-09 this file declared *what* to watch and said
# nothing about *who to tell*, so every monitor it created had an empty
# assignedAlertContacts and notified nobody. Only garm — hand-made in the UI —
# had a contact. musicforge's Fly backend went down for 10.6 minutes that
# evening; the monitor detected it exactly as designed, resolved it, and no
# alert was ever sent. That is this repo's recurring failure shape wearing a new
# hat: the sensor worked, the output went nowhere, and the silence read as
# health. Assignment is a union, never a replacement — a contact added by hand
# is left alone.
ALERT_CONTACTS = ["nlovejoy@me.com"]
ALERT_THRESHOLD = 0    # notify immediately; the 5-min interval is the delay
ALERT_RECURRENCE = 0   # no repeat nagging while it stays down

# --- Desired heartbeat monitors --------------------------------------------
# (job, friendlyName, interval, grace). Max age = interval + grace, and must
# exceed the job's real period or it alarms on a healthy run. `job` is the key
# heartbeat.py resolves to HEARTBEAT_URL_<JOB>.
HEARTBEATS = [
    ("synthesizer", "job: synthesizer (nightly 2:00am)", DAY, 2 * HOUR),
    ("review", "job: review email (nightly 2:30am)", DAY, 2 * HOUR),
    ("cost-pull", "job: cost pull + Turso sync (nightly 2:30am)", DAY, 2 * HOUR),
    # 1st & 15th, so the real gap runs to ~16 days.
    ("report", "job: bi-monthly report (1st & 15th, 3:00am)", 15 * DAY, 5 * DAY),
]


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _key():
    load_env()
    k = os.environ.get("UPTIMEROBOT_API_KEY")
    if not k:
        sys.exit("UPTIMEROBOT_API_KEY not set (see .env.tpl)")
    return k


def _throttle():
    """Free tier allows 10 requests/minute and answers 429 past it.

    An --apply that touches every monitor blows through this in about four
    seconds: the 2026-08-09 alert-contact backfill patched 2 of 7 monitors and
    429'd on the rest, which reads as a partial failure but is really just
    pacing. Sleep is applied *before* each call except the first.
    """
    now = time.monotonic()
    wait = _throttle.last + MIN_CALL_INTERVAL - now if _throttle.last else 0
    if wait > 0:
        time.sleep(wait)
    _throttle.last = time.monotonic()


_throttle.last = 0.0


def _call(path, method="GET", body=None, _retries=0):
    _throttle()
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {_call.key}",
            "Content-Type": "application/json",
            "User-Agent": "prompt-lab/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read(1000).decode(errors="replace")
        # 429 is pacing, not a real failure — the per-minute window just has to
        # drain. Back off once and retry rather than reporting a change failed
        # and leaving the run half-applied.
        if e.code == 429 and _retries < 2:
            print(f"  (429 — waiting {RATE_LIMIT_BACKOFF}s for the rate window)")
            time.sleep(RATE_LIMIT_BACKOFF)
            return _call(path, method, body, _retries + 1)
        raise ApiError(e.code, f"{method} {path} failed: {e.code} {detail}") from None


def fetch_monitors():
    d = _call("/monitors")
    return d.get("data", d if isinstance(d, list) else [])


def fetch_alert_contacts():
    d = _call("/alert-contacts")
    return d.get("data", d if isinstance(d, list) else [])


def resolve_alert_contacts(contacts):
    """Declared emails -> ids. Missing address is fatal, not a silent skip."""
    by_value = {c.get("value"): c for c in contacts}
    ids, missing = [], []
    for value in ALERT_CONTACTS:
        c = by_value.get(value)
        if c is None:
            missing.append(value)
        else:
            ids.append(int(c["id"]))
    if missing:
        sys.exit(f"declared alert contact(s) not on the account: {', '.join(missing)}\n"
                 f"available: {', '.join(sorted(by_value)) or '(none)'}")
    return ids


def _assigned_ids(mon):
    return {int(a["alertContactId"]) for a in (mon.get("assignedAlertContacts") or [])}


def cmd_list(_args):
    mons = fetch_monitors()
    contacts = {int(c["id"]): c.get("value") for c in fetch_alert_contacts()}
    print(f"{len(mons)} monitors\n")
    for m in sorted(mons, key=lambda x: (x.get("type", ""), x.get("friendlyName", ""))):
        name = m.get("friendlyName")
        print(f"  [{m.get('type'):9}] {name}")
        print(f"     status={m.get('status')} interval={m.get('interval')}s "
              f"grace={m.get('gracePeriod')}")
        if m.get("url"):
            print(f"     url={m['url']}")
        # Printed even when empty, and loudly: a monitor that notifies nobody
        # looks identical to a healthy one in every other line of this output.
        assigned = sorted(contacts.get(i, str(i)) for i in _assigned_ids(m))
        print(f"     alerts={', '.join(assigned) if assigned else '** NOBODY **'}")
    return 0


def cmd_sync(args):
    mons = fetch_monitors()
    by_name = {m.get("friendlyName"): m for m in mons}
    all_contacts = fetch_alert_contacts()
    want_contacts = resolve_alert_contacts(all_contacts)
    assign = [{"alertContactId": i, "threshold": ALERT_THRESHOLD,
               "recurrence": ALERT_RECURRENCE} for i in want_contacts]
    creates, updates = [], []

    by_id = {int(c["id"]): c.get("value") for c in all_contacts}

    def _contact_patch(cur):
        """Union of what's assigned and what's declared, or None if satisfied."""
        have = _assigned_ids(cur)
        if set(want_contacts) <= have:
            return None
        keep = [a for a in (cur.get("assignedAlertContacts") or [])
                if int(a["alertContactId"]) not in set(want_contacts)]
        was = sorted(by_id.get(i, str(i)) for i in have)
        return (f"alerts: {', '.join(was) if was else 'NOBODY'}",
                {"assignedAlertContacts": keep + assign})

    for name, url in HTTP_MONITORS:
        cur = by_name.get(name)
        if cur is None:
            creates.append(("HTTP", name, {"type": "HTTP", "friendlyName": name,
                                           "url": url, "interval": 300, "timeout": 30,
                                           "assignedAlertContacts": assign}))
            continue
        if cur.get("url") != url:
            updates.append((cur["id"], name, cur.get("url"), url, {"url": url}))
        patch = _contact_patch(cur)
        if patch is not None:
            was, body = patch
            updates.append((cur["id"], name, was,
                            f"alerts: {', '.join(ALERT_CONTACTS)}", body))

    for job, name, interval, grace in HEARTBEATS:
        cur = by_name.get(name)
        if cur is None:
            creates.append(("HEARTBEAT", name, {
                "type": "HEARTBEAT", "friendlyName": name,
                "interval": interval, "gracePeriod": grace,
                "assignedAlertContacts": assign, "_job": job}))
            continue
        patch = _contact_patch(cur)
        if patch is not None:
            was, body = patch
            updates.append((cur["id"], name, was,
                            f"alerts: {', '.join(ALERT_CONTACTS)}", body))

    declared = {n for n, _ in HTTP_MONITORS} | {n for _, n, _, _ in HEARTBEATS}
    unknown = [m.get("friendlyName") for m in mons if m.get("friendlyName") not in declared]

    if not creates and not updates:
        print("in sync — nothing to create or update")
    for kind, name, body in creates:
        extra = (f"interval={body['interval']}s grace={body['gracePeriod']}s"
                 if kind == "HEARTBEAT" else body.get("url"))
        print(f"CREATE {kind:9} {name}\n       {extra}")
    for _id, name, old, new, _ in updates:
        print(f"UPDATE {'HTTP':9} {name}\n       {old}\n    -> {new}")
    if unknown:
        print(f"\nnot declared here (left alone): {', '.join(sorted(unknown))}")

    if not args.apply:
        print("\n(dry run — re-run with --apply to make these changes)")
        return 0

    ping_urls, failed = {}, []
    # One failure must not strand the rest half-applied — the first --apply run
    # created prntd, then died on the heartbeat plan restriction and never
    # reached the ibuild4you update.
    for kind, name, body in creates:
        job = body.pop("_job", None)
        try:
            res = _call("/monitors", "POST", body)
        except ApiError as e:
            hint = ""
            if e.status == 403 and kind == "HEARTBEAT":
                hint = "  (HEARTBEAT is not available on the free plan)"
            print(f"FAILED  {kind} {name}: {e}{hint}")
            failed.append(name)
            continue
        mon = res.get("data", res)
        print(f"created {kind} {name} (id={mon.get('id')})")
        if job:
            ping_urls[job] = mon.get("url") or mon.get("heartbeatUrl") or ""
    for mid, name, _old, new, patch in updates:
        try:
            _call(f"/monitors/{mid}", "PATCH", patch)
        except ApiError as e:
            print(f"FAILED  update {name}: {e}")
            failed.append(name)
            continue
        print(f"updated {name} -> {new}")

    if ping_urls:
        print("\nHeartbeat ping URLs — store these in 1Password as item")
        print("'Prompt Lab Heartbeats' (vault dev-secrets), one field per job,")
        print("then declare HEARTBEAT_URL_<JOB> in .env.tpl:\n")
        for job, url in ping_urls.items():
            print(f"  {job:12} {url}")
    if failed:
        print(f"\n{len(failed)} change(s) failed: {', '.join(failed)}")
        return 1
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show current monitors")
    s = sub.add_parser("sync", help="reconcile monitors with this file")
    s.add_argument("--apply", action="store_true",
                   help="actually create/update (default is a dry run)")
    args = p.parse_args()
    _call.key = _key()
    return cmd_list(args) if args.cmd == "list" else cmd_sync(args)


if __name__ == "__main__":
    sys.exit(main())
