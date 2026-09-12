# Dual-Agent Commands (Claude Code + Codex CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/readup`, `/handoff`, and the rest of `workflow/commands/*` usable from Codex CLI (via `~/.codex/prompts/`) as well as Claude Code, from a single canonical source per command, with prompt-lab hosting the shared tooling the same way it already does for CLAUDE.md's shared-conventions block.

**Architecture:** `workflow/commands/*.md` stays the single source of truth. `workflow/install.sh` distributes each file to `~/.claude/commands/` unchanged and to `~/.codex/prompts/` with the Claude-only `allowed-tools:` frontmatter line stripped. A new `workflow/bin/session-context.sh` extracts the plain-text context-gathering logic out of the Claude-only `session-start.sh` hook so `/readup` can call it directly on agents with no hook (Codex). `workflow/bin/sync-claude-md.sh` is renamed to `sync-shared-md.sh` (it was already target-path-agnostic) so it can materialize the shared-conventions block into either `CLAUDE.md` or `AGENTS.md`. A `codex/<desc>` branch-naming convention, added to the shared-conventions source, gives Claude sessions a way to detect that Codex touched a repo despite `ListAgents` not seeing across tool types.

**Tech Stack:** Bash (`set -euo pipefail` style, matching existing `workflow/bin/*` scripts), Python 3 standalone test scripts (this repo does not use pytest — see Global Constraints), sqlite3.

**Spec:** `docs/superpowers/specs/2026-09-12-dual-agent-commands-design.md`

## Global Constraints

- Tests are standalone runners, not pytest: each new `scripts/test_*.py` must be runnable directly (`.venv/bin/python scripts/test_whatever.py`) and print pass/fail, matching the style of existing files in `scripts/test_*.py`.
- Never run `workflow/install.sh` for real against the implementer's actual `$HOME` during automated task execution — it writes into `~/.claude/`, `~/.codex/`, `~/Library/LaunchAgents/`, and `~/.zshrc`, and loads a real launchd job. Any verification of `install.sh` changes must be either a structural check (grep/awk against the script's own source) or an isolated snippet test that never invokes the script itself. Running the real script is a manual step for Nico, called out explicitly where it applies.
- Bash scripts under `workflow/bin/` follow the existing house style: `set -euo pipefail`, a comment block at the top explaining *why*, `$HOME`-relative paths (never hardcoded absolute paths outside `$HOME`).
- No database schema changes. `daily_summaries.model` already exists and already takes free-text values (`'claude-code'` today) — reuse it for `'codex'`.
- Preserve every existing behavior for Claude Code sessions. This is an additive port, not a rewrite: a Claude session running `/readup`/`/handoff`/etc. after this plan lands must see identical behavior to before, except where a task explicitly changes shared behavior (e.g. the renamed sync script, the new branch check).
- Frontmatter `name:`/`description:` values must stay identical between the `~/.claude/commands/` and `~/.codex/prompts/` copies of a given command — only `allowed-tools:` differs (present vs. absent).

---

### Task 1: Extract `session-context.sh` from the SessionStart hook

**Files:**
- Create: `workflow/bin/session-context.sh`
- Modify: `workflow/hooks/session-start.sh:18-196`
- Test: `scripts/test_session_context.py`

**Interfaces:**
- Produces: `workflow/bin/session-context.sh` — no args, no stdin required, prints the session-start context as plain text to stdout, exit 0. Guards: silently prints nothing and exits 0 if cwd is not a git repo under `$HOME/src/*` (same guard `session-start.sh` has today).
- Consumes (Task 5, readup.md): agents without a SessionStart-hook-equivalent call this directly.

This is a pure move, not a rewrite — the text `session-start.sh` currently builds into `$CTX` (lines 18-186) becomes this script's own stdout; `session-start.sh` becomes a thin wrapper that calls it and JSON-wraps the result.

- [ ] **Step 1: Create `workflow/bin/session-context.sh` by moving the CTX-building body verbatim**

Read `workflow/hooks/session-start.sh` lines 18-186 (everything from `CWD="$(pwd)"` through the end of the "neglected custom commands nudge" block, i.e. up to but not including the final `CTX+="\nThe user has NOT run /readup yet..."` line and the JSON emit). Move that exact text into the new file, changing only:
- The final assembly: instead of leaving the text in `$CTX` for a later JSON emit, end the script with `printf '%s' "$CTX"`.
- Drop the trailing "The user has NOT run /readup yet..." sentence — that line is specific to the *hook* being auto-injected before the user's first message; it doesn't make sense when an agent is explicitly running this script mid-command.

```bash
#!/bin/bash
# session-context.sh — print readup-style session context as plain text.
#
# Extracted from workflow/hooks/session-start.sh so both the Claude Code
# SessionStart hook (which JSON-wraps this output) and any agent with no
# hook mechanism (Codex) can get the same context. Pure text out, no JSON.
#
# Silent (no output) if cwd doesn't look like a real project — avoids noise
# on quick launches in ~ or /tmp. Does NOT register a session row or run
# `git pull` — those stay behind the explicit /readup command.

set -u

CWD="$(pwd)"
HOME_SRC="$HOME/src"

# Guard: only run in real project dirs under ~/src/ that are git repos
case "$CWD" in
  "$HOME_SRC"/*) ;;
  *) exit 0 ;;
esac
git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

PROJECT="$(basename "$CWD")"
TODAY="$(date "+%A, %B %-d, %Y")"

# Machine label, derived from hostname. Update the case below if you rename a host.
HOSTNAME_SHORT="$(hostname -s)"
case "$HOSTNAME_SHORT" in
  *[Mm]ini*) MACHINE="mini" ;;
  *[Mm][Bb][Pp]*|*[Mm]ac[Bb]ook*) MACHINE="laptop" ;;
  *) MACHINE="$HOSTNAME_SHORT" ;;
esac

# Last ended session for this project
LAST_SUMMARY="$(sqlite3 "$HOME/.claude/prompt-history.db" \
  "SELECT substr(summary, 1, 400) || '|' || ended_at FROM sessions WHERE project='$PROJECT' AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)"

# Recent commits + working tree
RECENT_COMMITS="$(git -C "$CWD" log --oneline -5 2>/dev/null)"
DIRTY="$(git -C "$CWD" status --short 2>/dev/null)"

# Bulletin headlines (skip silently if file missing)
BULLETIN="$(grep -E '^## ' "$HOME/src/prompt-lab/BULLETIN.md" 2>/dev/null | head -5)"

# Assemble context
CTX="Session-start context:

Today: $TODAY
Machine: $MACHINE
Project: $PROJECT
Working dir: $CWD
"

if [ -n "$LAST_SUMMARY" ]; then
  CTX+="
Last session: $LAST_SUMMARY
"
fi

if [ -n "$RECENT_COMMITS" ]; then
  CTX+="
Recent commits:
$RECENT_COMMITS
"
fi

if [ -n "$DIRTY" ]; then
  CTX+="
Uncommitted:
$DIRTY
"
fi

if [ -n "$BULLETIN" ]; then
  CTX+="
Cross-project bulletin (/bulletin for details):
$BULLETIN
"
fi

# --- Cross-repo handoff channel (issue #7) ------------------------------------
HANDOFF_DIR="$HOME/src/.handoff"
HANDOFF_BIN="$HOME/.claude/bin/handoff.sh"
if [ -d "$HANDOFF_DIR/.git" ]; then
  [ -x "$HANDOFF_BIN" ] && "$HANDOFF_BIN" pull >/dev/null 2>&1
  MATCHED=""
  for f in "$HANDOFF_DIR"/*-*.md; do
    [ -e "$f" ] || continue
    if head -5 "$f" | grep '^repos:' | grep -qw "$PROJECT"; then
      MATCHED="$MATCHED $f"
    fi
  done
  if [ -n "$MATCHED" ]; then
    for f in $MATCHED; do
      ACTIVE="$(awk '/^## Active/{a=1;next} /^## /{a=0} a' "$f")"
      if printf '%s' "$ACTIVE" | grep -q '[^[:space:]]'; then
        CTX+="
Cross-repo handoff — $(basename "$f") (## Active; reply via 'handoff.sh append'):
$ACTIVE
"
      fi
    done
  fi
fi

# Turso staleness check.
TURSO_STAMP="$HOME/.claude/.turso-last-sync"
TURSO_LOG="$HOME/.claude/.turso-last-sync.log"
if [ -f "$TURSO_STAMP" ] && [ -z "$(find "$TURSO_STAMP" -mmin -2880 2>/dev/null)" ] \
   && [ -f "$TURSO_LOG" ]; then
  TURSO_LAST_LINE="$(tail -1 "$TURSO_LOG" 2>/dev/null)"
  case "$TURSO_LAST_LINE" in
    *" ok: "*) : ;;
    "") : ;;
    *)
      LAST_SYNC="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$TURSO_STAMP" 2>/dev/null || stat -c '%y' "$TURSO_STAMP" 2>/dev/null | cut -d. -f1)"
      CTX+="
⚠️ Turso sync last succeeded $LAST_SYNC on this machine and the most recent attempt did NOT succeed: [$TURSO_LAST_LINE] — check ~/.claude/.turso-last-sync.log. The async sync hook retries each session, but it keeps failing.
"
      ;;
  esac
fi

# Neglected custom commands nudge — at most once per 7 days, only if any
# user-installed slash command has gone unused for 30+ days.
NUDGE_STAMP="$HOME/.claude/state/commands-nudge.touch"
NUDGE_FRESH="$(find "$NUDGE_STAMP" -mmin -10080 2>/dev/null)"
if [ -z "$NUDGE_FRESH" ] && [ -d "$HOME/.claude/commands" ]; then
  CUTOFF="$(date -v-30d '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '30 days ago' '+%Y-%m-%d %H:%M:%S')"
  NEGLECTED=""
  for cmd_file in "$HOME/.claude/commands/"*.md; do
    [ -f "$cmd_file" ] || continue
    cmd="$(basename "$cmd_file" .md)"
    case "$cmd" in *.bak.*) continue ;; esac
    last="$(sqlite3 "$HOME/.claude/prompt-history.db" \
      "SELECT MAX(timestamp) FROM prompts WHERE prompt = '/$cmd' OR prompt LIKE '/$cmd %' OR prompt LIKE '/$cmd' || x'0a' || '%';" 2>/dev/null)"
    if [ -z "$last" ] || [ "$last" \< "$CUTOFF" ]; then
      desc="$(awk -F': *' '/^description:/{sub(/^[ \t]+/, "", $2); print $2; exit}' "$cmd_file")"
      [ -z "$desc" ] && desc="(no description)"
      if [ -z "$last" ]; then
        NEGLECTED+="   /$cmd — $desc (never used)
"
      else
        NEGLECTED+="   /$cmd — $desc (last used $last)
"
      fi
    fi
  done
  if [ -n "$NEGLECTED" ]; then
    CTX+="
Custom commands you haven't used in 30+ days (weekly reminder):
$NEGLECTED"
    mkdir -p "$(dirname "$NUDGE_STAMP")"
    touch "$NUDGE_STAMP"
  fi
fi

printf '%s' "$CTX"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x workflow/bin/session-context.sh
```

- [ ] **Step 3: Rewrite `session-start.sh` to call the extracted script**

Replace `workflow/hooks/session-start.sh` lines 18-186 (the whole CTX-building body) with a call to the new script, keeping everything else (the shebang/header comment through line 17, and the JSON emit from line 187 onward) unchanged:

```bash
#!/bin/bash
# SessionStart hook — inject lightweight readup-style context at session start.
#
# Output: a single JSON object with hookSpecificOutput.additionalContext.
# Context-gathering logic lives in workflow/bin/session-context.sh (shared
# with agents that have no hook mechanism, e.g. Codex — see /readup step 0).
# This wrapper's only job is invoking that script and JSON-wrapping its
# output for the Claude Code hook protocol.
#
# Does NOT register a session row or run `git pull` — those stay behind the
# explicit /readup command.

set -u

# Read stdin (hook gets a JSON payload, but we don't need any of its fields)
cat >/dev/null 2>&1 || true

# Resolve our own real location so we can find the sibling bin script
# in-repo — this hook runs from $REPO_DIR/workflow/hooks/ (registered by
# absolute repo path in settings.json, never copied to ~/.claude/hooks/),
# same idiom log-prompt.sh uses for its own sibling script (HOOK_REAL).
HOOK_REAL=$(readlink -f "$0" 2>/dev/null || echo "$0")
SESSION_CONTEXT="$(dirname "$HOOK_REAL")/../bin/session-context.sh"

CTX="$("$SESSION_CONTEXT")"

if [ -n "$CTX" ]; then
  CTX+="

The user has NOT run /readup yet — they may or may not. Do not preemptively summarize. Use this context to answer their first message in an informed way."
fi

# Emit hook output JSON. Python handles the escaping cleanly.
python3 -c "
import json, sys
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'SessionStart',
    'additionalContext': sys.stdin.read()
  }
}))
" <<< "$CTX"
```

Note this resolves the sibling script relative to the hook's own real location, not the installed `~/.claude/bin/` copy — hooks in this repo run from their in-repo path (`install.sh`'s printed settings.json registers `$REPO_DIR/workflow/hooks/session-start.sh`, never a copied path), and `log-prompt.sh:186-187` already establishes this exact idiom (`HOOK_REAL=$(readlink -f "$0" ...)` + a relative path to a sibling script) for the same reason. Commands are different — they run from `~/.claude/commands/` invoked from an arbitrary cwd, so `readup.md` (Task 5) correctly references `~/.claude/bin/session-context.sh`, the installed copy. `workflow/install.sh` already copies everything in `workflow/bin/` to `~/.claude/bin/` for that purpose (no change needed there for this task — Task 4 adds the *Codex* distribution separately).

- [ ] **Step 4: Write the regression test**

```python
"""
scripts/test_session_context.py — verify session-context.sh and
session-start.sh agree, and that session-context.sh's own guard clauses work.

Standalone runner (this repo doesn't use pytest — see CLAUDE.md Testing section).
"""
import json
import subprocess
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

failures = []


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

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
```

- [ ] **Step 5: Run the test**

```bash
.venv/bin/python scripts/test_session_context.py
```

Expected: `All checks passed.` (This test runs against your real `$HOME/.claude/prompt-history.db`, real git log, and does a best-effort `~/src/.handoff` pull if that repo exists — same side effects `session-start.sh` already has on every real session start today, so this introduces no new risk.)

- [ ] **Step 6: Commit**

```bash
git add workflow/bin/session-context.sh workflow/hooks/session-start.sh scripts/test_session_context.py
git commit -m "Extract session-context.sh from the SessionStart hook

Pure move: the hook's context-gathering body now lives in a plain script
so agents with no SessionStart-hook equivalent (Codex) can call it
directly. session-start.sh becomes a thin JSON-wrapping caller."
```

---

### Task 2: Rename `sync-claude-md.sh` → `sync-shared-md.sh`

**Files:**
- Modify (rename): `workflow/bin/sync-claude-md.sh` → `workflow/bin/sync-shared-md.sh`
- Modify: `workflow/install.sh:79-85`
- Test: `scripts/test_sync_shared_md.py`

**Interfaces:**
- Produces: `workflow/bin/sync-shared-md.sh --check|--apply [TARGET]` — identical behavior/exit codes to the old `sync-claude-md.sh` (see spec: it was already target-path-agnostic). No functional change, name only.
- Consumes (Task 5): `readup.md` step 6 will call this by its new name.

- [ ] **Step 1: Write the test first (it references the not-yet-existing new filename)**

```python
"""
scripts/test_sync_shared_md.py — the shared-conventions sync script must
work identically against a CLAUDE.md-named and an AGENTS.md-named target,
using the same canonical source and content hash for both.

Standalone runner (no pytest in this repo).
"""
import subprocess
import tempfile
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow", "bin", "sync-shared-md.sh")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with tempfile.TemporaryDirectory() as tmp:
    canonical = os.path.join(tmp, "shared-source.md")
    with open(canonical, "w") as f:
        f.write("# Shared conventions\n\n- Rule one\n- Rule two\n")

    env = {**os.environ, "CLAUDE_MD_SHARED": canonical}

    for target_name in ("CLAUDE.md", "AGENTS.md"):
        target = os.path.join(tmp, target_name)

        apply_result = subprocess.run(
            [SCRIPT, "--apply", target], env=env, capture_output=True, text=True
        )
        check(f"--apply creates {target_name}", os.path.exists(target))
        check(f"--apply on {target_name} exits 0", apply_result.returncode == 0)

        check_result = subprocess.run(
            [SCRIPT, "--check", target], env=env, capture_output=True, text=True
        )
        check(
            f"--check reports in sync for {target_name}",
            check_result.returncode == 0 and "in sync" in check_result.stdout,
            check_result.stdout,
        )

        with open(target) as f:
            content = f.read()
        check(f"{target_name} contains canonical body", "Rule one" in content and "Rule two" in content)

    # Both targets must carry the SAME hash — same canonical source, same stamp.
    with open(os.path.join(tmp, "CLAUDE.md")) as f:
        claude_content = f.read()
    with open(os.path.join(tmp, "AGENTS.md")) as f:
        agents_content = f.read()
    import re

    claude_hash = re.search(r"v=([a-f0-9]+)", claude_content)
    agents_hash = re.search(r"v=([a-f0-9]+)", agents_content)
    check(
        "CLAUDE.md and AGENTS.md carry the same content hash",
        claude_hash and agents_hash and claude_hash.group(1) == agents_hash.group(1),
    )

    # Drift detection: changing the canonical source should flip --check to drift.
    with open(canonical, "a") as f:
        f.write("- Rule three\n")
    drift_result = subprocess.run(
        [SCRIPT, "--check", os.path.join(tmp, "CLAUDE.md")], env=env, capture_output=True, text=True
    )
    check(
        "--check reports drift after canonical source changes",
        drift_result.returncode == 1 and "drift" in drift_result.stdout,
        drift_result.stdout,
    )

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
```

Run it now, before the rename:

```bash
.venv/bin/python scripts/test_sync_shared_md.py
```

Expected: FAIL — `workflow/bin/sync-shared-md.sh` doesn't exist yet, so every `subprocess.run([SCRIPT, ...])` call raises `FileNotFoundError`. That failure is the point: it confirms the test is exercising the real file path this task is about to create.

- [ ] **Step 2: Perform the rename**

```bash
git mv workflow/bin/sync-claude-md.sh workflow/bin/sync-shared-md.sh
```

- [ ] **Step 3: Update the renamed script's internal self-references**

In `workflow/bin/sync-shared-md.sh`, replace every literal occurrence of the string `sync-claude-md` with `sync-shared-md` (the header comment, the two usage lines in the top comment block, the "canonical source not found" error message's script-name context, the `mktemp` template, and the final `usage:` error message). Also generalize the header's first line from "materialize the shared-conventions block into a repo's CLAUDE.md." to "materialize the shared-conventions block into a repo's CLAUDE.md or AGENTS.md." Do **not** rename the `CLAUDE_MD_SHARED` environment variable or the canonical source filename (`claude-md-shared.md`) — those stay as-is per the spec (Explicitly out of scope).

- [ ] **Step 4: Update `workflow/install.sh`'s reference to the old name**

In `workflow/install.sh:79-85`, replace:

```bash
# --- shared CLAUDE.md conventions source ---
# claude-md-shared.md is the single source of truth for Nico's cross-repo output
# rules. Installed to ~/.claude/ so sync-claude-md.sh (a bin script, installed above)
# can find it from any repo. Edit the in-repo copy, re-run install.sh, then
# `sync-claude-md.sh --apply` in each repo to materialize the block into its CLAUDE.md.
install_file "$REPO_DIR/workflow/claude-md-shared.md" "$HOME/.claude/claude-md-shared.md" "claude-md-shared.md"
echo "Copied conventions source: claude-md-shared.md → $HOME/.claude/"
```

with:

```bash
# --- shared conventions source ---
# claude-md-shared.md is the single source of truth for Nico's cross-repo output
# rules. Installed to ~/.claude/ so sync-shared-md.sh (a bin script, installed above)
# can find it from any repo. Edit the in-repo copy, re-run install.sh, then
# `sync-shared-md.sh --apply ./CLAUDE.md` (or `./AGENTS.md`) in each repo to
# materialize the block into that file.
install_file "$REPO_DIR/workflow/claude-md-shared.md" "$HOME/.claude/claude-md-shared.md" "claude-md-shared.md"
echo "Copied conventions source: claude-md-shared.md → $HOME/.claude/"
```

- [ ] **Step 5: Make the renamed script executable and run the real test**

```bash
chmod +x workflow/bin/sync-shared-md.sh
.venv/bin/python scripts/test_sync_shared_md.py
```

Expected: `All checks passed.`

- [ ] **Step 6: Commit**

```bash
git add workflow/bin/sync-claude-md.sh workflow/bin/sync-shared-md.sh workflow/install.sh scripts/test_sync_shared_md.py
git commit -m "Rename sync-claude-md.sh to sync-shared-md.sh

The script was already fully target-path-agnostic (marker tokens, hashing,
and the safety diff never referenced CLAUDE.md specifically) — only the
name was misleading. No behavior change. Prepares for AGENTS.md targets
in the next task."
```

---

### Task 3: Add the Codex branch-naming convention to the shared-conventions source

**Files:**
- Modify: `workflow/claude-md-shared.md`
- Test: reuse `scripts/test_sync_shared_md.py` from Task 2 (no new test file — this task only changes the canonical content, and Task 2's test already verifies content propagates and hashes match)

**Interfaces:**
- Produces: canonical shared-conventions text now documents the `codex/<desc>` branch convention. Consumed by Task 5's `readup.md` step 4 (which checks for branches matching this pattern) and by every repo's own `sync-shared-md.sh --apply` run (out of scope here — that's a per-repo action the repo's own agent takes later, per the existing invariant).

- [ ] **Step 1: Read the current file to find the right insertion point**

```bash
cat workflow/claude-md-shared.md
```

Find the "## Shared conventions" heading (it's the top-level heading of this file — the whole file is the shared-conventions body compiled into each repo's CLAUDE.md/AGENTS.md between the sentinel markers).

- [ ] **Step 2: Add a new convention entry**

Add this as a new bullet under the existing conventions (append at the end of the file, matching the existing bullet style — each convention is a bolded lead-in followed by an em-dash and explanation):

```markdown

- **Codex branches are named `codex/<description>`.** When working in this repo via Codex CLI, always create a working branch under the `codex/` prefix (e.g. `codex/fix-flaky-test`) rather than working directly on `main` or an unprefixed branch. Claude Code has no visibility into other tools' running sessions (`ListAgents` only sees Claude sessions), so this prefix is the one signal a Claude session can check for — a local or remote `codex/*` branch means Codex has touched or is touching this repo, even though its session itself is invisible. Claude branches keep whatever naming they already use; only Codex adopts this new prefix.
```

- [ ] **Step 3: Verify propagation with the existing test**

```bash
.venv/bin/python scripts/test_sync_shared_md.py
```

Expected: `All checks passed.` (this test uses its own temp canonical source, not the real `claude-md-shared.md`, so it isn't directly checking this new bullet — it's confirming the sync mechanism this bullet will travel through still works after Task 2's rename).

- [ ] **Step 4: Manually verify the new bullet is present in the real canonical file**

```bash
grep -A3 "Codex branches are named" workflow/claude-md-shared.md
```

Expected: the paragraph you just added, printed back.

- [ ] **Step 5: Commit**

```bash
git add workflow/claude-md-shared.md
git commit -m "Add codex/<desc> branch-naming convention to shared conventions

Gives a Claude session a way to detect that Codex has touched a repo
despite ListAgents not crossing tool boundaries. Propagates to every
repo's CLAUDE.md/AGENTS.md the next time that repo runs
sync-shared-md.sh --apply."
```

Note: this change does NOT itself update prompt-lab's own `CLAUDE.md` — that happens in Task 8, alongside the rest of this plan's documentation, via the normal `sync-shared-md.sh --apply ./CLAUDE.md` flow.

---

### Task 4: Distribute commands to Codex's `~/.codex/prompts/`

**Files:**
- Modify: `workflow/install.sh` (add a new section after the existing "Slash commands" section, i.e. after line 64)
- Test: `scripts/test_install_codex_prompts.py`

**Interfaces:**
- Produces: when `install.sh` runs (manually, by Nico — see Global Constraints), every file in `workflow/commands/*.md` is also written to `~/.codex/prompts/<name>.md` with any `allowed-tools:` line removed.

- [ ] **Step 1: Write the test first (structural + transformation-only, no `$HOME` writes)**

```python
"""
scripts/test_install_codex_prompts.py — verify install.sh's Codex-prompt
distribution step exists and that its frontmatter transform is correct.

Does NOT run install.sh (it writes into the real $HOME and loads a real
launchd job — see plan Global Constraints). Instead: (1) a structural check
that install.sh contains the expected loop, and (2) a functional check of
the exact transform (grep -v '^allowed-tools:') against every real command
file, run directly — no filesystem writes outside a temp dir.

Standalone runner (no pytest in this repo).
"""
import subprocess
import glob
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


# 1. Structural: install.sh must reference ~/.codex/prompts and strip allowed-tools.
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

    had_allowed_tools = any(l.startswith("allowed-tools:") for l in original_lines)
    check(
        f"{name}: has an allowed-tools line to strip",
        had_allowed_tools,
    )
    check(
        f"{name}: transform removes exactly one line",
        len(original_lines) - len(transformed_lines) == 1,
        f"{len(original_lines)} -> {len(transformed_lines)}",
    )
    check(
        f"{name}: transform leaves no allowed-tools line behind",
        not any(l.startswith("allowed-tools:") for l in transformed_lines),
    )
    check(
        f"{name}: transform preserves the name: line",
        any(l.startswith("name:") for l in transformed_lines),
    )
    check(
        f"{name}: transform preserves the description: line",
        any(l.startswith("description:") for l in transformed_lines),
    )

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
```

- [ ] **Step 2: Run the test to confirm it fails on the structural checks (install.sh doesn't have the Codex loop yet)**

```bash
.venv/bin/python scripts/test_install_codex_prompts.py
```

Expected: the two `install.sh references...` checks FAIL; the per-file functional checks PASS (they test `grep` directly against real files, independent of `install.sh`'s own content).

- [ ] **Step 3: Add the Codex-prompt distribution loop to `install.sh`**

In `workflow/install.sh`, immediately after the existing "Slash commands" block (after line 64, before the "bin scripts" section), insert:

```bash
# --- Codex custom prompts (same source, allowed-tools stripped) ---
# Codex CLI's equivalent of Claude commands lives in ~/.codex/prompts/<name>.md,
# invoked as /prompts:<name>. It has no allowed-tools frontmatter field, so we
# strip that one line rather than maintain a second copy of each command body.
CODEX_PROMPTS_DIR="$HOME/.codex/prompts"
mkdir -p "$CODEX_PROMPTS_DIR"
for cmd in "$REPO_DIR/workflow/commands/"*.md; do
    name=$(basename "$cmd")
    rendered=$(mktemp -t "codex-prompt.XXXXXX")
    grep -v '^allowed-tools:' "$cmd" > "$rendered"
    install_file "$rendered" "$CODEX_PROMPTS_DIR/$name" "codex prompt $name"
    rm -f "$rendered"
    echo "Copied codex prompt: $name → $CODEX_PROMPTS_DIR/"
done
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
.venv/bin/python scripts/test_install_codex_prompts.py
```

Expected: `All checks passed.`

- [ ] **Step 5: Commit**

```bash
git add workflow/install.sh scripts/test_install_codex_prompts.py
git commit -m "Distribute workflow/commands/* to Codex's ~/.codex/prompts/ too

Same source files as the Claude commands install step; only the
allowed-tools frontmatter line (Claude-only) is stripped for the Codex
copies. Not run automatically — Nico runs install.sh by hand when ready
(see plan's manual verification note)."
```

- [ ] **Step 6: Flag manual verification for Nico (do not execute this yourself)**

Note in the task's completion summary that a full end-to-end check requires actually running `workflow/install.sh`, which writes into the real `~/.claude/`, `~/.codex/`, and `~/Library/LaunchAgents/`. This is a manual step for Nico to run when he chooses:

```bash
workflow/install.sh
diff <(grep -v '^allowed-tools:' workflow/commands/readup.md) ~/.codex/prompts/readup.md
```

Expected: no diff output (identical).

---

### Task 5: Update `readup.md` for both agents

**Files:**
- Modify: `workflow/commands/readup.md`
- Test: `scripts/test_readup_md_structure.py`

**Interfaces:**
- Consumes: `workflow/bin/session-context.sh` (Task 1), `workflow/bin/sync-shared-md.sh` (Task 2), the `codex/<desc>` convention (Task 3).

- [ ] **Step 1: Write a structural test first**

```python
"""
scripts/test_readup_md_structure.py — readup.md must reference the renamed
sync script (not the old name), must reference session-context.sh, and must
check for codex/* branches. Content-level guard against regressions in a
markdown/prose file where a full behavioral test would require a live
agent session.

Standalone runner (no pytest in this repo).
"""
import subprocess
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
PATH = os.path.join(REPO_DIR, "workflow", "commands", "readup.md")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with open(PATH) as f:
    content = f.read()

check("no reference to the old script name remains", "sync-claude-md.sh" not in content)
check("references the renamed sync script", "sync-shared-md.sh" in content)
check("references session-context.sh", "session-context.sh" in content)
check("checks for codex/* branches", "codex/*" in content or "codex/" in content)
check("still checks CLAUDE.md drift", "CLAUDE.md" in content)
check("also checks AGENTS.md drift", "AGENTS.md" in content)
check("frontmatter still has a name: line", content.startswith("---\nname: readup"))

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
.venv/bin/python scripts/test_readup_md_structure.py
```

Expected: several FAILs (session-context.sh, AGENTS.md, codex/* not yet referenced; old script name still present).

- [ ] **Step 3: Update the frontmatter (`workflow/commands/readup.md:4`)**

Replace:

```
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/sync-claude-md.sh:*), Bash(~/.claude/bin/handoff.sh:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Bash(mkdir:*), Bash(touch:*), Bash(gh issue list:*), Bash(gh pr list:*), Bash(gh run list:*), Bash(gh run view:*), Bash(.venv/bin/python scripts/check_public_allowlist.py:*), Bash(python3 scripts/check_public_allowlist.py:*), Read, Write, Edit, Glob, Agent, ListAgents
```

with:

```
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/sync-shared-md.sh:*), Bash(~/.claude/bin/session-context.sh:*), Bash(~/.claude/bin/handoff.sh:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Bash(mkdir:*), Bash(touch:*), Bash(gh issue list:*), Bash(gh pr list:*), Bash(gh run list:*), Bash(gh run view:*), Bash(.venv/bin/python scripts/check_public_allowlist.py:*), Bash(python3 scripts/check_public_allowlist.py:*), Read, Write, Edit, Glob, Agent, ListAgents
```

- [ ] **Step 4: Add step 0 and update the intro note (`workflow/commands/readup.md:9`)**

Replace:

```
Note: the SessionStart hook already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines. **Do not re-fetch any of that.** This command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.
```

with:

```
Note: a SessionStart hook usually already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines (Claude Code sessions get this automatically). **If you already have that context, do not re-fetch it.** If you don't — Codex and any other agent without an equivalent hook won't — run this first:

```bash
~/.claude/bin/session-context.sh
```

and read its output before continuing. Either way, this command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.
```

- [ ] **Step 5: Update step 4, "Other agents on this repo" (`workflow/commands/readup.md:16`)**

Replace:

```
4. Other agents on this repo: `git worktree list` — a linked worktree besides the main checkout means another agent may be mid-task here; flag it with its branch. If the `ListAgents` tool is available, also call it and flag any other local or cloud session whose name/task suggests this repo (a cloud agent's work won't show in `git status` at all until it pushes). Remote branches with no local tracking (item 2) are the third tell. Only the main worktree and no other sessions → say nothing. `ListAgents` missing or erroring → skip silently, never block session start.
```

with:

```
4. Other agents on this repo: `git worktree list` — a linked worktree besides the main checkout means another agent may be mid-task here; flag it with its branch. If the `ListAgents` tool is available, also call it and flag any other local or cloud session whose name/task suggests this repo (a cloud agent's work won't show in `git status` at all until it pushes). Remote branches with no local tracking (item 2) are the third tell. Also check for Codex activity, which `ListAgents` cannot see: `git branch --list 'codex/*'` and `git branch -r --list 'origin/codex/*'` — by convention Codex always works on a `codex/<desc>` branch, so a match means Codex has touched or is touching this repo even with no visible session. Only the main worktree, no `codex/*` branches, and no other sessions → say nothing. `ListAgents` missing or erroring → skip silently, never block session start.
```

- [ ] **Step 6: Update step 6, shared-conventions drift check (`workflow/commands/readup.md:78-90`)**

Replace the entire "## 6. Check shared-conventions drift" section with:

```markdown
## 6. Check shared-conventions drift (check only — never auto-write)

Verify this repo's CLAUDE.md and AGENTS.md (whichever exist) carry the current shared-conventions block:

```bash
~/.claude/bin/sync-shared-md.sh --check ./CLAUDE.md
~/.claude/bin/sync-shared-md.sh --check ./AGENTS.md
```

- `in sync` → say nothing.
- `missing` / `drift` → flag one line per file in the summary and offer the exact fix: `~/.claude/bin/sync-shared-md.sh --apply ./<file>` (review the `git diff`, then commit). Never apply automatically — materializing into a checked-in file is the user's call.
- `absent` (that file doesn't exist in this repo) → skip silently; not every repo warrants a CLAUDE.md or an AGENTS.md.

The block is auto-managed between `SHARED-CONVENTIONS` markers; the source of truth is `prompt-lab/workflow/claude-md-shared.md`. A repo's AGENTS.md may carry other auto-managed blocks under different markers (e.g. songpath's `next dev`-generated `BEGIN:nextjs-agent-rules`) — those are untouched, since the sentinel tokens differ.
```

- [ ] **Step 7: Run the structural test again**

```bash
.venv/bin/python scripts/test_readup_md_structure.py
```

Expected: `All checks passed.`

- [ ] **Step 8: Commit**

```bash
git add workflow/commands/readup.md scripts/test_readup_md_structure.py
git commit -m "readup.md: support agents with no SessionStart hook

Adds an explicit session-context.sh fallback for Codex, checks for
codex/* branches as a substitute for cross-tool session visibility, and
checks AGENTS.md drift alongside CLAUDE.md via the renamed sync script."
```

---

### Task 6: Genericize `resync.md`'s subagent language

**Files:**
- Modify: `workflow/commands/resync.md:23`
- Test: manual (single-line prose edit; covered by re-reading the diff, no new test file — see rationale below)

**Interfaces:** none (no other task depends on this file's content).

Rationale for no automated test: this is a one-line wording change with no parseable structural contract (unlike readup.md's script references, there's no fixed string another file or script depends on). A grep-based test asserting the *absence* of the word "Explore" would be low-value theater. Verify by reading the diff in Step 2.

- [ ] **Step 1: Update the wording**

In `workflow/commands/resync.md:23`, replace:

```
6. Launch 2-3 Explore agents IN PARALLEL, each owning a cluster of items. Each must report **DONE / PARTIAL / TODO** with **commit SHA + file:line** as evidence. No CLAUDE.md citations.
```

with:

```
6. If your tool supports spawning parallel research subagents, launch 2-3 of them, each owning a cluster of items; otherwise work through the clusters yourself, one at a time. Each cluster must report **DONE / PARTIAL / TODO** with **commit SHA + file:line** as evidence. No CLAUDE.md citations.
```

- [ ] **Step 2: Review the diff**

```bash
git diff workflow/commands/resync.md
```

Confirm only line 23 changed, and the rest of the file (including the `allowed-tools: ... Agent` frontmatter, which is dropped entirely for the Codex copy at install time per Task 4 — no edit needed there) is untouched.

- [ ] **Step 3: Commit**

```bash
git add workflow/commands/resync.md
git commit -m "resync.md: genericize subagent-spawning language for Codex"
```

---

### Task 7: Make `handoff.md`'s model attribution agent-aware

**Files:**
- Modify: `workflow/commands/handoff.md:77,114`
- Test: `scripts/test_handoff_md_structure.py`

**Interfaces:** none (no other task depends on this file's content — Task 8's CLAUDE.md documentation mentions the behavior but doesn't parse the file).

- [ ] **Step 1: Write a structural test first**

```python
"""
scripts/test_handoff_md_structure.py — handoff.md must not hardcode
model='claude-code' (that's wrong when run from Codex); it must instead
leave an explicit substitution placeholder, consistent with the existing
<project>/<session_id> placeholder style already used in this same file.

Standalone runner (no pytest in this repo).
"""
import subprocess
import os
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
PATH = os.path.join(REPO_DIR, "workflow", "commands", "handoff.md")

failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


with open(PATH) as f:
    content = f.read()

check("no hardcoded model='claude-code'", "model='claude-code'" not in content)
check(
    "daily-summary persist uses the agent-choice placeholder",
    "model='<claude-code|codex>'" in content,
)
check(
    "weekly-rollup persist uses the agent-choice placeholder",
    content.count("model='<claude-code|codex>'") == 2,
)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("All checks passed.")
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
.venv/bin/python scripts/test_handoff_md_structure.py
```

Expected: FAIL on all three checks (the hardcoded literal is still present).

- [ ] **Step 3: Update the daily-summary persist command (`workflow/commands/handoff.md:77`)**

Replace:

```python
s.upsert_daily_summary(model='claude-code', **d)
```

with:

```python
s.upsert_daily_summary(model='<claude-code|codex>', **d)
```

And add one sentence directly above that code block (before "IMPORTANT: use these exact command forms to persist the daily summary:"):

```
Replace `<claude-code|codex>` with whichever you are running as (or the specific Codex model id, e.g. `gpt-6-astra`, if you want finer-grained attribution) — same substitution convention as `<project>`/`<session_id>` above.
```

- [ ] **Step 4: Update the weekly-rollup persist command (`workflow/commands/handoff.md:114`)**

Replace:

```python
s.upsert_weekly_rollup(model='claude-code', **d)
```

with:

```python
s.upsert_weekly_rollup(model='<claude-code|codex>', **d)
```

- [ ] **Step 5: Run the test again**

```bash
.venv/bin/python scripts/test_handoff_md_structure.py
```

Expected: `All checks passed.`

- [ ] **Step 6: Commit**

```bash
git add workflow/commands/handoff.md scripts/test_handoff_md_structure.py
git commit -m "handoff.md: attribute daily summaries/rollups to the running agent

model='claude-code' was hardcoded, which would mislabel every summary
written by a Codex-run /handoff. Now an explicit substitution
placeholder, matching the existing <project>/<session_id> convention in
the same file."
```

---

### Task 8: Document the change in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (Next Steps / Traps / Settled sections)

**Interfaces:** none — documentation only, closes out the plan.

- [ ] **Step 1: Materialize the updated shared-conventions block into prompt-lab's own CLAUDE.md**

```bash
~/.claude/bin/sync-shared-md.sh --apply ./CLAUDE.md
```

(This requires Task 2's rename and Task 3's new bullet to already be in place, and requires the renamed script to be runnable — either from `workflow/bin/` directly with a `CLAUDE_MD_SHARED` override pointing at the in-repo `workflow/claude-md-shared.md`, since the installed `~/.claude/bin/sync-shared-md.sh` won't exist until Nico runs `install.sh` per Task 4's manual step. Use:)

```bash
CLAUDE_MD_SHARED="$(pwd)/workflow/claude-md-shared.md" workflow/bin/sync-shared-md.sh --apply ./CLAUDE.md
```

- [ ] **Step 2: Review the diff**

```bash
git diff CLAUDE.md
```

Expected: only the text inside the `<!-- SHARED-CONVENTIONS:BEGIN -->`...`<!-- SHARED-CONVENTIONS:END -->` markers changed (new hash, new Codex-branch bullet added). Nothing outside the markers should differ — the script's own safety rail aborts if it does.

- [ ] **Step 3: Add a "Settled" entry under CLAUDE.md's "Settled — don't re-litigate" section**

Add:

```markdown
- **Dual-agent commands (Claude Code + Codex) — 2026-09-12.** `workflow/commands/*.md`
  is the single source for both; `install.sh` distributes to `~/.claude/commands/`
  (unchanged) and `~/.codex/prompts/` (allowed-tools stripped). Codex has no
  SessionStart-hook equivalent, so `/readup` falls back to running
  `workflow/bin/session-context.sh` directly — extracted from the hook for exactly
  this reuse. `sync-claude-md.sh` was renamed `sync-shared-md.sh` (it was already
  target-path-agnostic) so the same shared-conventions source compiles into both
  CLAUDE.md and AGENTS.md. Codex sessions always branch as `codex/<desc>`, the one
  signal a Claude session can check for since `ListAgents` doesn't cross tool
  boundaries. Full design: `docs/superpowers/specs/2026-09-12-dual-agent-commands-design.md`.
```

- [ ] **Step 4: Add a Next Steps entry for the deferred manual step**

Add under "### Open":

```markdown
**Dual-agent commands landed in code, not yet installed.** `workflow/install.sh`
now also writes `~/.codex/prompts/*`, but nobody has run it since — do that, then
verify `~/.codex/prompts/readup.md` has no `allowed-tools:` line and actually try
`/prompts:readup` from Codex in songpath or musicforge once. That first real
`/handoff` run from Codex is what actually gets songpath onto the dashboard (see
`docs/superpowers/specs/2026-09-12-dual-agent-commands-design.md` — no separate
registration step exists).
```

- [ ] **Step 5: Run the full test suite to confirm nothing else broke**

```bash
for f in scripts/test_*.py; do .venv/bin/python "$f"; done
```

Expected: all pass, including the four new test files from this plan.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: document dual-agent commands, flag install.sh as pending

Materializes the new codex/<desc> branch-naming bullet via
sync-shared-md.sh --apply, and records that install.sh needs a real run
before Codex actually has the ported commands."
```

---

## Self-review notes

- **Spec coverage:** Design section 1 (command porting) → Tasks 4, 5, 6. Section 2
  (session-context extraction) → Task 1. Section 3 (AGENTS.md sync) → Tasks 2, 3, 5.
  Section 4 (songpath/attribution) → Task 7 (mechanism) + Task 8 step 4 (the
  follow-through note that running it is what actually fixes songpath). Section 5
  (branch convention) → Task 3 (content) + Task 5 step 5 (readup's check). "Explicitly
  out of scope" items are not implemented anywhere in this plan — confirmed no task
  builds Codex prompt capture, a cross-agent registry, per-repo pushes, or AGENTS.md
  content trimming.
- **Placeholder scan:** no TBD/TODO/"handle appropriately" language in any task. The
  `<claude-code|codex>` and `<project>`/`<session_id>` strings in Task 7 are
  intentional, pre-existing-style substitution placeholders inside the *command file
  being edited* (documented and tested for), not gaps in this plan's own instructions.
- **Type/name consistency:** `session-context.sh` (Task 1) is referenced by that exact
  name in Task 5 Steps 3-4. `sync-shared-md.sh` (Task 2) is referenced by that exact
  name in Tasks 3, 5, 8. The `codex/*` branch pattern is worded identically in Task 3's
  convention text and Task 5's readup.md check.
