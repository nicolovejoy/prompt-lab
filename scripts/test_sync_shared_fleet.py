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
    (current / "AGENTS.md").write_text("Read CLAUDE.md first.\n")
    subprocess.run([str(SYNC), "--apply", str(current / "AGENTS.md")],
                   env=env, check=True, capture_output=True, text=True)

    canonical.write_text("## Shared conventions\n\n- New canonical rule\n")
    subprocess.run([str(SYNC), "--apply", str(current / "CLAUDE.md")],
                   env=env, check=True, capture_output=True, text=True)
    subprocess.run([str(SYNC), "--apply", str(current / "AGENTS.md")],
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
    check("dry-run changes no files", before == after)

    applied = subprocess.run([str(FLEET), "--apply"], env=env,
                             capture_output=True, text=True)
    check("apply updates verified behind block",
          "behind\tCLAUDE.md\tbehind -> updated" in applied.stdout)
    check("apply adds block to existing missing file",
          "missing\tCLAUDE.md\tmissing -> updated" in applied.stdout)
    check("apply leaves tampered block untouched", tampered_file.read_text() == tampered_text)
    check("apply does not create absent files", not (absent / "CLAUDE.md").exists())
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

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All shared-fleet checks passed.")
