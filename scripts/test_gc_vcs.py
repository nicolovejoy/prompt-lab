"""gc-vcs.sh: /handoff's version-control reads, for git and Fossil alike.

Run: python scripts/test_gc_vcs.py

Standalone runner (no pytest in this repo). The Fossil cases run against a fake
`fossil` on PATH, so they are the same on a machine without Fossil (CI has
none). One extra group drives a real Fossil checkout when the binary exists and
prints SKIP when it does not.

What this suite is for: a checkout that cannot be read must exit non-zero. The
bug being fixed recorded an unreadable Fossil checkout as "no commits, clean
tree" in every /handoff (ear-worm, 2026-11-20).
"""
import calendar
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "workflow" / "bin" / "gc-vcs.sh"
IDENT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
failures = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


def run(cwd, *args, env=None):
    r = subprocess.run([str(SCRIPT), *args], cwd=str(cwd), text=True,
                       capture_output=True, env=env or dict(os.environ), timeout=30)
    return r.returncode, r.stdout, r.stderr


def epoch(stamp):
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))


def fake_bin(tmp, name, body):
    d = tmp / f"fakebin-{name}"
    d.mkdir(exist_ok=True)
    f = d / name
    f.write_text("#!/bin/sh\n" + body)
    f.chmod(0o755)
    return d


def fossil_checkout(tmp, name="ear-worm"):
    root = tmp / name
    (root / "Sources").mkdir(parents=True)
    (root / ".fslckout").write_text("")
    return root


def test_git(tmp):
    print("\n1. git checkout")
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    when = "2026-11-20 12:00:00"
    env = {**os.environ, **IDENT,
           "GIT_AUTHOR_DATE": f"{when} +0000", "GIT_COMMITTER_DATE": f"{when} +0000"}
    (repo / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "first | with a pipe"], cwd=repo,
                   check=True, capture_output=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()
    (repo / "new.txt").write_text("n\n")

    check("kind", run(repo, "kind")[:2], (0, "git\n"))
    check("status names the VCS, then the files",
          run(repo, "status")[:2], (0, "VCS=git\n?? new.txt\n"))
    check("commit after the cutoff is listed with its own UTC timestamp",
          run(repo, "commits-since", "2026-11-20 11:00:00")[:2],
          (0, f"{head}|{epoch(when)}|first | with a pipe\n"))
    check("commit before the cutoff is not listed, and that is exit 0",
          run(repo, "commits-since", "2026-11-20 13:00:00")[:2], (0, ""))
    (repo / "web" / "api").mkdir(parents=True)
    check("works from a subdirectory",
          run(repo / "web" / "api", "kind")[:2], (0, "git\n"))

    fresh = tmp / "fresh"
    fresh.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fresh, check=True, capture_output=True)
    check("a repository with no commits yet has no commits, exit 0",
          run(fresh, "commits-since", "2026-11-20 11:00:00")[:2], (0, ""))


def test_none(tmp):
    print("\n2. a directory that is no checkout")
    loose = tmp / "loose"
    loose.mkdir()
    check("kind", run(loose, "kind")[:2], (0, "none\n"))
    check("status", run(loose, "status")[:2], (0, "VCS=none\n"))
    check("commits-since is empty and exit 0",
          run(loose, "commits-since", "2026-11-20 11:00:00")[:2], (0, ""))


def test_usage(tmp):
    print("\n3. arguments")
    loose = tmp / "loose"
    loose.mkdir()
    for bad in ("", "2026-11-20", "2026-11-20T11:00:00Z", "2026-11-20 11:00:00Z",
                "yesterday; rm -rf x"):
        rc, out, err = run(loose, "commits-since", bad)
        check(f"commits-since rejects {bad!r}", (rc, out, "usage" in err), (2, "", True))
    check("unknown subcommand", run(loose, "push")[0], 2)
    check("no subcommand", run(loose)[0], 2)


TIMELINE = """\
14787350f3e96a306f87e832df43df7a77ccd79e0e448a5c09c962a4780a6b80|2026-11-21 02:09:57|initial empty check-in
4ac5718d63f859c7309445d4f8287b909ca864623ff78c249e83f42737386fa4|2026-11-21 02:10:05|first | with a pipe
+++ end of timeline (2) +++
"""


def fossil_env(tmp, body):
    fakebin = fake_bin(tmp, "fossil", body)
    return {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}",
            "FOSSIL_ARGS_LOG": str(tmp / "fossil-args.log")}


def test_fossil_fake(tmp):
    print("\n4. Fossil checkout, fake fossil binary")
    root = fossil_checkout(tmp)
    deep = root / "Sources"
    body = f'''printf '%s\\n' "$*" >> "$FOSSIL_ARGS_LOG"
case "$1" in
  changes) printf 'EXTRA      .hidden\\nEDITED     a.txt\\n' ;;
  timeline) cat <<'EOF'
{TIMELINE}EOF
  ;;
esac
'''
    env = fossil_env(tmp, body)
    check("kind at the root", run(root, "kind", env=env)[:2], (0, "fossil\n"))
    check("kind in a subdirectory", run(deep, "kind", env=env)[:2], (0, "fossil\n"))
    check("status lists edited and untracked files",
          run(deep, "status", env=env)[:2],
          (0, "VCS=fossil\nEXTRA      .hidden\nEDITED     a.txt\n"))
    rc, out, err = run(deep, "commits-since", "2026-11-21 01:59:47", env=env)
    check("commits come out as hash|unix-seconds|subject, trailer dropped",
          (rc, out),
          (0, "14787350f3e96a306f87e832df43df7a77ccd79e0e448a5c09c962a4780a6b80"
              f"|{epoch('2026-11-21 02:09:57')}|initial empty check-in\n"
              "4ac5718d63f859c7309445d4f8287b909ca864623ff78c249e83f42737386fa4"
              f"|{epoch('2026-11-21 02:10:05')}|first | with a pipe\n"))
    log = (tmp / "fossil-args.log").read_text()
    check("status asks for untracked files and dotfiles",
          "changes --differ --dotfiles" in log, True)
    # Fossil's timeline stops at 20 lines unless told otherwise.
    check("timeline is asked for every commit, not the default 20",
          "timeline after 2026-11-21 01:59:47 -n 0 -t ci" in log, True)

    for trailer in ("+++ no more data (0) +++", "--- entry limit (20) reached ---",
                    "+++ end of timeline (0) +++"):
        env = fossil_env(tmp, f"echo '{trailer}'\n")
        check(f"only a trailer ({trailer[:14]}…) is no commits, exit 0",
              run(root, "commits-since", "2026-11-21 01:59:47", env=env)[:2], (0, ""))


def test_fossil_failures(tmp):
    print("\n5. an unreadable Fossil checkout is never 'nothing'")
    root = fossil_checkout(tmp)

    env = fossil_env(tmp, "echo 'not within an open check-out' >&2\nexit 1\n")
    for sub in (("status",), ("commits-since", "2026-11-21 01:59:47")):
        rc, out, err = run(root, *sub, env=env)
        check(f"{sub[0]}: a failing fossil exits 4 with no rows",
              (rc, out, "not within an open check-out" in err), (4, "", True))

    env = fossil_env(tmp, "echo 'a line in some future format'\n")
    rc, out, err = run(root, "commits-since", "2026-11-21 01:59:47", env=env)
    check("a timeline line that cannot be parsed exits 5",
          (rc, "unreadable timeline line" in err), (5, True))

    # No fossil on PATH. /usr/bin:/bin holds git, python3 and the coreutils the
    # script needs on macOS and Linux; skip where it also holds a fossil.
    bare = "/usr/bin:/bin"
    if shutil.which("fossil", path=bare) or not shutil.which("python3", path=bare):
        print("  SKIP missing-fossil case: /usr/bin:/bin is not a fossil-free toolchain here")
    else:
        env = {**os.environ, "PATH": bare}
        check("kind still answers without the binary", run(root, "kind", env=env)[:2],
              (0, "fossil\n"))
        for sub in (("status",), ("commits-since", "2026-11-21 01:59:47")):
            rc, out, err = run(root, *sub, env=env)
            check(f"{sub[0]}: Fossil checkout without fossil exits 3 with no rows",
                  (rc, out, "not installed" in err), (3, "", True))


def test_broken_git(tmp):
    print("\n6. a git that fails for another reason is an error, not 'none'")
    loose = tmp / "loose"
    loose.mkdir()
    fakebin = fake_bin(tmp, "git", "echo 'xcode license not accepted' >&2\nexit 69\n")
    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"}
    for sub in (("kind",), ("status",), ("commits-since", "2026-11-21 01:59:47")):
        rc, out, err = run(loose, *sub, env=env)
        check(f"{sub[0]} exits 2 with no answer", (rc, out), (2, ""))


def test_damaged_git_and_partial_install(tmp):
    print("\n8. a damaged repository or a partial install is an error, not 'none'")
    repo = tmp / "damaged"
    (repo / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".git" / "HEAD").unlink()
    for sub in (("kind",), ("status",), ("commits-since", "2026-11-21 01:59:47")):
        rc, out, err = run(repo / "src", *sub)
        check(f"{sub[0]}: git exit 128 under a .git entry exits 2 with no answer",
              (rc, out, ".git entry" in err), (2, "", True))

    # A branch ref emptied by a crash mid-write: git still sees a work tree, but
    # the history cannot be read. That is not "no commits yet".
    broken = tmp / "broken-ref"
    broken.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=broken, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "one"], cwd=broken,
                   check=True, capture_output=True, env={**os.environ, **IDENT})
    branch = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=broken,
                            capture_output=True, text=True, check=True).stdout.strip()
    (broken / ".git" / "refs" / "heads" / branch).write_text("")
    check("the emptied ref still looks like a git checkout", run(broken, "kind")[:2], (0, "git\n"))
    rc, out, err = run(broken, "commits-since", "2026-11-20 11:00:00")
    check("commits-since on a corrupt branch ref exits 4 with no rows",
          (rc, out, "git log failed" in err), (4, "", True))

    # gc-vcs.sh copied alone, as a stale ~/.claude/bin would hold it.
    alone = tmp / "bin"
    alone.mkdir()
    shutil.copy(SCRIPT, alone / "gc-vcs.sh")
    root = fossil_checkout(tmp)
    for sub in (("kind",), ("status",), ("commits-since", "2026-11-21 01:59:47")):
        r = subprocess.run([str(alone / "gc-vcs.sh"), *sub], cwd=str(root), text=True,
                           capture_output=True, timeout=30)
        check(f"{sub[0]}: without _gc_project.sh beside it exits 2 with no answer",
              (r.returncode, r.stdout, "_gc_project.sh" in r.stderr), (2, "", True))


def test_fossil_live(tmp):
    print("\n7. a real Fossil checkout")
    if not shutil.which("fossil"):
        print("  SKIP fossil is not installed")
        return
    env = {**os.environ, "HOME": str(tmp / "home"), "USER": "probe"}
    (tmp / "home").mkdir()
    co = tmp / "live"
    co.mkdir()

    def fossil(*args):
        subprocess.run(["fossil", *args], cwd=co, check=True, capture_output=True, env=env)

    before = int(time.time()) - 5
    subprocess.run(["fossil", "init", "--admin-user", "probe", str(tmp / "live.fossil")],
                   check=True, capture_output=True, env=env)
    fossil("open", str(tmp / "live.fossil"))
    (co / "a.txt").write_text("a\n")
    fossil("add", "a.txt")
    fossil("commit", "-m", "first | with a pipe", "--user", "probe", "--no-warnings")
    (co / "a.txt").write_text("a\nb\n")
    (co / ".hidden").write_text("h\n")

    check("kind", run(co, "kind", env=env)[:2], (0, "fossil\n"))
    rc, out, err = run(co, "status", env=env)
    lines = out.splitlines()
    check("status exits 0 and names the VCS", (rc, lines[:1]), (0, ["VCS=fossil"]))
    check("status lists the edit", any(ln.startswith("EDITED") and ln.endswith("a.txt") for ln in lines), True)
    check("status lists the untracked dotfile", any(ln.startswith("EXTRA") and ln.endswith(".hidden") for ln in lines), True)

    since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(before))
    rc, out, err = run(co, "commits-since", since, env=env)
    rows = [ln.split("|", 2) for ln in out.splitlines()]
    check("commits-since exits 0", rc, 0)
    check("the real commit is listed", [r[2] for r in rows if len(r) == 3][-1:], ["first | with a pipe"])
    check("hashes are 64 hex characters", all(len(r[0]) == 64 for r in rows), True)
    # The session clock and Fossil's must agree on UTC: a local-time reading
    # would be hours away from now.
    check("timestamps are UTC seconds, within a minute of now",
          all(abs(int(r[1]) - time.time()) < 60 for r in rows), True)
    later = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 3600))
    check("a cutoff an hour ahead lists nothing",
          run(co, "commits-since", later, env=env)[:2], (0, ""))


def main():
    for t in (test_git, test_none, test_usage, test_fossil_fake, test_fossil_failures,
              test_broken_git, test_fossil_live, test_damaged_git_and_partial_install):
        with tempfile.TemporaryDirectory(prefix="gc-vcs-") as d:
            t(Path(d).resolve())
    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + ", ".join(failures))
        return 1
    print("All gc-vcs tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
