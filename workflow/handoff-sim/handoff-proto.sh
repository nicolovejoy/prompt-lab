#!/bin/bash
# Prototype of the shipped workflow/bin/handoff.sh, written ONLY to pressure-test
# the design before building. Portable to macOS bash 3.2 (no flock, no timeout).
#
#   HANDOFF_REPO=<dir> handoff-proto.sh append <file> <text>
#   HANDOFF_REPO=<dir> handoff-proto.sh sync
#
# Exit codes: 0 ok | 3 conflict (kept local, not pushed) | 4 offline/push-failed
#             (kept local) | 5 lock timeout | 64 usage
set -u

REPO="${HANDOFF_REPO:?set HANDOFF_REPO}"
LOCKDIR="$REPO/.handoff.lock.d"
git_h() { git -C "$REPO" "$@"; }

# --- Portable mutex (mkdir is atomic). Serializes same-machine concurrent runs. ---
acquire_lock() {
  local tries=0
  until mkdir "$LOCKDIR" 2>/dev/null; do
    tries=$((tries + 1))
    [ "$tries" -ge 100 ] && return 1   # ~10s at 0.1s
    sleep 0.1
  done
  return 0
}
release_lock() { rmdir "$LOCKDIR" 2>/dev/null || true; }

# --- Rebase local commit(s) onto remote, then push. Distinguish a real merge
#     conflict (rebase in progress) from an unreachable remote (offline). ---
sync_push() {
  local tries=0
  while :; do
    if ! git_h pull --rebase --quiet 2>/dev/null; then
      if [ -d "$REPO/.git/rebase-merge" ] || [ -d "$REPO/.git/rebase-apply" ]; then
        git_h rebase --abort >/dev/null 2>&1 || true
        echo "CONFLICT: rebase failed; local commit kept, not pushed. Resolve manually." >&2
        return 3
      fi
      echo "OFFLINE: remote unreachable; local commit kept, not pushed. Re-run 'sync' later." >&2
      return 4
    fi
    if git_h push --quiet 2>/dev/null; then
      return 0
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 3 ]; then
      echo "PUSH-FAILED after retries; local commit kept." >&2
      return 4
    fi
  done
}

cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  append)
    file="${1:?file}"; text="${2:?text}"
    acquire_lock || { echo "LOCK-TIMEOUT" >&2; exit 5; }
    trap release_lock EXIT
    printf '%s\n' "$text" >> "$REPO/$file"
    git_h add "$file"
    git_h commit -m "handoff: append to $file" --quiet
    sync_push; rc=$?
    exit $rc
    ;;
  sync)
    acquire_lock || { echo "LOCK-TIMEOUT" >&2; exit 5; }
    trap release_lock EXIT
    git_h add -A
    git_h diff --cached --quiet 2>/dev/null || git_h commit -m "handoff: sync" --quiet
    sync_push; rc=$?
    exit $rc
    ;;
  *)
    echo "usage: handoff {append <file> <text>|sync}" >&2; exit 64 ;;
esac
