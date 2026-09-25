"""
scripts/test_handoff_md_structure.py — handoff.md must not hardcode
model='claude-code' (that's wrong when run from Codex); it must instead
leave an explicit substitution placeholder, consistent with the existing
<project>/<session_id> placeholder style already used in this same file.

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
check("Codex handoff requires a host receipt",
      "GC_RECEIPT" in content and "Missing\nreceipt means **pending**" in content)
check("routine handoff does not synthesize", "gc-read.sh today-context" not in content)
check("routine handoff does not check rollups", "weekly-rollup-check" not in content)
check("routine handoff does not trim docs", "claude-trim-" not in content)
check("routine handoff does not delegate", "Do not delegate" in content)
check("full handoff gathers whole-day context", "gc-read.sh today-context" in full)
check("full handoff uses guarded persistence", "gc-write.sh save-daily-summary" in full)
check("full handoff preserves revision and prose", "context_revision" in full and "existing_daily" in full)
check("full handoff attributes the actual agent", '"model": "<claude-code|codex>"' in full)
check("maintenance retains protected size trim", "SHARED-CONVENTIONS" in maintenance and "stat -c %Y" in maintenance)
check("maintenance preserves public review gate", "Never run the publish step yourself" in maintenance)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
