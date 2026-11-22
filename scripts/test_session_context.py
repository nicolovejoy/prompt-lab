"""
scripts/test_session_context.py — verify session-context.sh and
session-start.sh agree, and that session-context.sh's own guard clauses work.

Standalone runner (this repo doesn't use pytest — see CLAUDE.md Testing section).
"""
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

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

# 5. Handoff channel injection is headline-only and age-capped. Build a fake
#    ~/src/.handoff with one channel matching this repo's basename and three
#    entries: fresh, stale, and fresh-with-a-multiline-body. Bodies must never
#    reach the output (they were 99% of a 194 KB injection on 2026-09-13).
project = os.path.basename(REPO_DIR)
fresh = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
stale = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
with tempfile.TemporaryDirectory() as td:
    hd = pathlib.Path(td) / ".handoff"
    (hd / ".git").mkdir(parents=True)
    channel = hd / f"peer-{project}.md"
    channel.write_text(
        "---\n"
        f"repos: [peer, {project}]\n"
        "---\n"
        "## Active\n\n"
        f"### {fresh} peer → {project}: FRESH_HEADLINE_ONE\n\n"
        "BODY_LINE_MUST_NOT_APPEAR_ONE\n\n"
        f"### {stale} peer → {project}: STALE_HEADLINE\n\n"
        "BODY_LINE_MUST_NOT_APPEAR_TWO\n\n"
        f"### {fresh} {project} → peer: FRESH_HEADLINE_TWO\n\n"
        "BODY_LINE_MUST_NOT_APPEAR_THREE\nsecond body line\n\n"
        "## Archived\n\n"
        f"### {fresh} peer → {project}: ARCHIVED_HEADLINE\n"
    )
    env = dict(os.environ, HANDOFF_DIR=str(hd), HANDOFF_BIN="/nonexistent/handoff.sh")
    r = subprocess.run(
        ["workflow/bin/session-context.sh"], cwd=REPO_DIR, capture_output=True, text=True, env=env
    )
    out = r.stdout
    check("handoff: script exits 0 with fake channel", r.returncode == 0, r.stderr[-300:])
    check("handoff: fresh headline one listed", "FRESH_HEADLINE_ONE" in out)
    check("handoff: fresh headline two listed", "FRESH_HEADLINE_TWO" in out)
    check("handoff: stale headline NOT listed", "STALE_HEADLINE" not in out)
    check("handoff: archived headline NOT listed", "ARCHIVED_HEADLINE" not in out)
    check("handoff: no body text leaks", "BODY_LINE_MUST_NOT_APPEAR" not in out and "second body line" not in out)
    check("handoff: counts in header", f"peer-{project}.md: 3 active entries, 2 newer than 30d" in out)
    check("handoff: points at the file for bodies", f"cat ~/src/.handoff/peer-{project}.md" in out)

    # Window is overridable (so a repo can widen it) — with 100 days the stale one shows.
    env2 = dict(env, HANDOFF_HEADLINE_DAYS="100")
    out2 = subprocess.run(
        ["workflow/bin/session-context.sh"], cwd=REPO_DIR, capture_output=True, text=True, env=env2
    ).stdout
    check("handoff: HANDOFF_HEADLINE_DAYS widens the window", "STALE_HEADLINE" in out2)
    check("handoff: widened header counts", "3 active entries, 3 newer than 100d" in out2)

    # Non-numeric window falls back to the 30d default rather than admitting
    # every entry ever written (empty cutoff from a failed `date` call).
    env_bad = dict(env, HANDOFF_HEADLINE_DAYS="abc")
    out_bad = subprocess.run(
        ["workflow/bin/session-context.sh"], cwd=REPO_DIR, capture_output=True, text=True, env=env_bad
    ).stdout
    check("handoff: non-numeric HANDOFF_HEADLINE_DAYS falls back to 30d", "newer than 30d" in out_bad)

    # M == 0: a channel with only stale entries still prints its header (with
    # count) so an old-but-unarchived backlog stays visible — just no headlines.
    env3 = dict(env, HANDOFF_HEADLINE_DAYS="1")
    out3 = subprocess.run(
        ["workflow/bin/session-context.sh"], cwd=REPO_DIR, capture_output=True, text=True, env=env3
    ).stdout
    check("handoff: M==0 header still prints", f"peer-{project}.md: 3 active entries, 0 newer than 1d" in out3)
    check(
        "handoff: M==0 no headlines listed",
        "FRESH_HEADLINE_ONE" not in out3 and "FRESH_HEADLINE_TWO" not in out3 and "STALE_HEADLINE" not in out3,
    )

# 6. A Fossil checkout under ~/src gets start context too. It used to get none:
#    "not a git repo" was read as "not a project" (ear-worm, 2026-11-20). Runs
#    against a fake `fossil` and a temp HOME, so CI needs no Fossil.
with tempfile.TemporaryDirectory() as td:
    home = pathlib.Path(td).resolve() / "home"
    checkout = home / "src" / "ear-worm"
    checkout.mkdir(parents=True)
    (checkout / ".fslckout").write_text("")
    plain = home / "src" / "just-a-folder"
    plain.mkdir()
    fakebin = home / "fakebin"
    fakebin.mkdir()
    fossil = fakebin / "fossil"
    fossil.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  timeline) printf '4ac5718d63 add the lyric view\\n14787350f3 initial empty check-in\\n"
        "+++ no more data (2) +++\\n' ;;\n"
        "  changes) printf 'EDITED     Sources/App.swift\\nEXTRA      .hidden\\n' ;;\n"
        "esac\n"
    )
    fossil.chmod(0o755)
    script = f"{REPO_DIR}/workflow/bin/session-context.sh"
    env = dict(os.environ, HOME=str(home), PATH=f"{fakebin}:{os.environ['PATH']}",
               HANDOFF_DIR=str(home / "no-handoff"))

    r = subprocess.run([script], cwd=checkout, capture_output=True, text=True, env=env)
    out = r.stdout
    check("fossil: script exits 0", r.returncode == 0, r.stderr[-300:])
    check("fossil: checkout gets context", "Project: ear-worm" in out, out[:300])
    check("fossil: context says the checkout is Fossil", "Checkout: Fossil, not git." in out)
    check("fossil: recent commits listed", "4ac5718d63 add the lyric view" in out)
    check("fossil: timeline trailer is not a commit", "no more data" not in out)
    check("fossil: uncommitted and untracked files listed",
          "Uncommitted:\nEDITED     Sources/App.swift\nEXTRA      .hidden" in out)

    # A fossil that fails (a moved repository file, an older version) is not
    # "no commits, clean tree".
    fossil.write_text("#!/bin/sh\necho 'repository does not exist' >&2\nexit 1\n")
    r = subprocess.run([script], cwd=checkout, capture_output=True, text=True, env=env)
    check("fossil failing: says commits and files were NOT read",
          "A fossil command failed" in r.stdout and "were NOT read" in r.stdout
          and "Recent commits:" not in r.stdout and "Uncommitted:" not in r.stdout,
          r.stdout[:400])

    # session-context.sh copied alone: it cannot tell a Fossil checkout from a
    # plain folder, and must say so rather than print nothing.
    lone = home / "lonebin"
    lone.mkdir()
    shutil.copy(script, lone / "session-context.sh")
    r = subprocess.run([str(lone / "session-context.sh")], cwd=checkout,
                       capture_output=True, text=True, env=env)
    check("helper missing: says context was not produced",
          "not produced" in r.stdout and "_gc_project.sh" in r.stdout, r.stdout[:300])

    silent = subprocess.run([script], cwd=plain, capture_output=True, text=True, env=env)
    check("a plain folder under ~/src still gets nothing", silent.stdout == "")

    # A repository git cannot read (exit 128 under a .git entry) is a project.
    # It used to get no context at all, like a plain folder.
    damaged = home / "src" / "damaged"
    (damaged / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=damaged, check=True, capture_output=True)
    (damaged / ".git" / "HEAD").unlink()
    r = subprocess.run([script], cwd=damaged / "sub", capture_output=True, text=True, env=env)
    check("damaged repo: says context was not produced, and why",
          "not produced" in r.stdout and "git could not read this checkout (exit 128)" in r.stdout
          and "were NOT read" in r.stdout, r.stdout[:400])
    check("damaged repo: no commits or clean tree are claimed",
          "Recent commits:" not in r.stdout and "Uncommitted:" not in r.stdout, r.stdout[:400])

    # A git that fails any other way (the Xcode license prompt) says so as well.
    gitbin = home / "brokengit"
    gitbin.mkdir()
    (gitbin / "git").write_text("#!/bin/sh\necho 'xcode license not accepted' >&2\nexit 69\n")
    (gitbin / "git").chmod(0o755)
    r = subprocess.run([script], cwd=plain, capture_output=True, text=True,
                       env=dict(env, PATH=f"{gitbin}:{env['PATH']}"))
    check("broken git: says context was not produced, with git's message",
          "not produced" in r.stdout and "(exit 69): xcode license not accepted" in r.stdout,
          r.stdout[:400])

    bare = "/usr/bin:/bin"
    if shutil.which("fossil", path=bare):
        print("[SKIP] missing-fossil case: /usr/bin:/bin holds a fossil here")
    else:
        r = subprocess.run([script], cwd=checkout, capture_output=True, text=True,
                           env=dict(env, PATH=bare))
        check("fossil missing: says commits and files were NOT read",
              "were NOT read" in r.stdout and "Recent commits:" not in r.stdout, r.stdout[:400])

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
