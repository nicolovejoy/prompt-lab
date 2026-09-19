# Session-Context Diet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the per-session context tax (194 KB injected at SessionStart, 99% of it cross-repo handoff bodies; 49 KB CLAUDE.md) and the readup round-trip count, and make CLAUDE.md trimming a recurring part of `/handoff`.

**Architecture:** Four independent changes. (1) `session-context.sh` injects handoff *headlines* (dated `### ` lines, newer than 30 days) plus counts instead of full `## Active` bodies. (2) A new `workflow/bin/readup-checks.sh` runs readup's seven read-only probes in one call and prints a compact labelled report; `readup.md` shrinks to invoking it. (3) `CLAUDE.md` Next Steps narrative moves to `docs/history.md` under `(moved 2026-09-13)` headings. (4) `handoff.md` gains a weekly size-gated "trim CLAUDE.md" step with a state marker.

**Tech Stack:** bash (must run on macOS BSD userland AND Linux — see traps), Python 3 standalone test runners (not pytest), markdown command files under `workflow/commands/`.

**Spec:** This plan is its own spec; the design discussion lives in the 2026-09-13 session (measurements: handoff Active sections = 193 KB across 14 channels / 127 entries; CLAUDE.md = 49,315 bytes; readup.md = 13,561 bytes).

## Global Constraints

- Tests are standalone runners: run `.venv/bin/python scripts/test_<name>.py`, never pytest.
- **No macOS-only shell idioms** in `workflow/`: every `date -v…` needs a `|| date -d …` GNU fallback; never `tail -r`; `stat -f %m … || stat -c %Y …`.
- `workflow/bin/*` and `workflow/commands/*` run from installed copies under `~/.claude/`. Do NOT run `workflow/install.sh` — Nico runs it himself. Tests must exercise the in-repo files via explicit paths.
- Never edit anything between the `SHARED-CONVENTIONS` markers in `CLAUDE.md`; `scripts/test_sync_shared_md.py` guards this.
- Commit after each task with a message ending in:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XBnvXJ7HgKj35GzqHuS89X
  ```
- Work on the current branch `codex/agent-work-launchers` (it is the session's branch; don't create another).

---

### Task 1: Headline-only handoff injection in `session-context.sh`

**Files:**
- Modify: `workflow/bin/session-context.sh:82-117` (the `Cross-repo handoff channel` block)
- Modify: `scripts/test_session_context.py` (append a section)
- Modify: `CLAUDE.md:44-47` (the "Cross-agent handoff" paragraph's sentence "The SessionStart hook auto-injects the matching file's `## Active` section…")

**Interfaces:**
- Consumes: `PROJECT` (already set at line 24 as `basename "$CWD"`), `CTX` accumulator, the existing `date -v-30d … || date -d '30 days ago'` idiom at line 147.
- Produces: env overrides `HANDOFF_DIR` (default `$HOME/src/.handoff`), `HANDOFF_BIN` (default `$HOME/.claude/bin/handoff.sh`), `HANDOFF_HEADLINE_DAYS` (default `30`). Output block format per matched channel with ≥1 active entry:

  ```
  Cross-repo handoff — <file>: <N> active entries, <M> newer than <D>d (bodies: cat ~/src/.handoff/<file>; reply via 'handoff.sh append'):
  ### 2026-09-09 songpath → prompt-lab: <subject>
  ### …
  ```
  Only `### ` lines whose date (chars 5-14, `YYYY-MM-DD`) is ≥ cutoff are listed. When `M == 0` the header line still prints (so an old-but-unarchived backlog stays visible as a count) with no headline lines under it.

- [ ] **Step 1: Write the failing test**

Append to `scripts/test_session_context.py` before the final summary/exit block (find the existing `failures` reporting at the bottom and insert above it):

```python
# 3. Handoff channel injection is headline-only and age-capped. Build a fake
#    ~/src/.handoff with one channel matching this repo's basename and three
#    entries: fresh, stale, and fresh-with-a-multiline-body. Bodies must never
#    reach the output (they were 99% of a 194 KB injection on 2026-09-13).
import datetime
import tempfile

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python scripts/test_session_context.py`
Expected: FAIL on "handoff: no body text leaks" and "handoff: counts in header" (current script dumps whole Active section; also FAIL on "stale headline NOT listed").

- [ ] **Step 3: Implement**

Replace lines 83-84 of `workflow/bin/session-context.sh`:

```bash
HANDOFF_DIR="${HANDOFF_DIR:-$HOME/src/.handoff}"
HANDOFF_BIN="${HANDOFF_BIN:-$HOME/.claude/bin/handoff.sh}"
# Headline-only injection (2026-09-13). Full `## Active` bodies were 193 KB /
# ~48K tokens across 14 channels at every session start — 99% of the hook's
# output — because entries are appended far more often than they are archived.
# Inject the dated `### ` headlines newer than HANDOFF_HEADLINE_DAYS plus a
# count; the body is one `cat` away when a headline matters.
HANDOFF_HEADLINE_DAYS="${HANDOFF_HEADLINE_DAYS:-30}"
```

Replace the inner `for f in $MATCHED; do … done` loop (lines ~107-116) with:

```bash
    HANDOFF_CUTOFF="$(date -v-"${HANDOFF_HEADLINE_DAYS}"d '+%Y-%m-%d' 2>/dev/null \
      || date -d "${HANDOFF_HEADLINE_DAYS} days ago" '+%Y-%m-%d')"
    for f in $MATCHED; do
      # Only `### ` lines inside `## Active`; date is the first token after `### `.
      HEADLINES="$(awk '/^## Active/{a=1;next} /^## /{a=0} a && /^### /' "$f")"
      [ -n "$HEADLINES" ] || continue
      TOTAL="$(printf '%s\n' "$HEADLINES" | wc -l | tr -d ' ')"
      FRESH="$(printf '%s\n' "$HEADLINES" | awk -v c="$HANDOFF_CUTOFF" 'substr($0,5,10) >= c')"
      FRESH_N="$(printf '%s' "$FRESH" | grep -c '^### ' || true)"
      CTX+="
Cross-repo handoff — $(basename "$f"): $TOTAL active entries, $FRESH_N newer than ${HANDOFF_HEADLINE_DAYS}d (bodies: cat ~/src/.handoff/$(basename "$f"); reply via 'handoff.sh append'):
"
      [ -n "$FRESH" ] && CTX+="$FRESH
"
    done
```

Note `grep -c` on empty input prints `0` and exits 1; the `|| true` keeps `set -e` (if enabled) from tripping. Verify whether the script uses `set -e`/`pipefail` at the top and keep the idiom safe either way.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_session_context.py`
Expected: all PASS, including the pre-existing section-2 "hook wraps session-context exactly" checks (the hook inherits env, so nothing else changes).

Also run the real thing and eyeball size: `workflow/bin/session-context.sh | wc -c` — expected well under 10,000 bytes (was 194,265).

- [ ] **Step 5: Update CLAUDE.md pointer**

In `CLAUDE.md` "Cross-agent handoff" paragraph, replace "The SessionStart hook auto-injects the matching file's `## Active` section after a time-boxed best-effort pull, so you see pending notes without reading the file manually." with: "The SessionStart hook auto-injects, per matching file, the dated `### ` headlines newer than 30 days plus an active-entry count (`HANDOFF_HEADLINE_DAYS` overrides the window). Bodies are not injected — `cat` the file when a headline matters. Full bodies used to be injected and reached 193 KB per session start (2026-09-13)."

- [ ] **Step 6: Commit**

```bash
git add workflow/bin/session-context.sh scripts/test_session_context.py CLAUDE.md
git commit -m "session-context.sh: inject handoff headlines, not bodies (193 KB → <10 KB per session)"
```

---

### Task 2: `readup-checks.sh` — one call for readup's seven read-only probes

**Files:**
- Create: `workflow/bin/readup-checks.sh` (executable)
- Create: `scripts/test_readup_checks.py`
- Modify: `workflow/commands/readup.md` (replace the bodies of items 2 and 4 under "Do (in parallel)" and sections 5, 6, 7, 8, 9 with one invocation + an interpretation table; keep item 1 register-session, item 3 read CLAUDE.md, the `ListAgents` sentence in item 4, section 4 lazy synthesis, and the "Then" section intact)
- Modify: `scripts/test_readup_md_structure.py` (add checks)

**Interfaces:**
- Produces: `readup-checks.sh` prints one `KEY=VALUE` (or `KEY:` + indented block) line group per probe on stdout, always exits 0, never modifies the tree or pulls. Keys, in order:

  ```
  REMOTE=<git status -sb first line>
  TRACKING:            (block: branches whose upstream track is non-empty, from git for-each-ref; empty block = none)
  REMOTE_ONLY:         (block: git branch -r --no-merged | grep -v HEAD)
  WORKTREES:           (block: git worktree list, only if >1 line, else "WORKTREES=main-only")
  CODEX_BRANCHES:      (block: local + remote codex/* ; or "CODEX_BRANCHES=none")
  RESYNC=age_h=<n> commits_since=<n> due=<yes|no>
  CONVENTIONS_CLAUDE=<in sync|drift|missing|absent>
  CONVENTIONS_AGENTS=<in sync|drift|missing|absent>
  HANDOFF_SYNC=<ok|conflict|offline|absent>
  CI_PROBE=<ok|skip|error> [reason=...]
  CI_MAIN:             (block: the JSON from gh run list, when ok)
  CI_BRANCH:           (block: current-branch runs, only when current != default)
  PUBLIC_DRIFT=<ok|drift|config|skip>  (+ the script's output lines as a block when drift/config)
  ```
- Consumes: the exact commands already in `readup.md` sections 2, 4, 5, 6, 7, 8, 9 — port them verbatim, including the CI-probe's retry-once and its `CI_PROBE_NOTE=workflow-files-exist-but-no-runs` line, the resync marker math (`due=yes` iff `age_h >= 48 && commits_since > 3`), and the public-allowlist exit-code mapping (0→ok, 1→drift, 2→config, not-prompt-lab-or-missing→skip). `sync-shared-md.sh --check` output is `in sync: …` / `drift: …` / `missing: …` / `absent: …` — take the first word(s) before the colon.

- [ ] **Step 1: Write the failing test**

`scripts/test_readup_checks.py`:

```python
"""
scripts/test_readup_checks.py — readup-checks.sh bundles readup's read-only
probes into one call. Standalone runner (not pytest).
"""
import os
import subprocess
import sys

REPO_DIR = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()
SCRIPT = os.path.join(REPO_DIR, "workflow/bin/readup-checks.sh")
failures = []


def check(name, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


check("script is executable", os.access(SCRIPT, os.X_OK))
src = open(SCRIPT).read()
check("no BSD-only tail -r", "tail -r" not in src)
check("stat has GNU fallback", "stat -c" in src or "stat -f" not in src)
check("no git pull / checkout / reset (read-only)", not any(w in src for w in ("git pull", "git checkout", "git reset", "git rebase")))

before = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture_output=True, text=True).stdout
r = subprocess.run([SCRIPT], cwd=REPO_DIR, capture_output=True, text=True, timeout=120)
after = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_DIR, capture_output=True, text=True).stdout
check("exits 0", r.returncode == 0, r.stderr[-400:])
check("does not modify the tree", before == after)
out = r.stdout
for key in ("REMOTE=", "RESYNC=age_h=", "CONVENTIONS_CLAUDE=", "CONVENTIONS_AGENTS=", "HANDOFF_SYNC=", "CI_PROBE=", "PUBLIC_DRIFT="):
    check(f"prints {key}", key in out, out[:600])
check("RESYNC carries due=", "due=yes" in out or "due=no" in out)
check("CI_PROBE is one of ok/skip/error", any(f"CI_PROBE={v}" in out for v in ("ok", "skip", "error")))
check("PUBLIC_DRIFT is a known value", any(f"PUBLIC_DRIFT={v}" in out for v in ("ok", "drift", "config", "skip")))
check("worktree line present", "WORKTREES" in out)
check("codex line present", "CODEX_BRANCHES" in out)

# Run from a non-prompt-lab cwd: public check must report skip, not error.
r2 = subprocess.run([SCRIPT], cwd="/tmp", capture_output=True, text=True, timeout=120)
check("outside a repo: still exits 0", r2.returncode == 0, r2.stderr[-400:])
check("outside prompt-lab: PUBLIC_DRIFT=skip", "PUBLIC_DRIFT=skip" in r2.stdout)

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python scripts/test_readup_checks.py`
Expected: FAIL at "script is executable" (file missing) and cascade.

- [ ] **Step 3: Write `workflow/bin/readup-checks.sh`**

```bash
#!/bin/bash
# readup-checks.sh — readup's read-only probes in one call (2026-09-13).
# Prints KEY=VALUE lines / KEY: blocks; ALWAYS exits 0; never pulls, checks out,
# or writes to the tree. /readup interprets the keys (see readup.md).
# Portable: must run on macOS (BSD) and Linux (GNU) userland.

project="$(basename "$PWD")"
in_repo=0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && in_repo=1

# --- 2. remote check (no pull) ------------------------------------------------
if [ "$in_repo" = 1 ]; then
  git fetch --quiet --all --prune 2>/dev/null
  echo "REMOTE=$(git status -sb 2>/dev/null | head -1)"
  echo "TRACKING:"
  git for-each-ref --format='%(refname:short) %(upstream:short) %(upstream:track)' refs/heads | awk '$3 != "" {print "  " $0}'
  echo "REMOTE_ONLY:"
  git branch -r --no-merged 2>/dev/null | grep -v HEAD | sed 's/^/  /'
  # --- 4. other agents --------------------------------------------------------
  wt="$(git worktree list 2>/dev/null)"
  if [ "$(printf '%s\n' "$wt" | wc -l | tr -d ' ')" -gt 1 ]; then
    echo "WORKTREES:"; printf '%s\n' "$wt" | sed 's/^/  /'
  else
    echo "WORKTREES=main-only"
  fi
  cx="$(git branch --list 'codex/*' 2>/dev/null; git branch -r --list 'origin/codex/*' 2>/dev/null)"
  if [ -n "$(printf '%s' "$cx" | tr -d '[:space:]')" ]; then
    echo "CODEX_BRANCHES:"; printf '%s\n' "$cx" | sed 's/^/  /'
  else
    echo "CODEX_BRANCHES=none"
  fi
else
  echo "REMOTE=not-a-git-repo"; echo "WORKTREES=main-only"; echo "CODEX_BRANCHES=none"
fi

# --- 5. resync marker --------------------------------------------------------
marker="$HOME/.claude/state/resync-$project.touch"
if [ -f "$marker" ] && [ "$in_repo" = 1 ]; then
  mt="$(stat -f %m "$marker" 2>/dev/null || stat -c %Y "$marker" 2>/dev/null || echo 0)"
  age_h=$(( ($(date +%s) - mt) / 3600 ))
  commits_since="$(git log --oneline --since="@$mt" 2>/dev/null | wc -l | tr -d ' ')"
else
  age_h=9999; commits_since=9999
fi
due=no; [ "$age_h" -ge 48 ] && [ "$commits_since" -gt 3 ] && due=yes
echo "RESYNC=age_h=$age_h commits_since=$commits_since due=$due"

# --- 6. shared-conventions drift (check only) --------------------------------
conv() {  # $1 = file → in sync | drift | missing | absent
  local f="$1" out
  if [ -x "$HOME/.claude/bin/sync-shared-md.sh" ]; then
    out="$("$HOME/.claude/bin/sync-shared-md.sh" --check "./$f" 2>&1 | head -1)"
    printf '%s' "${out%%:*}"
  else
    printf 'skip'
  fi
}
echo "CONVENTIONS_CLAUDE=$(conv CLAUDE.md)"
echo "CONVENTIONS_AGENTS=$(conv AGENTS.md)"

# --- 7. flush handoff channel -------------------------------------------------
if [ -d "$HOME/src/.handoff/.git" ] && [ -x "$HOME/.claude/bin/handoff.sh" ]; then
  "$HOME/.claude/bin/handoff.sh" sync >/dev/null 2>&1
  case $? in 0) echo "HANDOFF_SYNC=ok" ;; 3) echo "HANDOFF_SYNC=conflict" ;; 4) echo "HANDOFF_SYNC=offline" ;; *) echo "HANDOFF_SYNC=error" ;; esac
else
  echo "HANDOFF_SYNC=absent"
fi

# --- 8. CI health --------------------------------------------------------------
if [ "$in_repo" != 1 ]; then
  echo "CI_PROBE=skip reason=not-a-git-repo"
elif ! command -v gh >/dev/null 2>&1; then
  echo "CI_PROBE=skip reason=gh-not-installed"
elif ! gh auth status >/dev/null 2>&1; then
  echo "CI_PROBE=skip reason=not-authenticated"
else
  default_branch="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
  default_branch="${default_branch:-main}"
  ci_fields=status,conclusion,name,displayTitle,createdAt,headSha,url
  # Retry once: the session's first gh call can fail on a cold keychain lookup.
  ci_out="$(gh run list --branch "$default_branch" --limit 5 --json "$ci_fields" 2>&1)" \
    || ci_out="$(gh run list --branch "$default_branch" --limit 5 --json "$ci_fields" 2>&1)"
  if [ $? -ne 0 ]; then
    echo "CI_PROBE=error"; printf '%s\n' "$ci_out" | head -3 | sed 's/^/  /'
  else
    echo "CI_PROBE=ok"; echo "CI_MAIN:"; printf '%s\n' "$ci_out" | sed 's/^/  /'
    if [ "$ci_out" = "[]" ] && ls .github/workflows/*.y*ml >/dev/null 2>&1; then
      echo "CI_PROBE_NOTE=workflow-files-exist-but-no-runs"
    fi
    current_branch="$(git branch --show-current)"
    if [ -n "$current_branch" ] && [ "$current_branch" != "$default_branch" ]; then
      echo "CI_BRANCH:"
      gh run list --branch "$current_branch" --limit 3 --json status,conclusion,name,displayTitle,createdAt,url 2>/dev/null | sed 's/^/  /'
    fi
  fi
fi

# --- 9. public-data drift (prompt-lab only) -----------------------------------
if [ "$project" = "prompt-lab" ] && [ -f scripts/check_public_allowlist.py ]; then
  py=python3; [ -x .venv/bin/python ] && py=.venv/bin/python
  pub_out="$("$py" scripts/check_public_allowlist.py 2>&1)"; rc=$?
  case $rc in 0) echo "PUBLIC_DRIFT=ok" ;; 1) echo "PUBLIC_DRIFT=drift" ;; 2) echo "PUBLIC_DRIFT=config" ;; *) echo "PUBLIC_DRIFT=error" ;; esac
  [ $rc -ne 0 ] && printf '%s\n' "$pub_out" | sed 's/^/  /'
else
  echo "PUBLIC_DRIFT=skip"
fi
exit 0
```

`chmod +x workflow/bin/readup-checks.sh`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python scripts/test_readup_checks.py`
Expected: all PASS. If `gh` is slow, the 120 s timeout still holds; note real runtime in the commit message.

- [ ] **Step 5: Rewrite `readup.md` to use it**

Edit `workflow/commands/readup.md`:

1. In "Do (in parallel)", item 2 becomes: `2. Run the bundled read-only checks (fetch, branch tracking, worktrees, codex branches, resync marker, conventions drift, handoff flush, CI, public drift) in ONE call: \`~/.claude/bin/readup-checks.sh\`. It never pulls or modifies the tree. Interpret its output with the table under "Interpreting readup-checks" below.`
2. Item 4 keeps ONLY the `ListAgents` sentences (the tool call the script cannot make) and the rule "`ListAgents` missing or erroring → skip silently, never block session start."
3. Delete sections `## 5. Auto-resync if drift likely`, `## 6. Check shared-conventions drift`, `## 7. Flush the cross-repo handoff channel`, `## 8. Check CI health`, `## 9. Check public-data drift` and replace with one section `## 5. Interpreting readup-checks` containing this, verbatim (it preserves every behavioural rule those sections carried):

```markdown
## 5. Interpreting readup-checks

One line of behaviour per key. Anything not listed here → say nothing.

- `REMOTE` / `TRACKING` / `REMOTE_ONLY`: any branch ahead/behind, or an unfamiliar remote-only branch → flag it in the summary so the user can decide whether to `git pull --rebase` / `git checkout` manually. Clean → silent.
- `WORKTREES:` block (more than the main checkout) → another agent may be mid-task; flag it with its branch. `CODEX_BRANCHES:` block → Codex has touched or is touching this repo (it always works on `codex/<desc>`); flag it. Combine with `ListAgents` from item 4.
- `RESYNC=… due=yes` → invoke `/resync --light` inline and fold its findings into the summary (no separate wall of text). `due=no` → silent.
- `CONVENTIONS_CLAUDE` / `CONVENTIONS_AGENTS`: `drift` or `missing` → one line per file offering the exact fix `~/.claude/bin/sync-shared-md.sh --apply ./<file>` (review the `git diff`, then commit). Never apply automatically — materializing into a checked-in file is the user's call. `in sync` / `absent` / `skip` → silent.
- `HANDOFF_SYNC=conflict` or `offline` → one line; the entry stays safe locally (conflict: resolve in `~/src/.handoff`; offline: re-run `handoff.sh sync` later). `ok` / `absent` → silent.
- `CI_PROBE=skip` → silent. `CI_PROBE=error` → say ONE line: "couldn't read CI status (`<first indented line>`)". Never report an error as "no CI configured" — you don't know. `CI_PROBE=ok` with `[]` and no `CI_PROBE_NOTE` → no CI, silent. `CI_PROBE_NOTE=workflow-files-exist-but-no-runs` → flag one line (Actions disabled, or every trigger filtered out). Latest run in `CI_MAIN:` (and `CI_BRANCH:` if present) with `conclusion: "success"` or still `in_progress`/`queued` → silent. `failure` / `cancelled` / `timed_out` → ⚠️ line in the summary naming workflow, branch, and how long it's been red (walk `createdAt`/`conclusion` back to the last success). If the workflow YAML has a job with `needs: test`, say so — a red `test` starves it and it shows as *skipped*, never failed. Offer `gh run view <run-id> --log-failed`; don't auto-fix.
- `PUBLIC_DRIFT=drift` → **urgent** ⚠️: a project that should be private has rows on the live unauthenticated endpoint. List the project(s)/table(s) from the indented lines and point at `.venv/bin/python scripts/unpublish_public.py <project> --apply` (venv python — the script imports `anthropic` via `claude_api`), or re-run the audit with `--fix`. `config` → flag once: `docs/public-allowlist.txt` missing or empty (a config problem, distinct from drift). `ok` / `skip` → silent.
```

4. In "Then", keep the ordering rule "drift first, then broken CI, then stale branches" as it stands.
5. Keep section 4 (lazy synthesis) untouched.

- [ ] **Step 6: Extend `scripts/test_readup_md_structure.py`**

Append before its exit block:

```python
check("readup invokes readup-checks.sh", "readup-checks.sh" in content)
check("readup no longer inlines the CI probe", "ci_fields=" not in content)
check("readup keeps the CI error rule", "couldn't read CI status" in content)
check("readup keeps the public-drift fix pointer", "unpublish_public.py" in content)
check("readup keeps ListAgents", "ListAgents" in content)
check("readup keeps lazy synthesis", "unsummarized-context" in content)
check("readup is materially smaller", len(content) < 9000, f"{len(content)} bytes")
```

Run: `.venv/bin/python scripts/test_readup_md_structure.py` and `.venv/bin/python scripts/test_readup_checks.py`. Expected: all PASS. (The existing checks for `sync-shared-md.sh`, `session-context.sh`, `CLAUDE.md`, `AGENTS.md` strings must still pass — the interpretation table mentions all four.)

- [ ] **Step 7: Commit**

```bash
git add workflow/bin/readup-checks.sh scripts/test_readup_checks.py workflow/commands/readup.md scripts/test_readup_md_structure.py
git commit -m "readup: bundle seven read-only probes into readup-checks.sh (one call, not ten)"
```

---

### Task 3: Trim CLAUDE.md, move narrative to `docs/history.md`

**Files:**
- Modify: `CLAUDE.md` (sections `### Open`, `### Traps that cost real time`, `### Settled — don't re-litigate`; leave `## Run`…`## Cross-agent handoff`, `### The failure shape…`, `### Invariants`, `### Testing`, and everything from `## Shared conventions` down untouched)
- Modify: `docs/history.md` (insert new entries directly under `## Build log (newest first)`, each headed `### <original bold lead-in> (moved 2026-09-13)`, newest-dated first)

**Interfaces:**
- Produces: `CLAUDE.md` ≤ 28,000 bytes (from 49,315). Every paragraph removed from CLAUDE.md appears verbatim in `docs/history.md` — no paraphrasing on the history side; the history file is an archive.

**Rules (this is a judgment task; apply them literally):**

1. **Open items** — for each bold-led block, keep in CLAUDE.md only: what is still open, the blocker, the decision already made (one line, with date), and file pointers. Everything narrating *how it got there* moves. Concrete per-item instructions:
   - *Codex workflow checkpoint (l.66-93)*: keep, compress to ≤ 10 lines: branch, `work`/`cx` state, the iTerm -10000 blocker and "diagnose before claiming it works", the three next-session scope items, the pointer to `docs/codex-workflow-roadmap.md` and `docs/codex-workflow-checkpoint.md`, the "do not trust `gc-read.sh current-session` from Codex" warning with rows 573/574. Move the install.sh review narrative and the title-setter narrative.
   - *1Password preference (l.95-100)*: keep as-is (it is a rule, 5 lines).
   - *Dual-agent commands installed (l.102-111)*: keep 3 lines: "still open: one real `/prompts:readup` + `/prompts:handoff` from Codex in songpath or musicforge (needs a session restart); that first Codex `/handoff` registers the project on the dashboard." Move the rest.
   - *Garm HARDEN-THEN-FREEZE (l.113-142)*: keep 4 lines: decision + date, `GARM_GATING` off via Vercel env var (code default is `on` — check `vercel env ls`), grant seeding deferred, revisit trigger. Move the harden-asks and the PR #54 paragraph. Add to **Traps** one line: "`web/garm_helper.py` defaults `GARM_GATING` to `on`; the freeze is a Vercel env var, so an env reset silently fails closed."
   - *Resend STAYING ON PRO (l.144-172)*: move the whole block; add to **Settled** 3 lines: decision + date + the 11-not-37 domain count; return-path `send.` subdomains don't consume a slot but `span.`/`mail.` subdomains do; `musicforge.org` SPF must be *extended* (`include:icloud.com`), never replaced.
   - *Nightly wake/DNS + two consequences + pipeline steps (l.174-209)*: keep the "Still outstanding: step 2's sleeping-host test" paragraph (compress to 6 lines, keep the `--- network: resolved after Ns ---` evidence line) and the 2-line "first real morning email is the acceptance test". Move the "two consequences" to history and add to **Traps** two one-liners: "escalation is one day late for a single dead night (the 2→1 age rule is what makes two dead nights escalate on time — don't 'simplify' it back)" and "a bad night stays red up to 7 days; re-running a date adds a row, never clears one".
   - *mini-rescue (l.211-220)*: keep 3 lines (13 repos, walk at leisure, folder-emptying is the meter, freevite/roll-your-own/skitrack deliberately unpushed). Move the rest.
   - *garm Neon CU (l.222-233) + byside follow-up (l.235-247)*: replace both with one 4-line open item: "Check September CU numbers for garm (`neon-bole-tree`) and byside — both were burned by prompt-lab's own 5-min deep health poll never letting Neon's free tier autosuspend; fixed 2026-08-14 (byside) and 2026-08-18 (garm), nothing alarms on the number." Move both narratives. The transferable rule already lives in `scripts/uptimerobot.py`; add to **Traps** one line if not already present: "deep coverage over an autosuspending DB needs a poll interval longer than the suspend window, or the check keeps the DB warm and reports that the warm DB answers."
   - *Pi inventory + closet move (l.249-264)*: keep 3 lines: pointer to `docs/pi-inventory.md` and the three non-prompt-lab leftovers as a one-line list. Move the rest.
   - *Copy review (l.266-274)*, *project-name follow-ups (l.276-282)*, *ACTIVE·N (l.284-291)*: keep, each compressed to ≤ 5 lines preserving the "track answered items, not batches" warning and the two `web/index.html` line refs.
   - *The "Open, from the 2026-08-02 uptime/health thread" bullet list (l.293-323)*: keep every bullet, but cap each at 2 lines; move the sandbox-can't-render explanation and the beacon history to history.
2. **Traps** (l.396-548): every trap becomes ≤ 3 lines: the rule + the one-line reason. Traps currently over 3 lines (Cloudflare bot protection, the two sampling traps, wake/DNS evidence erasure, `vercel env add`, `op inject`, the three Vercel diagnostics, `tail -r`) keep their rule and move their narrative to history under a `### Traps narrative (moved 2026-09-13)` heading, with each original trap paragraph verbatim as a bullet.
3. **Settled** (l.567-639): same ≤ 3-line rule; move longer narrative (UptimeRobot API facts, OAuth rejected alternatives, dual-agent commands design) under `### Settled narrative (moved 2026-09-13)`.
4. Do not touch `### The failure shape…`, `### Invariants`, `### Testing`, `## Shared conventions`, or anything above `## Next Steps`.
5. Do not rewrite content on the history side. Copy the removed paragraphs verbatim under the new headings. The history file's own intro paragraph already explains the convention.

- [ ] **Step 1: Record the baseline**

Run: `wc -c CLAUDE.md docs/history.md; cp CLAUDE.md /tmp/claude-md-before.md`
Expected: `49315 CLAUDE.md`.

- [ ] **Step 2: Apply the rules above**

Edit `CLAUDE.md` and `docs/history.md` per the rules. Work top to bottom through `### Open`, then Traps, then Settled.

- [ ] **Step 3: Verify**

Run:
```bash
wc -c CLAUDE.md                                           # expected ≤ 28000
.venv/bin/python scripts/test_sync_shared_md.py           # conventions block untouched
~/.claude/bin/sync-shared-md.sh --check ./CLAUDE.md        # expected: in sync
grep -c '(moved 2026-09-13)' docs/history.md               # expected ≥ 10
# Every sentence that left CLAUDE.md must exist somewhere in CLAUDE.md or history.md:
.venv/bin/python - <<'EOF'
import re
before = open('/tmp/claude-md-before.md').read()
after = open('CLAUDE.md').read() + open('docs/history.md').read()
lost = []
for para in re.split(r'\n\s*\n', before):
    p = para.strip()
    if len(p) < 120 or p.startswith('#'):
        continue
    # a paragraph counts as preserved if its first 80 chars survive somewhere
    if p[:80] not in after:
        lost.append(p[:80])
print(f"{len(lost)} paragraph(s) whose opening 80 chars appear in neither file:")
for l in lost: print("  ", l)
EOF
```
Expected: the "lost" list contains ONLY paragraphs you deliberately compressed in place (the Open items rewritten to ≤ N lines). List each one in the commit message body as "compressed in place: <first words>". If a lost paragraph is one you intended to *move*, it is not in history — fix it.

- [ ] **Step 4: Run the full test suite**

Run: `for f in scripts/test_*.py; do .venv/bin/python "$f" >/dev/null 2>&1 || echo "FAIL $f"; done`
Expected: no `FAIL` lines.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/history.md
git commit -m "CLAUDE.md: move settled narrative to docs/history.md (49 KB → <28 KB)"
```
Body: the "compressed in place" list from Step 3.

---

### Task 4: Weekly CLAUDE.md trim step in `/handoff`

**Files:**
- Modify: `workflow/commands/handoff.md` (insert new section `## 2.5 CLAUDE.md size check (weekly)` between `## 2. Do in parallel` and `## 3. Synthesize daily summary`)
- Modify: `scripts/test_handoff_md_structure.py` (add checks)

**Interfaces:**
- Produces: state marker `~/.claude/state/claude-trim-<project>.touch` (same directory and naming shape as `resync-<project>.touch`). Threshold constants live in the command text: `30000` bytes, `7` days.

- [ ] **Step 1: Write the failing test**

Append to `scripts/test_handoff_md_structure.py` before its exit block:

```python
check("handoff has the weekly CLAUDE.md size check", "## 2.5 CLAUDE.md size check" in content)
check("size check uses the state marker", "claude-trim-" in content)
check("size check names the history file", "docs/history.md" in content)
check("size check has a GNU stat fallback", "stat -c %Y" in content)
check("size check protects the conventions block", "SHARED-CONVENTIONS" in content)
check("size check runs before daily summary", content.index("## 2.5 CLAUDE.md size check") < content.index("## 3. Synthesize daily summary"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python scripts/test_handoff_md_structure.py`
Expected: FAIL on all six new checks.

- [ ] **Step 3: Insert the section into `handoff.md`**

Insert after the `## 2. Do in parallel` bullets (before `## 3. Synthesize daily summary`):

````markdown
## 2.5 CLAUDE.md size check (weekly)

CLAUDE.md is loaded into every session; narrative that has settled belongs in `docs/history.md`, not in the brief. Check whether a trim is due (oversized AND not trimmed in the last 7 days):

```bash
f=CLAUDE.md; m=~/.claude/state/claude-trim-$(basename "$PWD").touch
size=$(wc -c < "$f" 2>/dev/null | tr -d ' ' || echo 0)
mt=$(stat -f %m "$m" 2>/dev/null || stat -c %Y "$m" 2>/dev/null || echo 0)
echo "claude_md_bytes=${size:-0} trim_age_d=$(( ($(date +%s) - mt) / 86400 ))"
```

- No `CLAUDE.md` in this repo, or `claude_md_bytes <= 30000` → skip silently.
- `claude_md_bytes > 30000` and `trim_age_d < 7` → skip silently (trimmed recently; let it settle).
- `claude_md_bytes > 30000` and `trim_age_d >= 7` → trim now, then touch the marker:
  1. Move settled narrative out: any paragraph in Next Steps / Traps / Settled that explains *how something came to be* (a fix's story, an incident timeline, rejected alternatives) goes verbatim into `docs/history.md` under a heading `### <its lead-in> (moved YYYY-MM-DD)` at the top of the build log, newest first. Create `docs/history.md` with a one-paragraph intro if the repo has none.
  2. Keep in CLAUDE.md, each at ≤ 3 lines: what is still open, the decision made (with date), invariants, traps as rule + one-line reason, file pointers.
  3. Never edit between the `SHARED-CONVENTIONS` markers; never remove an open item, an invariant, or a trap — compress, don't delete.
  4. `mkdir -p ~/.claude/state && touch "$m"`, then tell the user in one line what moved and the before/after byte counts. The doc commit in step 5 carries it.
````

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python scripts/test_handoff_md_structure.py`
Expected: all PASS. Then run the snippet by hand from the repo root:
`bash -c '<the code block>'` — expected output shape `claude_md_bytes=NNNNN trim_age_d=NNNN` (large age: marker absent).

- [ ] **Step 5: Seed the marker for this repo (Task 3 just trimmed it)**

Run: `mkdir -p ~/.claude/state && touch ~/.claude/state/claude-trim-prompt-lab.touch`

- [ ] **Step 6: Commit**

```bash
git add workflow/commands/handoff.md scripts/test_handoff_md_structure.py
git commit -m "handoff: weekly size-gated CLAUDE.md trim into docs/history.md"
```

---

### After all tasks (controller, not a subagent)

- Run the whole suite once: `for f in scripts/test_*.py; do .venv/bin/python "$f" >/dev/null 2>&1 || echo "FAIL $f"; done`.
- Nothing is live until Nico runs `workflow/install.sh` (copies `workflow/bin/*` → `~/.claude/bin/` and `workflow/commands/*` → `~/.claude/commands/` + `~/.codex/prompts/`). Do NOT run it. Tell Nico, and give the diff-sweep to verify:
  `for f in workflow/bin/*.sh; do diff -q "$f" ~/.claude/bin/$(basename "$f"); done; for f in workflow/commands/*.md; do diff -q "$f" ~/.claude/commands/$(basename "$f"); done`
- Note `main` is 16 commits ahead of `origin/main` (unpushed) — separate from this work, Nico's call.

---

**Execution ruling (2026-09-13):** Task 3 landed CLAUDE.md at 32,492 bytes; rule 4's protected sections and the ≤3-line floor on 40 traps + 16 settled items make 28,000 unreachable without deleting rules. Accepted. Task 4's threshold was raised from 30000 to 35000 bytes so the weekly step does not fire on a file already at its floor.
