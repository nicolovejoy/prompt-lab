#!/bin/bash
# claude-md-size.sh — is this repo's CLAUDE.md due for a trim? Read-only.
#
#   claude-md-size.sh [FILE]     FILE defaults to ./CLAUDE.md, or .claude/CLAUDE.md
#                                when the root has none (the order readup uses)
#
# Prints one line and always exits 0:
#   own_bytes=N shared_bytes=N lines=N limit=N trim_age_d=N due=yes|no
#   absent                       (no such file)
#
# own_bytes leaves out the synced Shared conventions block (the lines from
# SHARED-CONVENTIONS:BEGIN to SHARED-CONVENTIONS:END). A repo cannot cut that
# block, and it is about 6 KB of every CLAUDE.md, so counting it would hold each
# repo responsible for text it does not own (l6-music, 2026-11-18).
#
# due=yes when own_bytes is over the limit AND the repo's trim marker
# (~/.claude/state/claude-trim-<dir>.touch, written by /workflow-maintenance) is
# at least 7 days old or missing. The marker keeps a file that was just trimmed,
# or that has nothing left to cut, from being flagged at every session start.
#
# The limit is 30000 bytes of own text. On 2026-11-20 that flagged 9 of 42
# CLAUDE.md files under ~/src (32 KB to 137 KB) and left alone l6-music's, which
# had just been cut by hand to 17 KB. Override with CLAUDE_SIZE_LIMIT.
#
# /readup (through readup-checks.sh) and /workflow-maintenance both read this
# line, so the two cannot disagree about what "too big" means.

f="${1:-}"
if [ -z "$f" ]; then
  f=CLAUDE.md
  [ ! -f CLAUDE.md ] && [ -f .claude/CLAUDE.md ] && f=.claude/CLAUDE.md
fi
limit="${CLAUDE_SIZE_LIMIT:-30000}"
case "$limit" in ''|*[!0-9]*) limit=30000 ;; esac

if [ ! -f "$f" ]; then
  echo "absent"
  exit 0
fi

total="$(wc -c < "$f" | tr -d ' ')"
lines="$(wc -l < "$f" | tr -d ' ')"
# LC_ALL=C so length() counts bytes, matching wc -c.
shared="$(LC_ALL=C awk '/SHARED-CONVENTIONS:BEGIN/{a=1} a{n+=length($0)+1} /SHARED-CONVENTIONS:END/{a=0} END{print n+0}' "$f")"
own=$(( total - shared ))
[ "$own" -lt 0 ] && own=0

marker="$HOME/.claude/state/claude-trim-$(basename "$PWD").touch"
# GNU first. GNU stat reads `-f` as "filesystem status", prints a report for the
# marker and fails, so with BSD first a marker that exists yields two answers.
# BSD stat rejects `-c` and prints nothing.
mt="$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo 0)"
trim_age_d=$(( ($(date +%s) - mt) / 86400 ))

due=no
[ "$own" -gt "$limit" ] && [ "$trim_age_d" -ge 7 ] && due=yes
echo "own_bytes=$own shared_bytes=$shared lines=$lines limit=$limit trim_age_d=$trim_age_d due=$due"
exit 0
