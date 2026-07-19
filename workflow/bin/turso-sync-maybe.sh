#!/bin/bash
# turso-sync-maybe.sh — conditional Turso sync, designed to be invoked from
# an async SessionStart hook. Per-machine: timestamp lives in ~/.claude/ which
# is not synced.
#
# Behavior:
#   <8h since last successful sync : silent skip
#   ≥8h                            : run sync, update timestamp on success
#
# The synchronous SessionStart hook (session-start.sh) reads the same
# timestamp file and warns only when it's ≥48h stale AND this log's newest
# line shows a failed attempt (a stale stamp alone just means the machine
# was idle — this script runs after that hook and catches up immediately).

set -u

STAMP="$HOME/.claude/.turso-last-sync"
LOG="$HOME/.claude/.turso-last-sync.log"
PYTHON="$HOME/src/prompt-lab/.venv/bin/python"
SYNC="$HOME/src/prompt-lab/sync_to_turso.py"

ts() { date "+%Y-%m-%d %H:%M:%S"; }

# Skip if stamp exists and was touched within the last 8h.
# `find -mmin -480` matches files modified within last 480 minutes (8h).
if [ -f "$STAMP" ] && [ -n "$(find "$STAMP" -mmin -480 2>/dev/null)" ]; then
  exit 0
fi

# Guard: required files exist?
if [ ! -x "$PYTHON" ] || [ ! -f "$SYNC" ]; then
  echo "$(ts) skip: missing $PYTHON or $SYNC" >> "$LOG"
  exit 0
fi

# Run the sync, capturing exit code and last line of output for the log
OUT="$("$PYTHON" "$SYNC" --days 1 2>&1)"
RC=$?

if [ "$RC" -eq 0 ]; then
  touch "$STAMP"
  echo "$(ts) ok: $(echo "$OUT" | tail -1)" >> "$LOG"
else
  echo "$(ts) FAIL rc=$RC: $(echo "$OUT" | tail -3 | tr '\n' '|')" >> "$LOG"
fi

exit 0
