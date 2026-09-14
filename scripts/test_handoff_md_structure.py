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
    '"model": "<claude-code|codex>"' in content,
)
check(
    "weekly-rollup persist uses the agent-choice placeholder",
    content.count("model='<claude-code|codex>'") == 1,
)

check("handoff validates the retained session ID", "current-session <session_id>" in content)
check("handoff gathers whole-day context", "gc-read.sh today-context" in content)
check("handoff uses guarded daily persistence", "gc-write.sh save-daily-summary" in content)
check("handoff retains context revision", "context_revision" in content)
check("handoff preserves earlier daily prose", "existing_daily" in content)

check("handoff has the weekly CLAUDE.md size check", "## 2.5 CLAUDE.md size check" in content)
check("size check uses the state marker", "claude-trim-" in content)
check("size check names the history file", "docs/history.md" in content)
check("size check has a GNU stat fallback", "stat -c %Y" in content)
check("size check protects the conventions block", "SHARED-CONVENTIONS" in content)
check("size check runs before daily summary", content.index("## 2.5 CLAUDE.md size check") < content.index("## 3. Synthesize daily summary"))

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
