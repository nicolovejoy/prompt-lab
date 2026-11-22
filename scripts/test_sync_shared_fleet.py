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
    check("an unreadable repository is not 'no git repositories found'",
          "no git repositories found" not in alone.stderr, alone.stderr)

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
          and "no git repositories found" in nothing.stderr,
          nothing.stdout + nothing.stderr)

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All shared-fleet checks passed.")
