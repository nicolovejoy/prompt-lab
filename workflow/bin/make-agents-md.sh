#!/bin/bash
# make-agents-md.sh — write a repo's AGENTS.md in the one supported form: a dated
# provenance comment, a pointer to CLAUDE.md, and the shared-conventions block.
#
# prompt-lab owns this format. The alternative that kept appearing was Codex Desktop's
# "import from Claude Code", which writes a whole-file copy of CLAUDE.md with a blind
# Claude→Codex find-replace (Sep 2026: ~/.claude became ~/.Codex, "Claude API" became
# "Codex API") that then drifts. The importer only writes where AGENTS.md is absent, so
# creating this file everywhere is also what keeps those copies from coming back.
#
# Usage:
#   make-agents-md.sh [DIR]                          # create if absent
#   make-agents-md.sh --replace-importer-copy [DIR]  # also replace an untracked importer copy
#
# Exit: 0 created · 2 no CLAUDE.md in DIR · 3 AGENTS.md exists (left alone)
#       4 importer copy is tracked by git (refused; fix it with a reviewed commit)
#       5 shared-block sync failed (partial file removed)
# Backups of replaced importer copies go to ~/.claude/agents-md-backups/.

set -euo pipefail

REPLACE=no
if [ "${1:-}" = "--replace-importer-copy" ]; then
    REPLACE=yes
    shift
fi
DIR="${1:-.}"
DIR="$(cd "$DIR" && pwd)"
TARGET="$DIR/AGENTS.md"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNC="${SYNC_SHARED_MD:-$SCRIPT_DIR/sync-shared-md.sh}"
BACKUP_DIR="${AGENTS_MD_BACKUP_DIR:-$HOME/.claude/agents-md-backups}"

# The importer's fingerprints: its header line, and the paths its replace corrupts.
is_importer_copy() {
    grep -qE 'guidance to Codex \(Codex\.ai/code\)|Codex-md-shared\.md|~/\.Codex/|Codex API' "$1"
}

if [ ! -f "$DIR/CLAUDE.md" ]; then
    echo "no-claude-md: $DIR has no CLAUDE.md to point at; nothing written" >&2
    exit 2
fi

if [ -e "$TARGET" ]; then
    if [ "$REPLACE" = yes ] && is_importer_copy "$TARGET"; then
        if git -C "$DIR" ls-files --error-unmatch AGENTS.md >/dev/null 2>&1; then
            echo "REFUSED: $TARGET is an importer copy but tracked by git; replace it in a reviewed commit" >&2
            exit 4
        fi
        mkdir -p "$BACKUP_DIR"
        backup="$BACKUP_DIR/$(basename "$DIR")-$(date -u +%Y%m%dT%H%M%SZ).md"
        mv "$TARGET" "$backup"
        echo "backed-up: importer copy moved to $backup"
    else
        echo "exists: $TARGET left alone" >&2
        exit 3
    fi
fi

today="$(TZ=America/Los_Angeles date +%F)"
cat > "$TARGET" <<EOF
<!--
  Written $today by prompt-lab's make-agents-md.sh, for Nico. The prompt-lab agent
  owns this format; raise questions in that repo's handoff channel.

  Why this is a pointer and not a copy: CLAUDE.md is this repo's single source of
  project instructions. Codex reads AGENTS.md automatically, so this file sends it
  to CLAUDE.md and carries the shared-conventions block below.

  Do not replace it with a copy of CLAUDE.md. In September 2026, Codex Desktop's
  "import from Claude Code" wrote whole-file copies using a blind Claude-to-Codex
  find-replace that broke real paths (~/.claude became ~/.Codex), and the copies
  drifted. The importer only writes AGENTS.md where none exists, so keeping this
  file in place also stops those copies from coming back.

  Codex-only notes can go above the markers. Refresh the block with:
  ~/.claude/bin/sync-shared-md.sh --apply ./AGENTS.md
-->

Read CLAUDE.md in this repo first for project-specific conventions.
EOF

if ! "$SYNC" --apply "$TARGET" >/dev/null; then
    rm -f "$TARGET"
    echo "sync-failed: shared block could not be applied; $TARGET removed" >&2
    exit 5
fi
echo "created: $TARGET"
