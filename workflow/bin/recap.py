#!/usr/bin/env python3
"""recap [DAYS] [PROJECT] — what each recent session said to do next.

Reads summarised sessions from the history DB (read-only). Default: newest
session per project, up to 8 projects. With PROJECT: that project's newest 3.
"""
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MAX_PROJECTS = 8
PROJECT_SESSIONS = 3
PACIFIC = ZoneInfo("America/Los_Angeles")
TS = "%Y-%m-%d %H:%M:%S"
WHEN = "COALESCE(NULLIF(ended_at, ''), started_at)"


def line_text(summary):
    s = " ".join(summary.split())
    if "Next:" in s:
        return s.split("Next:", 1)[1].strip()
    m = re.search(r"[.!?](\s|$)", s)
    return s[: m.start() + 1] if m else s


def pacific_day(ts):
    dt = datetime.strptime(ts[:19], TS).replace(tzinfo=timezone.utc)
    return dt.astimezone(PACIFIC).strftime("%m-%d")


def main(argv):
    days, project = 7, None
    for a in argv:
        if a.isdigit():
            days = int(a)
        else:
            project = a
    db = os.environ.get("PROMPT_HISTORY_DB") or os.path.expanduser("~/.claude/prompt-history.db")
    if not os.path.exists(db):
        print(f"recap: no history DB at {db}", file=sys.stderr)
        return 1
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(TS)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            f"SELECT project, {WHEN} AS t, summary FROM sessions "
            f"WHERE summary IS NOT NULL AND TRIM(summary) != '' AND project != 'scratch' "
            f"AND {WHEN} >= ? ORDER BY t DESC",
            (cutoff,),
        ).fetchall()
    except sqlite3.Error as e:
        print(f"recap: cannot read history DB: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()

    if project:
        picked = [r for r in rows if r[0] == project][:PROJECT_SESSIONS]
    else:
        picked, seen = [], set()
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                picked.append(r)
        picked = picked[:MAX_PROJECTS]
    if not picked:
        print(f"no summarised sessions in the last {days} days")
        return 0

    width = shutil.get_terminal_size((100, 20)).columns
    pad = max(len(r[0]) for r in picked)
    for proj, t, summary in picked:
        prefix = f"{proj:<{pad}}  {pacific_day(t)}  "
        text = line_text(summary)
        room = max(width - len(prefix), 1)
        if len(text) > room:
            text = text[: room - 1].rstrip() + "…"
        print(prefix + text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
