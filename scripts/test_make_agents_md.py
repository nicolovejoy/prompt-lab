"""
scripts/test_make_agents_md.py — make-agents-md.sh writes the pointer form of
AGENTS.md, never overwrites a real one, and replaces a Codex-importer copy only
when asked and only when git does not track it.

Standalone runner (no pytest in this repo).
"""
import os
import subprocess
import sys
import tempfile

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow", "bin", "make-agents-md.sh")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


IMPORTER_COPY = (
    "# AGENTS.md\n\n"
    "This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.\n\n"
    "See ~/.Codex/plans for plans.\n"
)

with tempfile.TemporaryDirectory() as tmp:
    canonical = os.path.join(tmp, "shared-source.md")
    with open(canonical, "w") as f:
        f.write("## Shared conventions\n\n- Rule one\n")
    backups = os.path.join(tmp, "backups")
    env = {
        **os.environ,
        "CLAUDE_MD_SHARED": canonical,
        "AGENTS_MD_BACKUP_DIR": backups,
    }

    def run(*args):
        return subprocess.run([SCRIPT, *args], env=env, capture_output=True, text=True)

    def repo(name, claude=True, git=False):
        d = os.path.join(tmp, name)
        os.makedirs(d)
        if claude:
            with open(os.path.join(d, "CLAUDE.md"), "w") as f:
                f.write("# Project\n")
        if git:
            subprocess.run(["git", "init", "-q", d], check=True)
        return d

    # Absent → created in pointer form, with a block sync-shared-md calls in sync.
    d = repo("fresh")
    r = run(d)
    agents = os.path.join(d, "AGENTS.md")
    check("absent AGENTS.md is created", r.returncode == 0 and os.path.exists(agents), r.stderr)
    content = open(agents).read()
    check("created file points at CLAUDE.md", "Read CLAUDE.md in this repo first" in content)
    check("created file explains provenance", "make-agents-md.sh" in content and "import from Claude Code" in content)
    check("created file carries the shared block", "SHARED-CONVENTIONS:BEGIN" in content and "Rule one" in content)
    sync = subprocess.run(
        [os.path.join(REPO_DIR, "workflow", "bin", "sync-shared-md.sh"), "--check", agents],
        env=env, capture_output=True, text=True,
    )
    check("created block checks in sync", sync.returncode == 0, sync.stdout)
    check("created file is not itself an importer copy", "Codex.ai/code" not in content and "~/.Codex/" not in content)

    # Existing real AGENTS.md → untouched, exit 3.
    d = repo("existing")
    with open(os.path.join(d, "AGENTS.md"), "w") as f:
        f.write("hand written\n")
    r = run(d)
    check("existing AGENTS.md exits 3", r.returncode == 3, r.stderr)
    check("existing AGENTS.md is untouched", open(os.path.join(d, "AGENTS.md")).read() == "hand written\n")
    r = run("--replace-importer-copy", d)
    check("replace flag leaves a non-importer file alone", r.returncode == 3 and open(os.path.join(d, "AGENTS.md")).read() == "hand written\n")

    # No CLAUDE.md → nothing written, exit 2.
    d = repo("no-claude", claude=False)
    r = run(d)
    check("missing CLAUDE.md exits 2", r.returncode == 2)
    check("missing CLAUDE.md writes nothing", not os.path.exists(os.path.join(d, "AGENTS.md")))

    # CLAUDE.md under .claude/ (home-assistant's layout) → pointer names that path.
    d = repo("dot-claude", claude=False)
    os.makedirs(os.path.join(d, ".claude"))
    with open(os.path.join(d, ".claude", "CLAUDE.md"), "w") as f:
        f.write("# Project\n")
    r = run(d)
    content = open(os.path.join(d, "AGENTS.md")).read() if r.returncode == 0 else ""
    check(".claude/CLAUDE.md is found", r.returncode == 0, r.stderr)
    check(".claude/CLAUDE.md pointer names its path", "Read .claude/CLAUDE.md in this repo first" in content)

    # Importer copy without the flag → left alone.
    d = repo("importer", git=True)
    with open(os.path.join(d, "AGENTS.md"), "w") as f:
        f.write(IMPORTER_COPY)
    r = run(d)
    check("importer copy needs the explicit flag", r.returncode == 3 and open(os.path.join(d, "AGENTS.md")).read() == IMPORTER_COPY)

    # Untracked importer copy with the flag → backed up and replaced.
    r = run("--replace-importer-copy", d)
    check("untracked importer copy is replaced", r.returncode == 0 and "Read CLAUDE.md" in open(os.path.join(d, "AGENTS.md")).read(), r.stderr)
    saved = os.listdir(backups) if os.path.isdir(backups) else []
    check("importer copy is backed up first", len(saved) == 1 and open(os.path.join(backups, saved[0])).read() == IMPORTER_COPY)

    # Tracked importer copy → refused, exit 4.
    d = repo("tracked", git=True)
    with open(os.path.join(d, "AGENTS.md"), "w") as f:
        f.write(IMPORTER_COPY)
    subprocess.run(["git", "-C", d, "add", "AGENTS.md"], check=True)
    r = run("--replace-importer-copy", d)
    check("tracked importer copy is refused", r.returncode == 4 and open(os.path.join(d, "AGENTS.md")).read() == IMPORTER_COPY, r.stderr)

    # Sync failure → no half-written file.
    d = repo("syncfail")
    r = subprocess.run([SCRIPT, d], env={**env, "SYNC_SHARED_MD": "/usr/bin/false"}, capture_output=True, text=True)
    check("sync failure exits 5", r.returncode == 5)
    check("sync failure leaves no partial file", not os.path.exists(os.path.join(d, "AGENTS.md")))

print(f"\n{len(failures)} failure(s)" if failures else "\nall passed")
sys.exit(1 if failures else 0)
