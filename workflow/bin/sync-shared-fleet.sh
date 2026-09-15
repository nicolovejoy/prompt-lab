#!/bin/bash
# sync-shared-fleet.sh — inventory shared-conventions state across sibling repos.
#
# Default mode is read-only. --apply refreshes only files whose verified block is
# behind or whose existing file has no block. It never creates an absent file,
# overwrites a tampered block, commits, or pushes.
#
# Usage: sync-shared-fleet.sh [--check|--apply] [ROOT]
# ROOT defaults to ~/src. SHARED_FLEET_ROOT and SYNC_SHARED_MD may override the
# root and single-file helper for isolated tests.

set -u

MODE="${1:---check}"
ROOT="${2:-${SHARED_FLEET_ROOT:-$HOME/src}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNC="${SYNC_SHARED_MD:-$SCRIPT_DIR/sync-shared-md.sh}"

case "$MODE" in
    --check|--apply) ;;
    *)
        echo "usage: sync-shared-fleet.sh [--check|--apply] [ROOT]" >&2
        exit 64
        ;;
esac

if [ ! -d "$ROOT" ]; then
    echo "sync-shared-fleet: root does not exist: $ROOT" >&2
    exit 2
fi
if [ ! -x "$SYNC" ]; then
    echo "sync-shared-fleet: helper is not executable: $SYNC" >&2
    exit 3
fi

problems=0
found=0
for repo in "$ROOT"/*; do
    [ -d "$repo" ] || continue
    git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || continue
    found=1
    repo_name="$(basename "$repo")"
    for filename in CLAUDE.md AGENTS.md; do
        target="$repo/$filename"
        output="$("$SYNC" --check "$target" 2>&1)"
        state="${output%%:*}"
        [ "$state" = "in sync" ] && state=current
        case "$state" in
            current|behind|tampered|missing|absent) ;;
            *) state=unknown; problems=1 ;;
        esac

        if [ "$MODE" = "--apply" ] && { [ "$state" = behind ] || [ "$state" = missing ]; }; then
            apply_output="$("$SYNC" --apply "$target" 2>&1)"
            if [ $? -eq 0 ]; then
                printf '%s\t%s\t%s -> updated\n' "$repo_name" "$filename" "$state"
            else
                printf '%s\t%s\terror: %s\n' "$repo_name" "$filename" "$apply_output"
                problems=1
            fi
        else
            printf '%s\t%s\t%s\n' "$repo_name" "$filename" "$state"
            [ "$state" = tampered ] && problems=1
        fi
    done
done

if [ "$found" = 0 ]; then
    echo "sync-shared-fleet: no git repositories found under $ROOT" >&2
fi
exit "$problems"
