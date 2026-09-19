#!/bin/bash
# sync-shared-md.sh — materialize the shared-conventions block into a repo's CLAUDE.md or AGENTS.md.
#
# The shared block (prompt-lab/workflow/claude-md-shared.md) is the single source of
# truth for Nico's cross-repo output rules. This script writes it verbatim between
# sentinel markers in a target Markdown file, touching NOTHING outside the markers — each
# repo's bespoke content is preserved. We compile-to-committed-text rather than rely on
# CLAUDE.md @import because @import is a Claude Code harness feature only (cloud/headless/
# third-party consumers see the literal @path), so it would not reach every environment.
#
# Usage:
#   sync-shared-md.sh --check  [TARGET]   # exit 0 in sync, 1 behind/tampered/missing, 2 absent
#   sync-shared-md.sh --apply  [TARGET]   # create/refresh clean blocks; refuses tampered blocks
#
# TARGET defaults to ./CLAUDE.md. Canonical source defaults to ~/.claude/claude-md-shared.md
# (installed copy); falls back to the in-repo copy next to this script. Override with
# CLAUDE_MD_SHARED=/path/to/source.

set -euo pipefail

BEGIN_TOKEN='SHARED-CONVENTIONS:BEGIN'
END_TOKEN='SHARED-CONVENTIONS:END'

MODE="${1:---check}"
TARGET="${2:-./CLAUDE.md}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CANONICAL="${CLAUDE_MD_SHARED:-}"
if [ -z "$CANONICAL" ]; then
    if [ -f "$HOME/.claude/claude-md-shared.md" ]; then
        CANONICAL="$HOME/.claude/claude-md-shared.md"
    else
        CANONICAL="$SCRIPT_DIR/../claude-md-shared.md"
    fi
fi

if [ ! -f "$CANONICAL" ]; then
    echo "sync-shared-md: canonical source not found: $CANONICAL" >&2
    exit 3
fi

HASH="$(shasum -a 256 "$CANONICAL" | awk '{print $1}' | cut -c1-12)"

recorded_hash() {
    [ -f "$TARGET" ] || return 0
    # Anchor to a real marker: a line that STARTS with the comment opener. Prose
    # that merely mentions the token mid-line (e.g. this repo's CLAUDE.md, which
    # documents the marker syntax) must not be mistaken for the marker itself.
    # `|| true`: grep returning non-zero on no-match must not trip set -e/pipefail.
    { grep -m1 "^<!-- $BEGIN_TOKEN" "$TARGET" 2>/dev/null || true; } | sed -n 's/.*v=\([a-f0-9]*\).*/\1/p'
}

target_state() {
    # Print exactly one machine-readable state. A clean old block is "behind";
    # a body that no longer matches its own recorded hash is "tampered". This
    # distinction prevents a canonical reword from looking like local damage.
    begin_count="$({ grep -c "^<!-- $BEGIN_TOKEN" "$TARGET" 2>/dev/null || true; } | tr -d ' ')"
    end_count="$({ grep -c "^<!-- $END_TOKEN" "$TARGET" 2>/dev/null || true; } | tr -d ' ')"
    if [ "$begin_count" = 0 ] && [ "$end_count" = 0 ]; then
        printf 'missing'
        return
    fi
    if [ "$begin_count" != 1 ] || [ "$end_count" != 1 ] || ! awk \
        -v b="<!-- $BEGIN_TOKEN" -v e="<!-- $END_TOKEN" '
            index($0, b) == 1 { begin_line=NR }
            index($0, e) == 1 { end_line=NR }
            END { exit !(begin_line > 0 && end_line > begin_line) }
        ' "$TARGET"
    then
        printf 'tampered'
        return
    fi

    rec="$(recorded_hash)"
    if [ "${#rec}" -ne 12 ] || printf '%s' "$rec" | grep -q '[^a-f0-9]'; then
        printf 'tampered'
        return
    fi

    body="$(mktemp -t sync-shared-body.XXXXXX)"
    awk -v b="<!-- $BEGIN_TOKEN" -v e="<!-- $END_TOKEN" '
        index($0, b) == 1 { inside=1; next }
        index($0, e) == 1 { inside=0; next }
        inside { print }
    ' "$TARGET" > "$body"
    actual="$(shasum -a 256 "$body" | awk '{print $1}' | cut -c1-12)"
    rm -f "$body"
    if [ "$actual" != "$rec" ]; then
        printf 'tampered'
    elif [ "$rec" != "$HASH" ]; then
        printf 'behind'
    else
        printf 'in sync'
    fi
}

case "$MODE" in
    --check)
        if [ ! -f "$TARGET" ]; then
            echo "absent: $TARGET does not exist"
            exit 2
        fi
        state="$(target_state)"
        rec="$(recorded_hash)"
        if [ "$state" = "missing" ]; then
            echo "missing: shared-conventions block not present in $TARGET (run --apply)"
            exit 1
        fi
        if [ "$state" = "tampered" ]; then
            echo "tampered: shared-conventions block or marker does not match its recorded hash in $TARGET (review manually; --apply will not overwrite it)"
            exit 1
        fi
        if [ "$state" = "in sync" ]; then
            echo "in sync: $TARGET (v=$HASH)"
            exit 0
        fi
        echo "behind: $TARGET has clean v=$rec, source is v=$HASH (run --apply)"
        exit 1
        ;;
    --apply)
        # Build the replacement block: BEGIN marker (with hash) + canonical body + END marker.
        block="$(mktemp -t sync-shared-md.XXXXXX)"
        trap 'rm -f "$block"' EXIT
        {
            printf '<!-- %s v=%s — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->\n' "$BEGIN_TOKEN" "$HASH"
            cat "$CANONICAL"
            printf '<!-- %s -->\n' "$END_TOKEN"
        } > "$block"

        if [ ! -f "$TARGET" ]; then
            mkdir -p "$(dirname "$TARGET")"
            cat "$block" > "$TARGET"
            echo "created: $TARGET with shared-conventions block (v=$HASH)"
            exit 0
        fi

        state="$(target_state)"
        if [ "$state" = "tampered" ]; then
            echo "REFUSED: shared-conventions block or marker is tampered in $TARGET." >&2
            echo "         Review the local edits manually; --apply never overwrites an unverified block." >&2
            exit 6
        fi

        if [ "$state" != "missing" ]; then
            # Replace existing region in place. On BEGIN, emit the new block then skip
            # old lines through END; everything else passes through untouched.
            # `index(...)==1` anchors to real markers (line starts with the comment
            # opener), so prose that mentions the token mid-line is left untouched.
            awk -v blockfile="$block" -v b="<!-- $BEGIN_TOKEN" -v e="<!-- $END_TOKEN" '
                index($0, b) == 1 { while ((getline l < blockfile) > 0) print l; skip=1; next }
                index($0, e) == 1 { skip=0; next }
                skip { next }
                { print }
            ' "$TARGET" > "$TARGET.tmp"

            # Safety rail: --apply may ONLY change the marker region. Everything
            # OUTSIDE the block must be byte-identical before and after; if not,
            # the splice has eaten bespoke content (the 2026-06-29 clobber) —
            # abort and write nothing. Strip the block from both and compare.
            strip_block() {
                awk -v b="<!-- $BEGIN_TOKEN" -v e="<!-- $END_TOKEN" '
                    index($0, b) == 1 { skip=1; next }
                    index($0, e) == 1 { skip=0; next }
                    skip { next }
                    { print }
                ' "$1"
            }
            if ! diff <(strip_block "$TARGET") <(strip_block "$TARGET.tmp") >/dev/null 2>&1; then
                echo "ABORT: --apply would alter content OUTSIDE the shared-conventions markers in $TARGET." >&2
                echo "       Nothing written. Out-of-band changes (- existing / + would-be):" >&2
                diff <(strip_block "$TARGET") <(strip_block "$TARGET.tmp") >&2 || true
                rm -f "$TARGET.tmp"
                exit 5
            fi

            mv "$TARGET.tmp" "$TARGET"
            echo "updated: shared-conventions block in $TARGET (v=$HASH)"
        else
            # No markers yet — append after a blank line.
            printf '\n' >> "$TARGET"
            cat "$block" >> "$TARGET"
            echo "appended: shared-conventions block to $TARGET (v=$HASH)"
        fi
        exit 0
        ;;
    *)
        echo "usage: sync-shared-md.sh [--check|--apply] [TARGET]" >&2
        exit 64
        ;;
esac
