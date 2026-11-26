"""Isolated tests for the shared-conventions fleet inventory/updater."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FLEET = ROOT / "workflow/bin/sync-shared-fleet.sh"
SYNC = ROOT / "workflow/bin/sync-shared-md.sh"
failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)
        print(detail)


with tempfile.TemporaryDirectory(prefix="shared-fleet-") as tmp:
    base = Path(tmp)
    fleet_root = base / "src"
    fleet_root.mkdir()
    canonical = base / "canonical.md"
    canonical.write_text("## Shared conventions\n\n- Original rule\n")
    env = dict(
        os.environ,
        CLAUDE_MD_SHARED=str(canonical),
        SHARED_FLEET_ROOT=str(fleet_root),
        SYNC_SHARED_MD=str(SYNC),
    )

    def repo(name):
        path = fleet_root / name
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        return path

    current = repo("current")
    behind = repo("behind")
    missing = repo("missing")
    tampered = repo("tampered")
    absent = repo("absent")

    for path in (current, behind, tampered):
        (path / "CLAUDE.md").write_text(f"# {path.name}\n")
        subprocess.run([str(SYNC), "--apply", str(path / "CLAUDE.md")],
                       env=env, check=True, capture_output=True, text=True)
    (missing / "CLAUDE.md").write_text("# Missing block\n")
    leftover_agents = "Read CLAUDE.md first.\n"
    (behind / "AGENTS.md").write_text(leftover_agents)

    # A repository git cannot read: a .git entry pointing at a record that is
    # gone, as a pruned linked worktree leaves behind. It must be reported,
    # never skipped like a plain directory.
    damaged = fleet_root / "damaged"
    damaged.mkdir()
    (damaged / ".git").write_text("gitdir: /nonexistent/.git/worktrees/damaged\n")
    damaged_text = "# Damaged, no block\n"
    (damaged / "CLAUDE.md").write_text(damaged_text)
    # Fossil checkouts: only the marker file, no fossil binary involved.
    fossil_behind = fleet_root / "fossil-behind"
    fossil_missing = fleet_root / "fossil-missing"
    fossil_absent = fleet_root / "fossil-absent"
    fossil_old = fleet_root / "fossil-old"
    for path, marker in ((fossil_behind, ".fslckout"), (fossil_missing, ".fslckout"),
                         (fossil_absent, ".fslckout"), (fossil_old, "_FOSSIL_")):
        path.mkdir()
        (path / marker).write_text("")
    (fossil_behind / "CLAUDE.md").write_text("# fossil-behind\n")
    subprocess.run([str(SYNC), "--apply", str(fossil_behind / "CLAUDE.md")],
                   env=env, check=True, capture_output=True, text=True)
    (fossil_missing / "CLAUDE.md").write_text("# Fossil, no block\n")
    (fossil_old / "CLAUDE.md").write_text("# Old-style marker\n")
    # A marker only counts if it is a file, as in _gc_project.sh.
    fossil_dir_marker = fleet_root / "fossil-dir-marker"
    (fossil_dir_marker / ".fslckout").mkdir(parents=True)
    # A fossil that is called would leave this sentinel behind.
    fake_fossil_bin = base / "fossil-bin"
    fake_fossil_bin.mkdir()
    sentinel = base / "fossil-was-called"
    fake_fossil = fake_fossil_bin / "fossil"
    fake_fossil.write_text(f"#!/bin/sh\ntouch {sentinel}\nexit 99\n")
    fake_fossil.chmod(0o755)
    env = dict(env, PATH=f"{fake_fossil_bin}:{env['PATH']}")
    plain = fleet_root / "plain-directory"
    plain.mkdir()
    (plain / "CLAUDE.md").write_text("# Not a repository\n")

    canonical.write_text("## Shared conventions\n\n- New canonical rule\n")
    subprocess.run([str(SYNC), "--apply", str(current / "CLAUDE.md")],
                   env=env, check=True, capture_output=True, text=True)
    tampered_file = tampered / "CLAUDE.md"
    tampered_text = tampered_file.read_text().replace("Original rule", "Local edit")
    tampered_file.write_text(tampered_text)

    before = {path: path.read_bytes() for path in fleet_root.glob("*/*.md")}
    audit = subprocess.run([str(FLEET)], env=env, capture_output=True, text=True)
    after = {path: path.read_bytes() for path in fleet_root.glob("*/*.md")}
    check("dry-run reports current", "current\tCLAUDE.md\tcurrent" in audit.stdout)
    check("dry-run reports behind", "behind\tCLAUDE.md\tbehind" in audit.stdout)
    check("dry-run reports missing", "missing\tCLAUDE.md\tmissing" in audit.stdout)
    check("dry-run reports tampered", "tampered\tCLAUDE.md\ttampered" in audit.stdout)
    check("dry-run reports absent", "absent\tCLAUDE.md\tabsent" in audit.stdout)
    check("tampered audit exits nonzero", audit.returncode == 1, audit.stdout)
    check("dry-run reports a repository git cannot read",
          "damaged\tCLAUDE.md\tunreadable: git exit 128" in audit.stdout, audit.stdout)
    check("a plain directory is still left out",
          "plain-directory" not in audit.stdout, audit.stdout)
    check("dry-run reports a Fossil checkout with an old block as behind, tagged fossil",
          "fossil-behind\tCLAUDE.md\tbehind\tfossil\n" in audit.stdout, audit.stdout)
    check("dry-run reports a Fossil checkout with no block as missing",
          "fossil-missing\tCLAUDE.md\tmissing\tfossil\n" in audit.stdout, audit.stdout)
    check("dry-run reports a Fossil checkout with no CLAUDE.md as absent, not skipped",
          "fossil-absent\tCLAUDE.md\tabsent\tfossil\n" in audit.stdout, audit.stdout)
    check("the older _FOSSIL_ marker counts",
          "fossil-old\tCLAUDE.md\tmissing\tfossil\n" in audit.stdout, audit.stdout)
    check("a directory named like a marker is not a Fossil checkout",
          "fossil-dir-marker" not in audit.stdout, audit.stdout)
    check("git members carry no fossil tag",
          "current\tCLAUDE.md\tcurrent\n" in audit.stdout
          and "behind\tCLAUDE.md\tbehind\n" in audit.stdout, audit.stdout)
    check("dry-run changes no files", before == after)

    applied = subprocess.run([str(FLEET), "--apply"], env=env,
                             capture_output=True, text=True)
    check("apply updates verified behind block",
          "behind\tCLAUDE.md\tbehind -> updated" in applied.stdout)
    check("apply adds block to existing missing file",
          "missing\tCLAUDE.md\tmissing -> updated" in applied.stdout)
    check("apply leaves tampered block untouched", tampered_file.read_text() == tampered_text)
    check("apply ignores a leftover AGENTS.md",
          "AGENTS.md" not in applied.stdout + audit.stdout
          and (behind / "AGENTS.md").read_text() == leftover_agents)
    check("apply does not create absent files", not (absent / "CLAUDE.md").exists())
    check("apply updates a Fossil checkout's behind block",
          "fossil-behind\tCLAUDE.md\tbehind -> updated\tfossil\n" in applied.stdout, applied.stdout)
    check("apply adds a block to a Fossil checkout's existing file",
          "fossil-missing\tCLAUDE.md\tmissing -> updated\tfossil\n" in applied.stdout, applied.stdout)
    check("apply does not create a Fossil checkout's absent file",
          not (fossil_absent / "CLAUDE.md").exists()
          and "fossil-absent\tCLAUDE.md\tabsent\tfossil\n" in applied.stdout, applied.stdout)
    fossil_checks = [subprocess.run([str(SYNC), "--check", str(path / "CLAUDE.md")],
                                    env=env, capture_output=True, text=True)
                     for path in (fossil_behind, fossil_missing, fossil_old)]
    check("apply updates the _FOSSIL_ checkout's file too",
          "fossil-old\tCLAUDE.md\tmissing -> updated\tfossil\n" in applied.stdout, applied.stdout)
    check("every Fossil checkout's applied block is current by --check",
          all(c.returncode == 0 for c in fossil_checks),
          str([c.stdout + c.stderr for c in fossil_checks]))
    check("Fossil handling never runs the fossil command", not sentinel.exists())
    check("apply reports the unreadable repository and leaves its file alone",
          "damaged\tCLAUDE.md\tunreadable: git exit 128" in applied.stdout
          and (damaged / "CLAUDE.md").read_text() == damaged_text, applied.stdout)
    check("apply with an unreadable repository exits nonzero",
          applied.returncode == 1, applied.stdout)
    check("apply makes no commits",
          all(not (path / ".git/refs/heads/main").exists() and
              not (path / ".git/refs/heads/master").exists()
              for path in (current, behind, missing, tampered, absent)))

    behind_check = subprocess.run([str(SYNC), "--check", str(behind / "CLAUDE.md")],
                                  env=env, capture_output=True, text=True)
    missing_check = subprocess.run([str(SYNC), "--check", str(missing / "CLAUDE.md")],
                                   env=env, capture_output=True, text=True)
    check("updated behind block is current", behind_check.returncode == 0)
    check("updated missing block is current", missing_check.returncode == 0)

with tempfile.TemporaryDirectory(prefix="shared-fleet-lone-") as tmp:
    base = Path(tmp)
    fleet_root = base / "src"
    lone = fleet_root / "lone"
    lone.mkdir(parents=True)
    (lone / ".git").write_text("gitdir: /nonexistent/.git/worktrees/lone\n")
    canonical = base / "canonical.md"
    canonical.write_text("## Shared conventions\n\n- Original rule\n")
    env = dict(os.environ, CLAUDE_MD_SHARED=str(canonical),
               SHARED_FLEET_ROOT=str(fleet_root), SYNC_SHARED_MD=str(SYNC))
    empty = subprocess.run([str(FLEET), "--check", str(base / "bin-less")],
                           env=env, capture_output=True, text=True)
    check("a missing root exits 2", empty.returncode == 2, empty.stderr)
    (fleet_root / "notes").mkdir()
    dangling = fleet_root / "dangling"
    dangling.mkdir()
    (dangling / ".git").symlink_to(base / "gone" / ".git")
    alone = subprocess.run([str(FLEET)], env=env, capture_output=True, text=True)
    check("a .git that is a dangling symlink is reported, not skipped",
          "dangling\tCLAUDE.md\tunreadable: git exit 128" in alone.stdout,
          alone.stdout + alone.stderr)
    check("an unreadable repository alone exits nonzero",
          alone.returncode == 1 and "lone\tCLAUDE.md\tunreadable" in alone.stdout,
          alone.stdout + alone.stderr)
    check("an unreadable repository is not an empty inventory",
          "checkouts found" not in alone.stderr, alone.stderr)

    # git itself failing (missing, or the Xcode license prompt) must not read
    # as an empty fleet either: every directory holding a .git is reported.
    fake_bin = base / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\necho 'git: broken for this test' >&2\n"
                        "echo 'second line' >&2\nexit 69\n")
    fake_git.chmod(0o755)
    broken_env = dict(env, PATH=f"{fake_bin}:{env['PATH']}")
    broken = subprocess.run([str(FLEET)], env=broken_env, capture_output=True, text=True)
    check("a failing git reports the repository with git's own words",
          broken.returncode == 1
          and "lone\tCLAUDE.md\tunreadable: git exit 69: git: broken for this test\n"
          in broken.stdout and "second line" not in broken.stdout,
          broken.stdout + broken.stderr)

with tempfile.TemporaryDirectory(prefix="shared-fleet-empty-") as tmp:
    fleet_root = Path(tmp) / "src"
    (fleet_root / "notes").mkdir(parents=True)
    env = dict(os.environ, SHARED_FLEET_ROOT=str(fleet_root), SYNC_SHARED_MD=str(SYNC))
    nothing = subprocess.run([str(FLEET)], env=env, capture_output=True, text=True)
    check("a root with no repositories exits nonzero and says so",
          nothing.returncode == 1 and nothing.stdout == ""
          and "no git or Fossil checkouts found" in nothing.stderr,
          nothing.stdout + nothing.stderr)

with tempfile.TemporaryDirectory(prefix="shared-fleet-fossil-") as tmp:
    base = Path(tmp)
    fleet_root = base / "src"
    canonical = base / "canonical.md"
    canonical.write_text("## Shared conventions\n\n- Original rule\n")
    env = dict(os.environ, CLAUDE_MD_SHARED=str(canonical),
               SHARED_FLEET_ROOT=str(fleet_root), SYNC_SHARED_MD=str(SYNC))
    # A root holding only a Fossil checkout is a real fleet, not an empty one.
    only = fleet_root / "only-fossil"
    only.mkdir(parents=True)
    (only / ".fslckout").write_text("")
    solo = subprocess.run([str(FLEET)], env=env, capture_output=True, text=True)
    check("a root holding only a Fossil checkout is not an empty inventory",
          solo.returncode == 0 and "only-fossil\tCLAUDE.md\tabsent\tfossil\n" in solo.stdout
          and "checkouts found" not in solo.stderr, solo.stdout + solo.stderr)

    # A .git entry git cannot read wins over a Fossil marker beside it:
    # report it unreadable and fail, as gc-vcs.sh does.
    both = fleet_root / "both"
    both.mkdir()
    (both / ".fslckout").write_text("")
    (both / ".git").write_text("gitdir: /nonexistent/.git/worktrees/both\n")
    mixed = subprocess.run([str(FLEET)], env=env, capture_output=True, text=True)
    check("an unreadable .git beside a Fossil marker is reported unreadable",
          mixed.returncode == 1
          and "both\tCLAUDE.md\tunreadable: git exit 128" in mixed.stdout
          and not [ln for ln in mixed.stdout.splitlines()
                   if ln.startswith("both\t")][0].endswith("\tfossil"),
          mixed.stdout + mixed.stderr)

    # Without git on PATH (rc 127) a Fossil checkout is still listed.
    nogit_bin = base / "nogit-bin"
    nogit_bin.mkdir()
    fake_git = nogit_bin / "git"
    fake_git.write_text("#!/bin/sh\nexit 69\n")
    fake_git.chmod(0o755)
    nogit = subprocess.run([str(FLEET)], env=dict(env, PATH=f"{nogit_bin}:{env['PATH']}"),
                           capture_output=True, text=True)
    check("a Fossil checkout is listed even when git itself is failing",
          "only-fossil\tCLAUDE.md\tabsent\tfossil\n" in nogit.stdout, nogit.stdout + nogit.stderr)

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All shared-fleet checks passed.")
