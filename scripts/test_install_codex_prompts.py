"""
scripts/test_install_codex_prompts.py — verify install.sh's Codex prompt and
user-skill distribution steps and their frontmatter transforms.

Does NOT run install.sh (it writes into the real $HOME and loads a real
launchd job — see plan Global Constraints). Instead: (1) a structural check
that install.sh contains the expected loop, and (2) a functional check of
the exact transform (grep -v '^allowed-tools:') against every real command
file, run directly, plus (3) the real distribution block against a temporary
destination — no filesystem writes outside a temp dir.

Standalone runner (no pytest in this repo).
"""
import subprocess
import glob
import os
import sys
import tempfile

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


# 1. Structural: retain legacy prompts, install current explicit-only skills,
#    and install a narrow rule for the out-of-workspace session helper.
with open(os.path.join(REPO_DIR, "workflow", "install.sh")) as f:
    install_src = f.read()

check(
    "install.sh references $HOME/.codex/prompts",
    ".codex/prompts" in install_src,
)
check(
    "install.sh strips allowed-tools when writing Codex prompts",
    "allowed-tools" in install_src and "grep -v" in install_src,
)
check(
    "install.sh references $HOME/.agents/skills",
    ".agents/skills" in install_src,
)
check(
    "installed Codex skills are explicit-only",
    "allow_implicit_invocation: false" in install_src,
)
check(
    "install.sh installs a separate Codex session rule",
    "prompt-lab-session.rules" in install_src
    and "workflow/codex-session.rules.tpl" in install_src,
)

# 2. Functional: the transform must drop exactly the allowed-tools line (when
#    present) and nothing else, for every real command file.
command_files = sorted(glob.glob(os.path.join(REPO_DIR, "workflow", "commands", "*.md")))
check("found command files to test", len(command_files) > 0, f"found {len(command_files)}")

for path in command_files:
    name = os.path.basename(path)
    with open(path) as f:
        original_lines = f.readlines()

    result = subprocess.run(
        ["grep", "-v", "^allowed-tools:", path], capture_output=True, text=True
    )
    transformed_lines = result.stdout.splitlines(keepends=True)

    had_allowed_tools = any(line.startswith("allowed-tools:") for line in original_lines)
    # Informational only — not every command file is required to have an
    # allowed-tools line. The transform's actual contract (per install.sh's own
    # comment) is "drop the line when present", not "every file has one".
    print(f"[INFO] {name}: has an allowed-tools line to strip = {had_allowed_tools}")
    expected_removed = 1 if had_allowed_tools else 0
    check(
        f"{name}: transform removes exactly {expected_removed} line(s)",
        len(original_lines) - len(transformed_lines) == expected_removed,
        f"{len(original_lines)} -> {len(transformed_lines)}",
    )
    check(
        f"{name}: transform leaves no allowed-tools line behind",
        not any(line.startswith("allowed-tools:") for line in transformed_lines),
    )
    check(
        f"{name}: transform preserves the name: line",
        any(line.startswith("name:") for line in transformed_lines),
    )
    check(
        f"{name}: transform preserves the description: line",
        any(line.startswith("description:") for line in transformed_lines),
    )

# Run the real legacy-prompt distribution block against a disposable destination.
# This catches wrong installation layouts that the frontmatter-only checks above
# cannot.
block = install_src.split('# --- Codex custom prompts', 1)[1].split(
    '# --- Codex user skills', 1
)[0]
block = '# --- Codex custom prompts' + block
block = block.replace('CODEX_PROMPTS_DIR="$HOME/.codex/prompts"',
                      'CODEX_PROMPTS_DIR="$CODEX_TEST_DEST"')
with tempfile.TemporaryDirectory(prefix='codex-prompt-install-') as dest:
    env = dict(os.environ, REPO_DIR=REPO_DIR, CODEX_TEST_DEST=dest)
    run = subprocess.run(
        ['bash', '-e', '-c', 'install_file() { cp "$1" "$2"; }\n' + block],
        env=env, capture_output=True, text=True)
    check('real Codex distribution block succeeds', run.returncode == 0, run.stderr)
    check('installed prompts are top-level Markdown files',
          sorted(os.listdir(dest)) == sorted(os.path.basename(p) for p in command_files))
    for path in command_files:
        target = os.path.join(dest, os.path.basename(path))
        with open(path) as f:
            expected = ''.join(line for line in f if not line.startswith('allowed-tools:'))
        actual = None
        if os.path.isfile(target):
            with open(target) as f:
                actual = f.read()
        check(f'{os.path.basename(path)}: installed body matches source transform',
              actual == expected)

# Run the real skill distribution block too. The skill renderer must preserve the
# canonical command body and paths, changing only the frontmatter name and removing
# Claude's allowed-tools line. Codex's automatic Claude importer rewrote both and
# produced unusable ~/.Codex/bin paths; this test pins the narrower transform.
skill_block = install_src.split('# --- Codex user skills', 1)[1].split(
    '# --- Codex session-bookkeeping rule', 1
)[0]
skill_block = '# --- Codex user skills' + skill_block
skill_block = skill_block.replace(
    'CODEX_SKILLS_DIR="$HOME/.agents/skills"',
    'CODEX_SKILLS_DIR="$CODEX_TEST_DEST"',
)
with tempfile.TemporaryDirectory(prefix='codex-skill-install-') as dest:
    env = dict(os.environ, REPO_DIR=REPO_DIR, CODEX_TEST_DEST=dest)
    run = subprocess.run(
        ['bash', '-e', '-c', 'install_file() { cp "$1" "$2"; }\n' + skill_block],
        env=env, capture_output=True, text=True)
    check('real Codex skill distribution block succeeds', run.returncode == 0, run.stderr)

    expected_dirs = sorted(
        f"source-command-{os.path.splitext(os.path.basename(path))[0]}"
        for path in command_files
    )
    check('installed skills use source-command-* directories',
          sorted(os.listdir(dest)) == expected_dirs)

    for path in command_files:
        command_name = os.path.splitext(os.path.basename(path))[0]
        skill_name = f"source-command-{command_name}"
        skill_dir = os.path.join(dest, skill_name)
        skill_path = os.path.join(skill_dir, 'SKILL.md')
        policy_path = os.path.join(skill_dir, 'agents', 'openai.yaml')

        with open(path) as f:
            expected_lines = []
            in_frontmatter = False
            for line_number, line in enumerate(f, start=1):
                if line_number == 1 and line.rstrip('\n') == '---':
                    in_frontmatter = True
                    expected_lines.append(line)
                elif in_frontmatter and line.rstrip('\n') == '---':
                    in_frontmatter = False
                    expected_lines.append(line)
                elif in_frontmatter and line.startswith('allowed-tools:'):
                    continue
                elif in_frontmatter and line.startswith('name:'):
                    expected_lines.append(f'name: "{skill_name}"\n')
                else:
                    expected_lines.append(line)
        expected = ''.join(expected_lines)

        actual = None
        if os.path.isfile(skill_path):
            with open(skill_path) as f:
                actual = f.read()
        check(f'{skill_name}: installed body matches narrow source transform',
              actual == expected)

        policy = None
        if os.path.isfile(policy_path):
            with open(policy_path) as f:
                policy = f.read()
        check(f'{skill_name}: explicit-only policy installed',
              policy == 'policy:\n  allow_implicit_invocation: false\n')

# Run the real Codex-rule distribution block against a disposable destination.
rules_block = install_src.split('# --- Codex session-bookkeeping rule', 1)[1].split(
    '# --- bin scripts', 1
)[0]
rules_block = '# --- Codex session-bookkeeping rule' + rules_block
rules_block = rules_block.replace(
    'CODEX_RULES_DIR="$HOME/.codex/rules"',
    'CODEX_RULES_DIR="$CODEX_TEST_DEST"',
)
with tempfile.TemporaryDirectory(prefix='codex-rule-install-') as dest:
    fake_home = os.path.join(dest, 'home')
    rules_dest = os.path.join(dest, 'rules')
    os.makedirs(fake_home)
    env = dict(
        os.environ,
        REPO_DIR=REPO_DIR,
        CODEX_TEST_DEST=rules_dest,
        BIN_DIR=os.path.join(fake_home, '.claude', 'bin'),
    )
    run = subprocess.run(
        ['bash', '-e', '-c', 'install_file() { cp "$1" "$2"; }\n' + rules_block],
        env=env, capture_output=True, text=True)
    check('real Codex rule distribution block succeeds', run.returncode == 0, run.stderr)
    rule_path = os.path.join(rules_dest, 'prompt-lab-session.rules')
    rule = open(rule_path).read() if os.path.isfile(rule_path) else ''
    expected_helper = os.path.join(fake_home, '.claude', 'bin', 'gc-write.sh')
    check('installed rule resolves the absolute helper path',
          expected_helper in rule and '__GC_WRITE_PATH__' not in rule)
    check('installed rule allows only reviewed gc-write subcommands',
          '"register-session", "update-session-summary", "end-session", "save-daily-summary"' in rule)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
