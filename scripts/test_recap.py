"""
scripts/test_recap.py — verify workflow/bin/recap.py against a temp DB.

Standalone runner (this repo doesn't use pytest — see CLAUDE.md Testing section).
Never touches the real history DB.
"""
import os
import shutil
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
    env = dict(os.environ, PROMPT_HISTORY_DB=db, COLUMNS=cols, RECAP_SRC=src, RECAP_STATE=state)
    return subprocess.run([SCRIPT, *args], capture_output=True, text=True, env=env)


def git(repo, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when + " +0000"
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


def make_repo(name, commits):
    repo = os.path.join(src, name)
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    for when, subject in commits:
        git(repo, "commit", "-q", "--allow-empty", "-m", subject, when=when)


def body(line):
    """A line minus its leading recap number."""
    return line.split(None, 1)[1] if line[:1].strip() == "" or line.split()[0].isdigit() else line


tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "src")
state = os.path.join(tmp, "state", "recap-last.txt")
os.makedirs(src)
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
# alpha: 2 commits in window, 1 outside. commitonly: no sessions, newest touch of all.
make_repo("alpha", [(ago(30), "old"), (ago(2), "a1"), (ago(1), "a2")])
make_repo("commitonly", [(ago(1), "first"), (ago(0, 2), "newest subject")])
make_repo("quiet", [(ago(40), "long ago")])
os.makedirs(os.path.join(src, "notarepo"))

r = run(db)
lines = r.stdout.splitlines()
names = [line.split()[1] for line in lines]
check("exit 0", r.returncode == 0, r.stderr)
check("lines are numbered 1..n", [line.split()[0] for line in lines] == [str(i) for i in range(1, len(lines) + 1)], r.stdout)
check("Next: extraction", any("ship the widget" in line for line in lines), r.stdout)
check("Next: text has no summary prefix", not any("Merged #1" in line for line in lines))
check("first-sentence fallback", any(n == "beta" and line.endswith("Fixed the parser.") for n, line in zip(names, lines)), r.stdout)
check("bare Next: falls back to first sentence", any(n == "bare" and line.endswith("Wrapped up the thing.") for n, line in zip(names, lines)), r.stdout)
check("one line per project", names.count("alpha") == 1, r.stdout)
check("older alpha not shown", not any("stale item" in line for line in lines))
check("empty-string ended_at falls back to started_at", "beta" in names)
check("session without summary still listed", any(n == "empty" and "(no summary)" in line for n, line in zip(names, lines)), r.stdout)
check("scratch excluded", "scratch" not in names)
check("outside 14-day default window excluded", "gamma" not in names)
check("commit-only repo listed with its newest subject", any(n == "commitonly" and "last commit: newest subject" in line for n, line in zip(names, lines)), r.stdout)
check("commit-only repo is newest touch, so first", names[0] == "commitonly", r.stdout)
check("git commit count in window", any(n == "alpha" and " 2c " in line for n, line in zip(names, lines)), r.stdout)
check("no-repo project shows 0c", any(n == "beta" and " 0c " in line for n, line in zip(names, lines)), r.stdout)
check("repo quiet in window excluded", "quiet" not in names and "notarepo" not in names, r.stdout)
check("projects newest touch first", names.index("alpha") < names.index("beta") < names.index("delta"), str(names))
check("truncation ends with ellipsis", any(n == "delta" and line.endswith("…") for n, line in zip(names, lines)))
check("lines fit width", all(len(line) <= 100 for line in lines))
saved = open(state).read().splitlines() if os.path.exists(state) else []
check("numbers saved for work, in order", saved == names, f"{saved} vs {names}")

r = run(db, "30")
check("DAYS arg widens window", "gamma" in [line.split()[1] for line in r.stdout.splitlines()])
r = run(db, "1", "alpha")
check("DAYS + PROJECT any order", r.stdout.count("alpha") == 1, r.stdout)
r = run(db, "alpha")
pl = r.stdout.splitlines()
check("PROJECT mode newest 3", len(pl) == 3 and all(line.startswith("alpha") for line in pl), r.stdout)
check("PROJECT mode newest first", "ship the widget" in pl[0] and "third item" in pl[2], r.stdout)

r = run(db, "9999", "pacific")
check("Pacific date (03:00 UTC 11-05 -> 11-04)", "  11-04  " in r.stdout, r.stdout)

r = run(db, "nosuch")
check("empty result message", r.stdout.strip() == "no summarised sessions in the last 14 days", r.stdout)

r = run(os.path.join(tmp, "missing.db"))
check("missing DB exits 1", r.returncode == 1 and r.stderr.strip() != "" and r.stdout == "")

# work.zsh: `work 1 3` resolves recap numbers; model/effort asked once. Needs zsh (not on CI).
WORK = os.path.join(REPO_DIR, "workflow", "shell", "work.zsh")
if shutil.which("zsh"):
    for n in ("commitonly", "beta"):
        os.makedirs(os.path.join(src, n), exist_ok=True)
    open(state, "w").write("commitonly\nbeta\nalpha\n")

    def work(*args):
        script = (
            f"source {WORK}; WORK_SRC_DIR={src}; WORK_RECAP_STATE={state}; "
            "_work_window() { echo WINDOW \"$1\" | grep -o -- '--name [^ ]*'; }; "
            "_work_model() { echo ASK-MODEL; REPLY=${1:-opus}; }; "
            "_work_effort() { echo ASK-EFFORT; REPLY=${1:-high}; }; "
            "work " + " ".join(args)
        )
        return subprocess.run(["zsh", "-fc", script], capture_output=True, text=True)

    r = work("1", "3")
    check("work 1 3 opens recap lines 1 and 3", "Opening: commitonly, alpha" in r.stdout and r.stdout.count("--name") == 2, r.stdout + r.stderr)
    check("work N asks model/effort once", r.stdout.count("ASK-MODEL") == 1 and r.stdout.count("ASK-EFFORT") == 1, r.stdout)
    r = work("2", "sonnet", "low")
    check("work N passes model/effort through", "Opening: beta" in r.stdout and r.stdout.count("--name") == 1, r.stdout + r.stderr)
    r = work("9")
    check("work out-of-range number refuses", "no line 9" in r.stdout and "--name" not in r.stdout, r.stdout)
    r = work("alpha")
    check("work NAME still opens by name", r.stdout.count("--name") == 1 and "Opening" not in r.stdout, r.stdout + r.stderr)
    os.utime(state, (0, 0))
    r = work("1")
    check("work N refuses a stale recap", "run recap first" in r.stdout and "--name" not in r.stdout, r.stdout)
else:
    print("[SKIP] work.zsh checks — zsh not installed")

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall passed")
