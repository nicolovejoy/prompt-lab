"""
scripts/test_session_context.py — verify session-context.sh and
session-start.sh agree, and that session-context.sh's own guard clauses work.

Standalone runner (this repo doesn't use pytest — see CLAUDE.md Testing section).
"""
import json
import os
import pathlib
import subprocess
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

failures = []

# The "neglected custom commands" nudge in session-context.sh is
# self-extinguishing: if the nudge stamp is >7 days stale and a command
# qualifies, whichever of the two invocations below runs first emits the
# nudge text AND touches the stamp, so the second invocation won't see it —
# making the two outputs differ and flaking the startswith assertion below
# about once a week. Freshen (or create) the stamp right before both
# invocations so they see identical "not yet due" nudge-eligibility state.
NUDGE_STAMP = pathlib.Path.home() / ".claude" / "state" / "commands-nudge.touch"
NUDGE_STAMP.parent.mkdir(parents=True, exist_ok=True)
NUDGE_STAMP.touch(exist_ok=True)
os.utime(NUDGE_STAMP, None)


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


# 1. session-context.sh run standalone from the repo root produces non-empty
#    output containing the expected field labels.
ctx_result = subprocess.run(
    ["workflow/bin/session-context.sh"], cwd=REPO_DIR, capture_output=True, text=True
)
check("session-context.sh exits 0", ctx_result.returncode == 0)
ctx_out = ctx_result.stdout
check("session-context.sh output non-empty", len(ctx_out.strip()) > 0)
for label in ("Today:", "Machine:", "Project:", "Working dir:"):
    check(f"session-context.sh output contains '{label}'", label in ctx_out)

# 2. session-start.sh's JSON output wraps EXACTLY session-context.sh's stdout
#    plus the readup nudge sentence — i.e. the hook is a thin wrapper, not a
#    second copy of the gathering logic.
hook_result = subprocess.run(
    ["workflow/hooks/session-start.sh"],
    cwd=REPO_DIR,
    input="{}",
    capture_output=True,
    text=True,
)
check("session-start.sh exits 0", hook_result.returncode == 0)
try:
    hook_json = json.loads(hook_result.stdout)
    additional_context = hook_json["hookSpecificOutput"]["additionalContext"]
    check("session-start.sh output is valid JSON with additionalContext", True)
except (json.JSONDecodeError, KeyError) as e:
    check("session-start.sh output is valid JSON with additionalContext", False, str(e))
    additional_context = ""

expected_suffix = (
    "The user has NOT run /readup yet — they may or may not. Do not "
    "preemptively summarize. Use this context to answer their first "
    "message in an informed way."
)
check(
    "hook's additionalContext starts with session-context.sh's stdout",
    additional_context.startswith(ctx_out),
)
check(
    "hook's additionalContext ends with the readup nudge sentence",
    additional_context.rstrip().endswith(expected_suffix),
)

# 3. Guard clause: outside ~/src/*, session-context.sh prints nothing.
outside_result = subprocess.run(
    ["bash", "-c", f'cd /tmp && "{REPO_DIR}/workflow/bin/session-context.sh"'],
    capture_output=True,
    text=True,
)
check("session-context.sh silent outside ~/src/*", outside_result.stdout == "")

# 4. Guard clause at hook level: when session-context.sh produces empty output
#    (guard fails), session-start.sh exits 0 with zero stdout (no JSON) to
#    preserve the exact old behavior when the guard fails.
hook_outside_result = subprocess.run(
    ["bash", "-c", f'cd /tmp && "{REPO_DIR}/workflow/hooks/session-start.sh"'],
    input="{}",
    capture_output=True,
    text=True,
)
check("session-start.sh produces zero stdout outside ~/src/*", hook_outside_result.stdout == "")
check("session-start.sh exits 0 outside ~/src/*", hook_outside_result.returncode == 0)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
