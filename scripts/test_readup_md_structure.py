"""
scripts/test_readup_md_structure.py — readup.md must reference the renamed
sync script (not the old name), must reference session-context.sh, and must
check for codex/* branches. Content-level guard against regressions in a
markdown/prose file where a full behavioral test would require a live
agent session.

Standalone runner (no pytest in this repo).
"""
import re
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
    "CODEX_BRANCHES" in content,
)
check("still checks CLAUDE.md drift", "CLAUDE.md" in content)
check("also checks AGENTS.md drift", "AGENTS.md" in content)
check("frontmatter still has a name: line", content.startswith("---\nname: readup"))

check("readup invokes readup-checks.sh", "readup-checks.sh" in content)
check("readup no longer inlines the CI probe", "ci_fields=" not in content)
check("readup keeps the CI error rule", "couldn't read CI status" in content)
check("readup keeps the public-drift fix pointer", "unpublish_public.py" in content)
check("readup keeps ListAgents", "ListAgents" in content)
check("readup keeps lazy synthesis", "unsummarized-context" in content)
check("readup is materially smaller", len(content) < 9000, f"{len(content)} bytes")

# Table-drift guard: every KEY the script can emit must be named in readup.md's
# interpretation table — the catch-all "Anything not listed here → say
# nothing" otherwise silently swallows a new/renamed key.
SCRIPT_PATH = os.path.join(REPO_DIR, "workflow", "bin", "readup-checks.sh")
with open(SCRIPT_PATH) as f:
    script_src = f.read()

# Not anchored to line-start: some lines emit two keys via chained
# `echo "A=..."; echo "B=..."` (e.g. CI_PROBE and CI_MAIN), which an
# anchored ^\s*echo pattern would only catch the first of.
emitted_keys = sorted(set(re.findall(r'echo "([A-Z_]+)[=:]', script_src)))
expected_keys = {
    "HANDOFF_SYNC", "PUBLIC_DRIFT", "CI_PROBE", "CI_PROBE_NOTE", "CI_MAIN",
    "CI_BRANCH", "RESYNC", "CONVENTIONS_CLAUDE", "CONVENTIONS_AGENTS",
    "REMOTE", "TRACKING", "REMOTE_ONLY", "WORKTREES", "CODEX_BRANCHES",
    "PROJECT",
}
check(
    "extraction found all expected keys",
    expected_keys.issubset(set(emitted_keys)),
    f"missing: {expected_keys - set(emitted_keys)}",
)
for k in emitted_keys:
    check(f"table documents {k}", k in content)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
