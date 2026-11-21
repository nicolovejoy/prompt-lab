"""
scripts/test_handoff_md_structure.py — structural guards on the handoff
commands: the routine handoff saves continuity before closing and never
synthesizes; the full handoff gathers whole-day context, persists through the
guarded helpers and attributes the daily summary to claude-code.

Standalone runner (no pytest in this repo).
"""
import subprocess
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
PATH = os.path.join(REPO_DIR, "workflow", "commands", "handoff.md")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with open(PATH) as f:
    content = f.read()

full = open(os.path.join(REPO_DIR, "workflow/commands/handoff-full.md")).read()
maintenance = open(os.path.join(REPO_DIR, "workflow/commands/workflow-maintenance.md")).read()
check("handoff validates the retained session ID", "current-session <session_id>" in content)
check("handoff saves continuity before closing",
      content.index("update-session-summary") < content.index("gc-write.sh end-session"))
check("routine handoff does not synthesize", "gc-read.sh today-context" not in content)
check("routine handoff does not check rollups", "weekly-rollup-check" not in content)
check("routine handoff does not trim docs", "claude-trim-" not in content)
check("routine handoff does not delegate", "Do not delegate" in content)
check("full handoff gathers whole-day context", "gc-read.sh today-context" in full)
check("full handoff uses guarded persistence", "gc-write.sh save-daily-summary" in full)
check("full handoff preserves revision and prose", "context_revision" in full and "existing_daily" in full)
check("full handoff attributes the agent", '"model": "claude-code"' in full)
check("maintenance retains protected size trim",
      "SHARED-CONVENTIONS" in maintenance and "claude-md-size.sh" in maintenance and "claude-trim-" in maintenance)
check("maintenance may run the size helper",
      "Bash(~/.claude/bin/claude-md-size.sh:*)" in maintenance.split("---")[1])
# /handoff reads the checkout through gc-vcs.sh so a Fossil checkout is not
# recorded as "no commits, clean tree" (ear-worm, 2026-11-20).
check("handoff reads uncommitted work through gc-vcs.sh", "gc-vcs.sh status" in content)
check("handoff reads commits through gc-vcs.sh", 'gc-vcs.sh commits-since "<started_at>"' in content)
check("handoff no longer calls git directly", "git status" not in content.split("do not run")[0] and "git log" not in content)
check("handoff may run gc-vcs.sh", "Bash(~/.claude/bin/gc-vcs.sh:*)" in content.split("---")[1])
check("handoff never records an unread checkout as zero", "Never record that as zero" in content)
check("maintenance preserves public review gate", "Never run the publish step yourself" in maintenance)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
