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
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claude_api import load_env  # noqa: E402

API = "https://api.uptimerobot.com/v3"
HOUR = 3600
DAY = 24 * HOUR

# --- Desired HTTP monitors -------------------------------------------------
# url is the source of truth; a monitor found under the same friendlyName with
# a different url gets updated. Prefer a deep health URL over a homepage.
HTTP_MONITORS = [
    ("garm.prompt-labs.org/api/health?db=1",
     "https://garm.prompt-labs.org/api/health?db=1"),
    ("prompt-labs", "https://prompt-labs.org/api/health?db=1"),
    # ibuild4you implements the convention with per-dependency detail; its
    # monitor pointed at the homepage until 2026-07-31.
    ("ibuild4you", "https://ibuild4you.com/api/health"),
    # Deep URLs, not the bare path: the shallow variant answers 200 while the
    # database behind it is down, which is the state the homepage check already
    # passed on. Adopted 2026-07-31 (byside PR #125, selected-projects PR #24).
    ("byside", "https://by-side.net/api/health?db=1"),
    # www, not the apex: the apex 307s to www (domain canonical), and a monitor
    # that depends on redirect-following is one setting away from a false DOWN.
    ("pianohouse", "https://www.pianohouseproject.org/api/health?db=1"),
    # No /api/health yet — homepage checks until each app adopts the convention.
    ("bakerylouise", "https://bakerylouise.com/"),
    ("musicforge", "https://musicforge.app/"),
    # recountly's /api/health exists but is auth-gated (401), so pointing at it
    # would false-DOWN forever — the #40 failure exactly. Homepage until it is
    # moved outside auth.
    ("recountly", "https://recountly.org/"),
    # Was entirely unmonitored until 2026-07-31. Note .org, not .com.
    ("prntd", "https://prntd.org/"),
]

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


def _call(path, method="GET", body=None):
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
        raise ApiError(e.code, f"{method} {path} failed: {e.code} {detail}") from None


def fetch_monitors():
    d = _call("/monitors")
    return d.get("data", d if isinstance(d, list) else [])


def cmd_list(_args):
    mons = fetch_monitors()
    print(f"{len(mons)} monitors\n")
    for m in sorted(mons, key=lambda x: (x.get("type", ""), x.get("friendlyName", ""))):
        name = m.get("friendlyName")
        print(f"  [{m.get('type'):9}] {name}")
        print(f"     status={m.get('status')} interval={m.get('interval')}s "
              f"grace={m.get('gracePeriod')}")
        if m.get("url"):
            print(f"     url={m['url']}")
    return 0


def cmd_sync(args):
    mons = fetch_monitors()
    by_name = {m.get("friendlyName"): m for m in mons}
    creates, updates = [], []

    for name, url in HTTP_MONITORS:
        cur = by_name.get(name)
        if cur is None:
            creates.append(("HTTP", name, {"type": "HTTP", "friendlyName": name,
                                           "url": url, "interval": 300, "timeout": 30}))
        elif cur.get("url") != url:
            updates.append((cur["id"], name, cur.get("url"), url, {"url": url}))

    for job, name, interval, grace in HEARTBEATS:
        if name not in by_name:
            creates.append(("HEARTBEAT", name, {
                "type": "HEARTBEAT", "friendlyName": name,
                "interval": interval, "gracePeriod": grace, "_job": job}))

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
