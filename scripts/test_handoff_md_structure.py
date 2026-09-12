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

check("no hardcoded model='claude-code'", "model='claude-code'" not in content)
check(
    "daily-summary persist uses the agent-choice placeholder",
    "model='<claude-code|codex>'" in content,
)
check(
    "weekly-rollup persist uses the agent-choice placeholder",
    content.count("model='<claude-code|codex>'") == 2,
)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
