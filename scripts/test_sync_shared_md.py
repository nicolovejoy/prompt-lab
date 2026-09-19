"""
scripts/test_sync_shared_md.py — the shared-conventions sync script must
work identically against a CLAUDE.md-named and an AGENTS.md-named target,
using the same canonical source and content hash for both.

Standalone runner (no pytest in this repo).
"""
import subprocess
import tempfile
import os
import re
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

    def run(mode, target):
        return subprocess.run(
            [SCRIPT, mode, target], env=env, capture_output=True, text=True
        )

    for target_name in ("CLAUDE.md", "AGENTS.md"):
        target = os.path.join(tmp, target_name)
        bespoke = f"# {target_name} project instructions\n\nKeep this content.\n"
        with open(target, "w") as f:
            f.write(bespoke)

        apply_result = run("--apply", target)
        check(f"--apply adds a block to {target_name}", os.path.exists(target))
        check(f"--apply on {target_name} exits 0", apply_result.returncode == 0)

        check_result = run("--check", target)
        check(
            f"--check reports in sync for {target_name}",
            check_result.returncode == 0 and "in sync" in check_result.stdout,
            check_result.stdout,
        )

        with open(target) as f:
            content = f.read()
        check(f"{target_name} contains canonical body", "Rule one" in content and "Rule two" in content)
        check(f"{target_name} preserves content outside the block", content.startswith(bespoke))

        # Editing the body without changing the recorded marker is local damage,
        # not ordinary fleet lag. Check must expose it and apply must not erase it.
        tampered = content.replace("- Rule one", "- Locally changed rule", 1)
        with open(target, "w") as f:
            f.write(tampered)
        tampered_result = run("--check", target)
        check(
            f"--check reports tampered body for {target_name}",
            tampered_result.returncode == 1 and "tampered" in tampered_result.stdout,
            tampered_result.stdout,
        )
        refused_result = run("--apply", target)
        with open(target) as f:
            after_refusal = f.read()
        check(
            f"--apply refuses tampered {target_name}",
            refused_result.returncode == 6 and after_refusal == tampered,
            refused_result.stderr,
        )
        with open(target, "w") as f:
            f.write(content)

    # Both targets must carry the SAME hash — same canonical source, same stamp.
    with open(os.path.join(tmp, "CLAUDE.md")) as f:
        claude_content = f.read()
    with open(os.path.join(tmp, "AGENTS.md")) as f:
        agents_content = f.read()
    claude_hash = re.search(r"v=([a-f0-9]+)", claude_content)
    agents_hash = re.search(r"v=([a-f0-9]+)", agents_content)
    check(
        "CLAUDE.md and AGENTS.md carry the same content hash",
        claude_hash and agents_hash and claude_hash.group(1) == agents_hash.group(1),
    )

    # A canonical change leaves the old block internally valid: it is behind,
    # not tampered. Explicit apply updates it and preserves bespoke text.
    with open(canonical, "a") as f:
        f.write("- Rule three\n")
    for target_name in ("CLAUDE.md", "AGENTS.md"):
        target = os.path.join(tmp, target_name)
        behind_result = run("--check", target)
        check(
            f"--check reports clean behind state for {target_name}",
            behind_result.returncode == 1 and "behind" in behind_result.stdout,
            behind_result.stdout,
        )
        refresh_result = run("--apply", target)
        refreshed_result = run("--check", target)
        with open(target) as f:
            refreshed = f.read()
        check(f"--apply refreshes behind {target_name}", refresh_result.returncode == 0)
        check(f"refreshed {target_name} returns to in sync", refreshed_result.returncode == 0)
        check(f"refresh preserves bespoke {target_name} content", "Keep this content." in refreshed)

    missing_target = os.path.join(tmp, "MISSING.md")
    with open(missing_target, "w") as f:
        f.write("# Existing file without a shared block\n")
    missing_result = run("--check", missing_target)
    check("--check reports missing block", missing_result.returncode == 1 and
          "missing" in missing_result.stdout)
    check("--apply adds a missing block", run("--apply", missing_target).returncode == 0)

    absent_target = os.path.join(tmp, "ABSENT.md")
    absent_result = run("--check", absent_target)
    check("--check distinguishes an absent file", absent_result.returncode == 2 and
          "absent" in absent_result.stdout)

    malformed_target = os.path.join(tmp, "MALFORMED.md")
    with open(malformed_target, "w") as f:
        f.write("""<!-- SHARED-CONVENTIONS:BEGIN v=000000000000 -->
bad
<!-- SHARED-CONVENTIONS:BEGIN v=000000000000 -->
<!-- SHARED-CONVENTIONS:END -->
""")
    malformed_before = open(malformed_target).read()
    malformed_result = run("--check", malformed_target)
    malformed_apply = run("--apply", malformed_target)
    check("duplicate markers are tampered", malformed_result.returncode == 1 and
          "tampered" in malformed_result.stdout)
    check("--apply refuses malformed markers", malformed_apply.returncode == 6 and
          open(malformed_target).read() == malformed_before)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
