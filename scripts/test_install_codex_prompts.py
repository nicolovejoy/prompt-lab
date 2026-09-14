"""
scripts/test_install_codex_prompts.py — verify install.sh's Codex-prompt
distribution step exists and that its frontmatter transform is correct.

Does NOT run install.sh (it writes into the real $HOME and loads a real
launchd job — see plan Global Constraints). Instead: (1) a structural check
that install.sh contains the expected loop, and (2) a functional check of
the exact transform (grep -v '^allowed-tools:') against every real command
file, run directly — no filesystem writes outside a temp dir.

Standalone runner (no pytest in this repo).
"""
import subprocess
import glob
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


# 1. Structural: install.sh must reference ~/.codex/prompts and strip allowed-tools.
with open(os.path.join(REPO_DIR, "workflow", "install.sh")) as f:
    install_src = f.read()

check(
    "install.sh references $HOME/.codex/prompts",
    ".codex/prompts" in install_src,
)
check(
    "install.sh strips allowed-tools when writing Codex prompts",
    "allowed-tools" in install_src and "grep -v" in install_src,
)

# 2. Functional: the transform must drop exactly the allowed-tools line (when
#    present) and nothing else, for every real command file.
command_files = sorted(glob.glob(os.path.join(REPO_DIR, "workflow", "commands", "*.md")))
check("found command files to test", len(command_files) > 0, f"found {len(command_files)}")

for path in command_files:
    name = os.path.basename(path)
    with open(path) as f:
        original_lines = f.readlines()

    result = subprocess.run(
        ["grep", "-v", "^allowed-tools:", path], capture_output=True, text=True
    )
    transformed_lines = result.stdout.splitlines(keepends=True)

    had_allowed_tools = any(line.startswith("allowed-tools:") for line in original_lines)
    # Informational only — not every command file is required to have an
    # allowed-tools line. The transform's actual contract (per install.sh's own
    # comment) is "drop the line when present", not "every file has one".
    print(f"[INFO] {name}: has an allowed-tools line to strip = {had_allowed_tools}")
    expected_removed = 1 if had_allowed_tools else 0
    check(
        f"{name}: transform removes exactly {expected_removed} line(s)",
        len(original_lines) - len(transformed_lines) == expected_removed,
        f"{len(original_lines)} -> {len(transformed_lines)}",
    )
    check(
        f"{name}: transform leaves no allowed-tools line behind",
        not any(line.startswith("allowed-tools:") for line in transformed_lines),
    )
    check(
        f"{name}: transform preserves the name: line",
        any(line.startswith("name:") for line in transformed_lines),
    )
    check(
        f"{name}: transform preserves the description: line",
        any(line.startswith("description:") for line in transformed_lines),
    )

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
