"""Deterministic wrapper probes; no live git, network, DB, or handoff sync."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "workflow/bin/readup-checks.sh"
failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)
        print(detail)


with tempfile.TemporaryDirectory(prefix="readup-checks-") as tmp:
    home = Path(tmp) / "home"
    home.mkdir()
    sync_dir = home / ".claude/bin"
    sync_dir.mkdir(parents=True)
    sync = sync_dir / "sync-shared-md.sh"
    sync.write_text('''#!/bin/sh
[ -n "${FAKE_CONV_LOG:-}" ] && printf '%s\n' "$2" >> "$FAKE_CONV_LOG"
case "$2" in
  *CLAUDE.md) state="${FAKE_CONV_CLAUDE:-in sync}" ;;
esac
printf '%s: fixture\n' "$state"
[ "$state" = "in sync" ] && exit 0
[ "$state" = "absent" ] && exit 2
exit 1
''')
    sync.chmod(0o755)
    repo = Path(tmp) / "prompt-lab"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/check_public_allowlist.py").write_text("# Fake audit entrypoint\n")
    fakebin = Path(tmp) / "bin"
    fakebin.mkdir()

    def executable(name, source):
        file = fakebin / name
        file.write_text(source)
        file.chmod(0o755)

    executable("git", '''#!/bin/sh
if [ "${FAKE_OUTSIDE:-0}" = 1 ]; then exit 128; fi
if [ "$1" = -C ]; then shift 2; fi
case "$1" in
  rev-parse)
    case "$2" in
      --is-inside-work-tree) echo true ;;
      --show-toplevel) pwd ;;
      --path-format=absolute) printf '%s/.git\n' "$PWD" ;;
    esac ;;
  fetch) [ "${FAKE_FETCH_RC:-0}" = 0 ] || { echo 'offline' >&2; exit "$FAKE_FETCH_RC"; } ;;
  status) echo '## main...origin/main' ;;
  symbolic-ref) echo refs/remotes/origin/main ;;
  worktree) echo "$PWD fake-head [main]" ;;
  for-each-ref) echo 'main origin/main [behind 1]' ;;
  ls-files) exit "${FAKE_LSFILES_RC:-0}" ;;
esac
exit 0
''')
    executable("gh", '''#!/bin/sh
if [ "$1" = auth ]; then exit "${FAKE_AUTH_RC:-0}"; fi
printf '[]\n'
''')
    executable("python3", '''#!/bin/sh
printf '%s\n' "${FAKE_AUDIT_OUTPUT:-audit result}"
exit "${FAKE_AUDIT_RC:-0}"
''')
    env = dict(os.environ, HOME=str(home), PATH=f"{fakebin}:{os.environ['PATH']}")

    def probe(**overrides):
        result = subprocess.run([str(SCRIPT)], cwd=repo, env=dict(env, **overrides),
                                capture_output=True, text=True, timeout=10)
        check("probe exits zero", result.returncode == 0, result.stderr)
        return result.stdout

    clean = probe()
    for key in ("REMOTE=", "RESYNC=", "CONVENTIONS_CLAUDE=",
                "HANDOFF_SYNC=", "CI_PROBE=", "PUBLIC_DRIFT="):
        check(f"prints {key}", key in clean, clean)
    check("healthy fetch reports tracking", "TRACKING:\n" in clean)
    check("complete clean audit is reported", "PUBLIC_DRIFT=ok" in clean)
    for rc, state in (("10", "drift"), ("2", "config"), ("3", "incomplete"),
                      ("4", "error"), ("1", "error"), ("127", "error")):
        out = probe(FAKE_AUDIT_RC=rc, FAKE_AUDIT_OUTPUT="fixture diagnostic")
        check(f"audit exit {rc} means {state}", f"PUBLIC_DRIFT={state}" in out, out)
        check(f"audit exit {rc} preserves diagnostic", "fixture diagnostic" in out)
    failed_fetch = probe(FAKE_FETCH_RC="7")
    check("fetch failure is explicit", "REMOTE=error" in failed_fetch)
    check("stale tracking is not presented as current",
          "TRACKING=unavailable" in failed_fetch and "[behind 1]" not in failed_fetch)
    failed_auth = probe(FAKE_AUTH_RC="1")
    check("unverifiable authentication is not a silent skip", "CI_PROBE=error" in failed_auth)
    conventions = probe(FAKE_CONV_CLAUDE="behind")
    check("clean shared-block lag is reported as behind",
          "CONVENTIONS_CLAUDE=behind" in conventions)
    tampered = probe(FAKE_CONV_CLAUDE="tampered")
    check("locally changed shared block is reported as tampered",
          "CONVENTIONS_CLAUDE=tampered" in tampered)
    conv_log = Path(tmp) / "conv.log"
    probe(FAKE_CONV_LOG=str(conv_log))
    check("root CLAUDE.md is the default conventions target",
          "./CLAUDE.md" in conv_log.read_text().splitlines())
    conv_log.unlink()
    (repo / ".claude").mkdir()
    (repo / ".claude/CLAUDE.md").write_text("# Project\n")
    probe(FAKE_CONV_LOG=str(conv_log))
    check("with no root CLAUDE.md, .claude/CLAUDE.md is checked",
          "./.claude/CLAUDE.md" in conv_log.read_text().splitlines(), conv_log.read_text())
    (repo / "CLAUDE.md").write_text("# Root\n")
    conv_log.unlink()
    probe(FAKE_CONV_LOG=str(conv_log))
    check("root CLAUDE.md wins when both exist",
          "./CLAUDE.md" in conv_log.read_text().splitlines())
    # CLAUDE.md size: own text only, and quiet for a week after a trim.
    block = ("<!-- SHARED-CONVENTIONS:BEGIN v=x -->\n" + "shared line\n" * 50
             + "<!-- SHARED-CONVENTIONS:END -->\n")
    own = "# Root\n" + "own line é\n" * 20
    (repo / "CLAUDE.md").write_text(own + block)
    own_bytes, shared_bytes = len(own.encode()), len(block.encode())
    sized = probe(CLAUDE_SIZE_LIMIT=str(own_bytes - 1))
    check("size line leaves the shared block out of own_bytes",
          f"CLAUDE_SIZE=own_bytes={own_bytes} shared_bytes={shared_bytes} " in sized, sized)
    check("own text over the limit with no trim marker is due",
          f"limit={own_bytes - 1} " in sized and " due=yes\n" in sized, sized)
    check("own text at the limit is not due, however big the shared block",
          " due=no\n" in probe(CLAUDE_SIZE_LIMIT=str(own_bytes)))
    marker = home / ".claude/state" / f"claude-trim-{repo.name}.touch"
    marker.parent.mkdir()
    marker.write_text("")
    check("a trim in the last 7 days silences the reminder",
          "trim_age_d=0 due=no\n" in probe(CLAUDE_SIZE_LIMIT=str(own_bytes - 1)))
    os.utime(marker, (0, 0))
    check("an old trim marker lets it come due again",
          " due=yes\n" in probe(CLAUDE_SIZE_LIMIT=str(own_bytes - 1)))
    check("a non-numeric limit falls back to the default",
          "limit=30000 " in probe(CLAUDE_SIZE_LIMIT="lots"))
    (repo / "CLAUDE.md").unlink()
    (repo / ".claude/CLAUDE.md").unlink()
    check("no CLAUDE.md is absent, not zero bytes",
          "CLAUDE_SIZE=absent\n" in probe())
    (repo / "CLAUDE.md").write_text("# Root\n")

    outside = probe(FAKE_OUTSIDE="1")
    check("outside repo skips CI and public audit",
          "CI_PROBE=skip" in outside and "PUBLIC_DRIFT=skip" in outside)
    check("a plain directory is not a git repo", "REMOTE=not-a-git-repo\n" in outside, outside)
    # A Fossil checkout is a project whose remote nothing here checks yet.
    (repo / "scripts/deep").mkdir()
    (repo / ".fslckout").write_text("")
    result = subprocess.run([str(SCRIPT)], cwd=repo / "scripts/deep",
                            env=dict(env, FAKE_OUTSIDE="1"), capture_output=True,
                            text=True, timeout=10)
    check("Fossil checkout: remote is reported unchecked, never clean",
          "REMOTE=fossil-unchecked\n" in result.stdout, result.stdout)
    check("Fossil checkout: CLAUDE.md is found from a subdirectory",
          "CONVENTIONS_CLAUDE=in sync" in result.stdout and "CLAUDE_SIZE=own_bytes=" in result.stdout,
          result.stdout)
    check("Fossil checkout: CI probe is skipped", "CI_PROBE=skip" in result.stdout)
    check("Fossil checkout: the git-based resync is never due",
          "RESYNC=skip reason=not-a-git-repo due=no\n" in result.stdout, result.stdout)
    (repo / ".fslckout").unlink()
    check("no home state beyond the isolated sync fixture",
          list(home.iterdir()) == [home / ".claude"])

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All isolated readup checks passed.")
