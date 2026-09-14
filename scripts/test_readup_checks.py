"""
scripts/test_readup_checks.py — readup-checks.sh bundles readup's read-only
probes into one call. Standalone runner (not pytest).
"""
import os
import subprocess
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow/bin/readup-checks.sh")
failures = []


def check(name, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


check("script is executable", os.access(SCRIPT, os.X_OK))
src = open(SCRIPT).read()
check("no BSD-only tail -r", "tail -r" not in src)
check("stat has GNU fallback", "stat -c" in src or "stat -f" not in src)
check("no git pull / checkout / reset (read-only)", not any(w in src for w in ("git pull", "git checkout", "git reset", "git rebase")))

before = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture_output=True, text=True).stdout
r = subprocess.run([SCRIPT], cwd=REPO_DIR, capture_output=True, text=True, timeout=120)
after = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture_output=True, text=True).stdout
check("exits 0", r.returncode == 0, r.stderr[-400:])
check("does not modify the tree", before == after)
out = r.stdout
for key in ("REMOTE=", "RESYNC=age_h=", "CONVENTIONS_CLAUDE=", "CONVENTIONS_AGENTS=", "HANDOFF_SYNC=", "CI_PROBE=", "PUBLIC_DRIFT="):
    check(f"prints {key}", key in out, out[:600])
check("RESYNC carries due=", "due=yes" in out or "due=no" in out)
check("CI_PROBE is one of ok/skip/error", any(f"CI_PROBE={v}" in out for v in ("ok", "skip", "error")))
check("PUBLIC_DRIFT is a known value", any(f"PUBLIC_DRIFT={v}" in out for v in ("ok", "drift", "config", "skip")))
check("worktree line present", "WORKTREES" in out)
check("codex line present", "CODEX_BRANCHES" in out)

# Run from a non-prompt-lab cwd: public check must report skip, not error.
r2 = subprocess.run([SCRIPT], cwd="/tmp", capture_output=True, text=True, timeout=120)
check("outside a repo: still exits 0", r2.returncode == 0, r2.stderr[-400:])
check("outside prompt-lab: PUBLIC_DRIFT=skip", "PUBLIC_DRIFT=skip" in r2.stdout)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
