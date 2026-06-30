#!/bin/bash
# handoff.sh — cross-repo coordination log writer (issue #7).
#
# Wraps the git repo at ~/src/.handoff (override with HANDOFF_REPO). Provides an
# atomic append+push, a deferred sync, and a time-boxed best-effort pull for the
# session-start hook. Portable to macOS bash 3.2 + BSD userland (no flock, no
# `timeout`/`gtimeout`, no associative arrays).
#
#   handoff.sh append <file> <text>   # add entry to top of ## Active, commit, push
#   handoff.sh sync                   # commit any pending change, pull-rebase, push
#   handoff.sh pull                   # best-effort time-boxed pull; ALWAYS exits 0
#
# Exit codes: 0 ok | 3 conflict (kept local, not pushed) | 4 offline/push-failed
#             (kept local) | 5 lock timeout | 64 usage. `pull` is exempt — always 0.
#
# Design + pressure test: docs/handoff-repo-plan.md, workflow/handoff-sim/.
set -u

REPO="${HANDOFF_REPO:-$HOME/src/.handoff}"
LOCKDIR="$REPO/.handoff.lock.d"
LOCK_STALE_SECS=120          # reclaim a lock older than this (a crashed run)
PULL_TIMEOUT_SECS=3          # cap on the hook pull (hook budget is 5s) — never block a session

git_h() { git -C "$REPO" "$@"; }

# --- Portable mutex via atomic mkdir, with stale-lock recovery. ----------------
acquire_lock() {
  local tries=0
  until mkdir "$LOCKDIR" 2>/dev/null; do
    # Reclaim a stale lock left by a crashed run (older than LOCK_STALE_SECS).
    if [ -d "$LOCKDIR" ] && [ -z "$(find "$LOCKDIR" -prune -mmin -"$(( (LOCK_STALE_SECS + 59) / 60 ))" 2>/dev/null)" ]; then
      rmdir "$LOCKDIR" 2>/dev/null || true
      continue
    fi
    tries=$((tries + 1))
    [ "$tries" -ge 100 ] && return 1   # ~10s at 0.1s
    sleep 0.1
  done
  # Keep the lock dir EMPTY: `git add -A` skips empty dirs, so a held lock never
  # pollutes a `sync` commit. Stale recovery keys off the dir's mtime, not a pid.
  return 0
}
release_lock() { rmdir "$LOCKDIR" 2>/dev/null || true; }

# --- Portable timeout: background the command, watchdog escalates TERM→KILL. ---
run_timeout() {
  local secs="$1"; shift
  "$@" & local pid=$!
  ( sleep "$secs"; kill -TERM "$pid" 2>/dev/null; sleep 2; kill -KILL "$pid" 2>/dev/null ) & local w=$!
  wait "$pid" 2>/dev/null; local rc=$?
  kill -TERM "$w" 2>/dev/null; wait "$w" 2>/dev/null
  return $rc
}

# --- Insert text as a new entry at the TOP of the ## Active section. -----------
#     Honors the files' newest-first convention; falls back to EOF if no such
#     header exists. Uses a head/tail split (NOT awk -v) so multi-line entries
#     work — BSD awk rejects embedded newlines in a -v variable.
insert_after_active() {
  local file="$1" text="$2" tmp line
  tmp="$file.handoff.tmp.$$"
  line="$(grep -n '^## Active' "$file" 2>/dev/null | head -1 | cut -d: -f1)"
  if [ -n "$line" ]; then
    { head -n "$line" "$file"; printf '\n%s\n' "$text"; tail -n +"$((line + 1))" "$file"; } > "$tmp" \
      && mv "$tmp" "$file" || { rm -f "$tmp"; return 1; }
  else
    printf '\n%s\n' "$text" >> "$file"
  fi
}

# --- Rebase local commit(s) onto remote, then push. Distinguish a real merge
#     conflict (rebase in progress) from an unreachable remote (offline). -------
sync_push() {
  local tries=0
  while :; do
    if ! git_h pull --rebase --quiet 2>/dev/null; then
      if [ -d "$REPO/.git/rebase-merge" ] || [ -d "$REPO/.git/rebase-apply" ]; then
        git_h rebase --abort >/dev/null 2>&1 || true
        echo "CONFLICT: rebase failed; local commit kept, not pushed. Resolve manually in $REPO." >&2
        return 3
      fi
      echo "OFFLINE: remote unreachable; local commit kept, not pushed. Re-run 'handoff.sh sync' later." >&2
      return 4
    fi
    if git_h push --quiet 2>/dev/null; then
      return 0
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 3 ]; then
      echo "PUSH-FAILED after retries; local commit kept. Re-run 'handoff.sh sync' later." >&2
      return 4
    fi
  done
}

[ -d "$REPO/.git" ] || { echo "handoff: $REPO is not a git repo (run the issue #7 baseline import first)" >&2; exit 64; }

cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  append)
    file="${1:?usage: handoff.sh append <file> <text>}"
    text="${2:?usage: handoff.sh append <file> <text>}"
    [ -f "$REPO/$file" ] || { echo "handoff: no such file: $file" >&2; exit 64; }
    acquire_lock || { echo "LOCK-TIMEOUT: another handoff write is in progress." >&2; exit 5; }
    trap release_lock EXIT
    insert_after_active "$REPO/$file" "$text" || { echo "handoff: failed to write entry into $file" >&2; exit 1; }
    git_h add "$file"
    if ! git_h commit -m "handoff: append to $file" --quiet; then
      echo "handoff: nothing committed for $file (entry not written?)" >&2; exit 1
    fi
    sync_push; exit $?
    ;;
  sync)
    acquire_lock || { echo "LOCK-TIMEOUT: another handoff write is in progress." >&2; exit 5; }
    trap release_lock EXIT
    git_h add -A
    git_h diff --cached --quiet 2>/dev/null || git_h commit -m "handoff: sync" --quiet
    sync_push; exit $?
    ;;
  pull)
    # Best-effort, time-boxed, ALWAYS graceful — used by the session-start hook.
    # Never blocks a session and never fails it, even offline or mid-conflict.
    run_timeout "$PULL_TIMEOUT_SECS" git -C "$REPO" pull --rebase --autostash --quiet 2>/dev/null
    exit 0
    ;;
  *)
    echo "usage: handoff.sh {append <file> <text>|sync|pull}" >&2; exit 64 ;;
esac
