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
