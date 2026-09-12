"""
scripts/test_sync_shared_md.py — the shared-conventions sync script must
work identically against a CLAUDE.md-named and an AGENTS.md-named target,
using the same canonical source and content hash for both.

Standalone runner (no pytest in this repo).
"""
import subprocess
import tempfile
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow", "bin", "sync-shared-md.sh")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with tempfile.TemporaryDirectory() as tmp:
    canonical = os.path.join(tmp, "shared-source.md")
    with open(canonical, "w") as f:
        f.write("# Shared conventions\n\n- Rule one\n- Rule two\n")

    env = {**os.environ, "CLAUDE_MD_SHARED": canonical}

    for target_name in ("CLAUDE.md", "AGENTS.md"):
        target = os.path.join(tmp, target_name)

        apply_result = subprocess.run(
            [SCRIPT, "--apply", target], env=env, capture_output=True, text=True
        )
        check(f"--apply creates {target_name}", os.path.exists(target))
        check(f"--apply on {target_name} exits 0", apply_result.returncode == 0)

        check_result = subprocess.run(
            [SCRIPT, "--check", target], env=env, capture_output=True, text=True
        )
        check(
            f"--check reports in sync for {target_name}",
            check_result.returncode == 0 and "in sync" in check_result.stdout,
            check_result.stdout,
        )

        with open(target) as f:
            content = f.read()
        check(f"{target_name} contains canonical body", "Rule one" in content and "Rule two" in content)

    # Both targets must carry the SAME hash — same canonical source, same stamp.
    with open(os.path.join(tmp, "CLAUDE.md")) as f:
        claude_content = f.read()
    with open(os.path.join(tmp, "AGENTS.md")) as f:
        agents_content = f.read()
    import re

    claude_hash = re.search(r"v=([a-f0-9]+)", claude_content)
    agents_hash = re.search(r"v=([a-f0-9]+)", agents_content)
    check(
        "CLAUDE.md and AGENTS.md carry the same content hash",
        claude_hash and agents_hash and claude_hash.group(1) == agents_hash.group(1),
    )

    # Drift detection: changing the canonical source should flip --check to drift.
    with open(canonical, "a") as f:
        f.write("- Rule three\n")
    drift_result = subprocess.run(
        [SCRIPT, "--check", os.path.join(tmp, "CLAUDE.md")], env=env, capture_output=True, text=True
    )
    check(
        "--check reports drift after canonical source changes",
        drift_result.returncode == 1 and "drift" in drift_result.stdout,
        drift_result.stdout,
    )

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
