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
    for key in ("REMOTE=", "RESYNC=", "CONVENTIONS_CLAUDE=", "CONVENTIONS_AGENTS=",
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
    outside = probe(FAKE_OUTSIDE="1")
    check("outside repo skips CI and public audit",
          "CI_PROBE=skip" in outside and "PUBLIC_DRIFT=skip" in outside)
    check("no real home state created", list(home.iterdir()) == [])

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All isolated readup checks passed.")
