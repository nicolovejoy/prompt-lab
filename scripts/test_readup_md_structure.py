"""
scripts/test_readup_md_structure.py — readup.md must reference the renamed
sync script (not the old name), must reference session-context.sh, and must
check for codex/* branches. Content-level guard against regressions in a
markdown/prose file where a full behavioral test would require a live
agent session.

Standalone runner (no pytest in this repo).
"""
import subprocess
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
PATH = os.path.join(REPO_DIR, "workflow", "commands", "readup.md")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with open(PATH) as f:
    content = f.read()

check("no reference to the old script name remains", "sync-claude-md.sh" not in content)
check("references the renamed sync script", "sync-shared-md.sh" in content)
check("references session-context.sh", "session-context.sh" in content)
check(
    "checks for codex/* branches",
    "git branch --list 'codex/*'" in content
    and "git branch -r --list 'origin/codex/*'" in content,
)
check("still checks CLAUDE.md drift", "CLAUDE.md" in content)
check("also checks AGENTS.md drift", "AGENTS.md" in content)
check("frontmatter still has a name: line", content.startswith("---\nname: readup"))

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
