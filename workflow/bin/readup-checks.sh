#!/bin/bash
# readup-checks.sh — readup's read-only probes in one call (2026-09-13).
# Prints KEY=VALUE lines / KEY: blocks; ALWAYS exits 0; never pulls, checks out,
# or writes to the tree. /readup interprets the keys (see readup.md).
# Portable: must run on macOS (BSD) and Linux (GNU) userland.

RC_BIN_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
if [ -f "$RC_BIN_DIR/_gc_project.sh" ]; then
  # shellcheck source=./_gc_project.sh
  . "$RC_BIN_DIR/_gc_project.sh"
  project="$(gc_resolve_project "$PWD")"
else
  project="$(basename "$PWD")"
  echo "PROJECT_RESOLVER=fallback-basename"
fi
echo "PROJECT=$project"
in_repo=0; git_rc=0
git_err="$(git rev-parse --is-inside-work-tree 2>&1 >/dev/null)" || git_rc=$?
[ "$git_rc" -eq 0 ] && in_repo=1
# git answers 128 for "not a repository" and for one it cannot read (a damaged
# .git, a pruned worktree record). With a .git entry here or above, or any other
# failure, the checkout is unreadable: that is not "not a git repo".
unreadable=0; skip_reason=not-a-git-repo
if [ "$in_repo" != 1 ] && command -v git >/dev/null 2>&1; then
  if [ "$git_rc" -ne 128 ]; then
    unreadable=1
  elif command -v gc_git_entry_root >/dev/null 2>&1 && gc_git_entry_root "$PWD" >/dev/null; then
    unreadable=1
  fi
  [ "$unreadable" = 1 ] && skip_reason=repo-unreadable
fi
# A Fossil checkout (ear-worm, 2026-11-20) is a project too, just not a git one.
fossil_root=""
if [ "$in_repo" != 1 ] && [ "$unreadable" != 1 ] && command -v gc_fossil_root >/dev/null 2>&1; then
  fossil_root="$(gc_fossil_root "$PWD")" || fossil_root=""
fi

# --- 2. remote check (no pull) ------------------------------------------------
if [ "$in_repo" = 1 ]; then
  cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
  fetch_out="$(git fetch --quiet --all --prune 2>&1)"; fetch_rc=$?
  if [ "$fetch_rc" -eq 0 ]; then
    echo "REMOTE=$(git status -sb 2>/dev/null | head -1)"
    echo "TRACKING:"
    git for-each-ref --format='%(refname:short) %(upstream:short) %(upstream:track)' refs/heads | awk '$3 != "" {print "  " $0}'
    echo "REMOTE_ONLY:"
    git branch -r --no-merged 2>/dev/null | grep -v HEAD | sed 's/^/  /'
  else
    echo "REMOTE=error"
    printf '%s\n' "$fetch_out" | head -3 | sed 's/^/  fetch: /'
    echo "TRACKING=unavailable (fetch failed; local tracking data may be stale)"
    echo "REMOTE_ONLY=unavailable (fetch failed)"
  fi
  # --- 4. other agents --------------------------------------------------------
  wt="$(git worktree list 2>/dev/null)"
  if [ "$(printf '%s\n' "$wt" | wc -l | tr -d ' ')" -gt 1 ]; then
    echo "WORKTREES:"; printf '%s\n' "$wt" | sed 's/^/  /'
  else
    echo "WORKTREES=main-only"
  fi
elif [ "$unreadable" = 1 ]; then
  echo "REMOTE=unreadable"
  printf '%s\n' "git exit $git_rc: $git_err" | head -1 | sed 's/^/  /'
  echo "WORKTREES=unavailable (git could not read this checkout)"
elif [ -n "$fossil_root" ]; then
  # Nothing here talks to a Fossil remote yet, so say "unchecked", never "clean".
  cd "$fossil_root" || true
  echo "REMOTE=fossil-unchecked"; echo "WORKTREES=main-only"
else
  echo "REMOTE=not-a-git-repo"; echo "WORKTREES=main-only"
fi

# --- 5. resync marker --------------------------------------------------------
marker="$HOME/.claude/state/resync-$project.touch"
if [ -f "$marker" ] && [ "$in_repo" = 1 ]; then
  # GNU form first: see claude-md-size.sh for why the other order breaks on Linux.
  mt="$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo 0)"
  age_h=$(( ($(date +%s) - mt) / 3600 ))
  commits_since="$(git log --oneline --since="@$mt" 2>/dev/null | wc -l | tr -d ' ')"
else
  age_h=9999; commits_since=9999
fi
due=no; [ "$age_h" -ge 48 ] && [ "$commits_since" -gt 3 ] && due=yes
if [ "$in_repo" = 1 ]; then
  echo "RESYNC=age_h=$age_h commits_since=$commits_since due=$due"
else
  # /resync reads git history and GitHub issues. Outside a git repo the 9999s
  # above would read as "due" at every session start of a Fossil checkout.
  echo "RESYNC=skip reason=$skip_reason due=no"
fi

# --- 6. shared-conventions drift (check only) --------------------------------
conv() {  # $1 = file → in sync | behind | tampered | missing | absent
  local f="$1" out
  if [ -x "$HOME/.claude/bin/sync-shared-md.sh" ]; then
    out="$("$HOME/.claude/bin/sync-shared-md.sh" --check "./$f" 2>&1 | head -1)"
    out="${out%%:*}"
    printf '%s' "${out:-unknown}"
  else
    printf 'skip'
  fi
}
# Some repos keep project instructions at .claude/CLAUDE.md instead of the root.
claude_md=CLAUDE.md
[ ! -f CLAUDE.md ] && [ -f .claude/CLAUDE.md ] && claude_md=.claude/CLAUDE.md
echo "CONVENTIONS_CLAUDE=$(conv "$claude_md")"

# --- 6b. CLAUDE.md size (reminder only; nothing here edits the file) ----------
if [ -x "$RC_BIN_DIR/claude-md-size.sh" ]; then
  echo "CLAUDE_SIZE=$("$RC_BIN_DIR/claude-md-size.sh" "$claude_md")"
else
  echo "CLAUDE_SIZE=skip"
fi

# --- 7. flush handoff channel -------------------------------------------------
if [ -d "$HOME/src/.handoff/.git" ] && [ -x "$HOME/.claude/bin/handoff.sh" ]; then
  "$HOME/.claude/bin/handoff.sh" sync >/dev/null 2>&1
  # $? must be read on the very next line — do not insert anything between.
  case $? in 0) echo "HANDOFF_SYNC=ok" ;; 3) echo "HANDOFF_SYNC=conflict" ;; 4) echo "HANDOFF_SYNC=offline" ;; *) echo "HANDOFF_SYNC=error" ;; esac
else
  echo "HANDOFF_SYNC=absent"
fi

# --- 8. CI health --------------------------------------------------------------
if [ "$in_repo" != 1 ]; then
  echo "CI_PROBE=skip reason=$skip_reason"
elif ! command -v gh >/dev/null 2>&1; then
  echo "CI_PROBE=skip reason=gh-not-installed"
elif ! gh auth status >/dev/null 2>&1; then
  echo "CI_PROBE=error"
  echo "  Could not verify GitHub authentication; check gh auth status."
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
  case $rc in
    0) echo "PUBLIC_DRIFT=ok" ;;
    10) echo "PUBLIC_DRIFT=drift" ;;
    2) echo "PUBLIC_DRIFT=config" ;;
    3) echo "PUBLIC_DRIFT=incomplete" ;;
    *) echo "PUBLIC_DRIFT=error" ;;
  esac
  [ $rc -ne 0 ] && printf '%s\n' "$pub_out" | sed 's/^/  /'
else
  echo "PUBLIC_DRIFT=skip"
fi
exit 0
