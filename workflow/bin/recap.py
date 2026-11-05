#!/usr/bin/env python3
"""recap [DAYS] [PROJECT] — every repo touched lately, and what to do next.

Default (14 days): one numbered line per repo with a session in the history
DB or a commit in ~/src/<repo> inside the window, newest touch first:

     1  prompt-lab   11-05  14c  <newest session's "Next:" line>

The numbers are saved so `work 1 3 4` opens those repos. A repo with
commits but no summarised session shows its newest commit subject instead.
With PROJECT: that project's newest 3 summarised sessions.

Reads the DB read-only. Env overrides (tests): PROMPT_HISTORY_DB,
RECAP_SRC (default ~/src), RECAP_STATE (default ~/.claude/state/recap-last.txt).
"""
import os
import re
import shutil
import pathlib
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_DAYS = 14
PROJECT_SESSIONS = 3
PACIFIC = ZoneInfo("America/Los_Angeles")
TS = "%Y-%m-%d %H:%M:%S"
WHEN = "COALESCE(NULLIF(ended_at, ''), started_at)"


def line_text(summary):
    s = " ".join(summary.split())
    if "Next:" in s:
        nxt = s.split("Next:", 1)[1].strip()
        if nxt:
            return nxt
    m = re.search(r"[.!?](\s|$)", s)
    return s[: m.start() + 1] if m else s


def pacific_day(dt):
    return dt.astimezone(PACIFIC).strftime("%m-%d")


def parse_ts(ts):
    return datetime.strptime(ts[:19], TS).replace(tzinfo=timezone.utc)


def git_activity(repo, since):
    """(commit count, newest commit time, newest subject) on any branch since `since`."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--branches", "--remotes", "--no-merges",
             f"--since={since.isoformat()}", "--format=%ct %s"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0, None, None
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        return 0, None, None
    newest = max(lines, key=lambda ln: int(ln.split(" ", 1)[0]))
    stamp, _, subject = newest.partition(" ")
    return len(lines), datetime.fromtimestamp(int(stamp), timezone.utc), subject


def fit(prefix, text, width):
    room = max(width - len(prefix), 1)
    if len(text) > room:
        text = text[: room - 1].rstrip() + "…"
    return prefix + text


def main(argv):
    days, project = DEFAULT_DAYS, None
    for a in argv:
        if a.isdigit():
            days = int(a)
        else:
            project = a
    db = os.environ.get("PROMPT_HISTORY_DB") or os.path.expanduser("~/.claude/prompt-history.db")
    src = pathlib.Path(os.environ.get("RECAP_SRC") or os.path.expanduser("~/src"))
    state = pathlib.Path(os.environ.get("RECAP_STATE") or os.path.expanduser("~/.claude/state/recap-last.txt"))
    if not os.path.exists(db):
        print(f"recap: no history DB at {db}", file=sys.stderr)
        return 1
    since = datetime.now(timezone.utc) - timedelta(days=days)
    con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True)
    try:
        rows = con.execute(
            f"SELECT project, {WHEN} AS t, summary FROM sessions "
            f"WHERE project != 'scratch' AND {WHEN} >= ? ORDER BY t DESC",
            (since.strftime(TS),),
        ).fetchall()
    except sqlite3.Error as e:
        print(f"recap: cannot read history DB: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()
    width = shutil.get_terminal_size((100, 20)).columns

    if project:
        picked = [r for r in rows if r[0] == project and (r[2] or "").strip()][:PROJECT_SESSIONS]
        if not picked:
            print(f"no summarised sessions in the last {days} days")
            return 0
        for proj, t, summary in picked:
            print(fit(f"{proj}  {pacific_day(parse_ts(t))}  ", line_text(summary), width))
        return 0

    # repo -> {touch, next, commits}
    repos = {}
    for proj, t, summary in rows:
        r = repos.setdefault(proj, {"touch": parse_ts(t), "next": None, "commits": 0})
        if r["next"] is None and (summary or "").strip():
            r["next"] = line_text(summary)
    names = set(repos)
    if src.is_dir():
        names |= {p.name for p in src.iterdir() if not p.name.startswith(".") and (p / ".git").exists()}
    for name in names:
        count, newest, subject = git_activity(src / name, since) if (src / name / ".git").exists() else (0, None, None)
        if not count and name not in repos:
            continue
        r = repos.setdefault(name, {"touch": newest, "next": None, "commits": 0})
        r["commits"] = count
        if newest and newest > r["touch"]:
            r["touch"] = newest
        if r["next"] is None:
            r["next"] = f"(no summary) last commit: {subject}" if subject else "(no summary)"

    if not repos:
        print(f"nothing touched in the last {days} days")
        return 0
    order = sorted(repos, key=lambda n: (repos[n]["touch"], n), reverse=True)
    pad = max(len(n) for n in order)
    num = len(str(len(order)))
    cpad = max(len(f"{repos[n]['commits']}c") for n in order)
    for i, name in enumerate(order, 1):
        r = repos[name]
        prefix = f"{i:>{num}}  {name:<{pad}}  {pacific_day(r['touch'])}  {str(r['commits']) + 'c':>{cpad}}  "
        print(fit(prefix, r["next"], width))
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("\n".join(order) + "\n")
    except OSError as e:
        print(f"recap: could not save numbers for `work`: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
