#!/bin/bash
# sync-shared-fleet.sh — inventory shared-conventions state across sibling repos.
#
# Only CLAUDE.md is managed. AGENTS.md was Codex's copy; Codex is retired
# (2026-10-16), so a leftover AGENTS.md is neither reported nor refreshed.
#
# Default mode is read-only. --apply refreshes only files whose verified block is
# behind or whose existing file has no block. It never creates an absent file,
# overwrites a tampered block, commits, or pushes.
#
# A directory with a .git entry that git cannot read is reported as `unreadable`
# and the run exits nonzero. It is never skipped as if it were a plain directory.
#
# A Fossil checkout (marker file .fslckout, or _FOSSIL_ on older and Windows
# checkouts, directly in the directory: the same marker _gc_project.sh looks
# for) is a fleet member too. Its lines carry a fourth tab-separated column,
# `fossil`. Nothing here asks the VCS anything: the check and apply act on
# CLAUDE.md alone, and git members get no clean-tree or tracked-file test
# either, so Fossil needs no `fossil` binary and gets none. An apply leaves
# the edit uncommitted, as it does in git. Git wins when both apply.
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
    repo_name="$(basename "$repo")"
    filename=CLAUDE.md
    git_rc=0
    vcs_note=""
    git_err="$(git -C "$repo" rev-parse --is-inside-work-tree 2>&1 >/dev/null)" || git_rc=$?
    if [ "$git_rc" -ne 0 ]; then
        if [ ! -e "$repo/.git" ] && [ ! -L "$repo/.git" ]; then
            # No .git entry. A Fossil checkout is a member; anything else is a
            # plain directory. (-L above: -e is false for a dangling symlink.)
            if [ -f "$repo/.fslckout" ] || [ -f "$repo/_FOSSIL_" ]; then
                vcs_note="$(printf '\tfossil')"
            else
                continue
            fi
        fi
    fi
    if [ "$git_rc" -ne 0 ] && [ -z "$vcs_note" ]; then
        # A .git entry git cannot read (damaged, a pruned worktree record,
        # "dubious ownership"), or git itself failing. That is a repository,
        # so say so and fail the run; its file is neither checked nor changed.
        found=1
        problems=1
        printf '%s\t%s\tunreadable: git exit %s: %s\n' \
            "$repo_name" "$filename" "$git_rc" "${git_err%%$'\n'*}"
        continue
    fi
    found=1
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
            printf '%s\t%s\t%s -> updated%s\n' "$repo_name" "$filename" "$state" "$vcs_note"
        else
            printf '%s\t%s\terror: %s%s\n' "$repo_name" "$filename" "$apply_output" "$vcs_note"
            problems=1
        fi
    else
        printf '%s\t%s\t%s%s\n' "$repo_name" "$filename" "$state" "$vcs_note"
        [ "$state" = tampered ] && problems=1
    fi
done

if [ "$found" = 0 ]; then
    # An empty inventory is a failure, not a clean fleet: a wrong ROOT must not pass.
    echo "sync-shared-fleet: no git or Fossil checkouts found under $ROOT" >&2
    problems=1
fi
exit "$problems"
