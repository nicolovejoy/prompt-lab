"""
scripts/test_recap.py — verify workflow/bin/recap.py against a temp DB.

Standalone runner (this repo doesn't use pytest — see CLAUDE.md Testing section).
Never touches the real history DB.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow", "bin", "recap.py")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def ago(days, hours=0):
    t = datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def run(db, *args, cols="100"):
    env = dict(os.environ, PROMPT_HISTORY_DB=db, COLUMNS=cols)
    return subprocess.run([SCRIPT, *args], capture_output=True, text=True, env=env)


tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "h.db")
con = sqlite3.connect(db)
con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, project TEXT, started_at TEXT, ended_at TEXT, summary TEXT)")
rows = [
    ("alpha", ago(3), ago(3), "Did old thing. Next: stale item"),
    ("alpha", ago(0, 20), ago(0, 20), "Merged #1. Next: ship   the\n  widget"),
    ("beta", ago(2), "", "Fixed the parser. Then more words here."),
    ("gamma", ago(20), ago(20), "Ancient. Next: nothing"),
    ("scratch", ago(0, 1), ago(0, 1), "Scratch work. Next: ignore"),
    ("delta", ago(4), ago(4), "Long. Next: " + "word " * 60),
    ("alpha", ago(5), ago(5), "Third. Next: third item"),
    ("alpha", ago(6), ago(6), "Fourth. Next: fourth item"),
    ("empty", ago(1), ago(1), ""),
    ("bare", ago(2), ago(2), "Wrapped up the thing. Next:   "),
    ("pacific", "2026-11-05 03:00:00", "2026-11-05 03:00:00", "Late. Next: x"),
]
con.executemany("INSERT INTO sessions (project, started_at, ended_at, summary) VALUES (?,?,?,?)", rows)
con.commit()
con.close()

r = run(db)
lines = r.stdout.splitlines()
check("exit 0", r.returncode == 0, r.stderr)
check("Next: extraction", any("ship the widget" in line for line in lines), r.stdout)
check("Next: text has no summary prefix", not any("Merged #1" in line for line in lines))
check("first-sentence fallback", any(line.startswith("beta") and line.endswith("Fixed the parser.") for line in lines), r.stdout)
check("bare Next: falls back to first sentence", any(line.startswith("bare") and line.endswith("Wrapped up the thing.") for line in lines), r.stdout)
check("newest per project (one alpha line)", sum(line.startswith("alpha") for line in lines) == 1)
check("older alpha not shown", not any("stale item" in line for line in lines))
check("empty-string ended_at falls back to started_at", any(line.startswith("beta") for line in lines))
check("empty summary excluded", not any(line.startswith("empty") for line in lines))
check("scratch excluded", not any("scratch" in line.lower() for line in lines))
check("outside DAYS window excluded", not any(line.startswith("gamma") for line in lines))
order = [line.split()[0] for line in lines]
check("projects newest first", order.index("alpha") < order.index("beta") < order.index("delta"), str(order))
check("truncation ends with ellipsis", any(line.startswith("delta") and line.endswith("…") for line in lines))
check("lines fit width", all(len(line) <= 100 for line in lines))

r = run(db, "30")
check("DAYS arg widens window", any(line.startswith("gamma") for line in r.stdout.splitlines()))
r = run(db, "1", "alpha")
check("DAYS + PROJECT any order", r.stdout.count("alpha") == 1, r.stdout)
r = run(db, "alpha")
pl = r.stdout.splitlines()
check("PROJECT mode newest 3", len(pl) == 3 and all(line.startswith("alpha") for line in pl), r.stdout)
check("PROJECT mode newest first", "ship the widget" in pl[0] and "third item" in pl[2], r.stdout)

r = run(db, "9999", "pacific")
check("Pacific date (03:00 UTC 11-05 -> 11-04)", "  11-04  " in r.stdout, r.stdout)

r = run(db, "nosuch")
check("empty result message", r.stdout.strip() == "no summarised sessions in the last 7 days", r.stdout)

r = run(os.path.join(tmp, "missing.db"))
check("missing DB exits 1", r.returncode == 1 and r.stderr.strip() != "" and r.stdout == "")

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall passed")
