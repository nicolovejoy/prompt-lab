#!/bin/bash
# gc-write.sh — write operations against ~/.claude/prompt-history.db for slash commands.
# Not auto-allowed in settings.json — invocations still prompt for permission.
# Centralizing here so the prompt-shown command line is stable (no $() expansion).

set -euo pipefail

DB="$HOME/.claude/prompt-history.db"
PROJECT="$(basename "$PWD")"
CMD="${1:-}"
shift || true

case "$CMD" in
  register-session)
    sqlite3 "$DB" "INSERT INTO sessions (project) VALUES ('$PROJECT');"
    ;;
  update-session-summary)
    # args: <session_id>; summary read from stdin. Uses python sqlite param
    # binding to dodge bash quote-escaping bugs entirely.
    SID="$1"
    if [ -z "${SID:-}" ]; then
      echo "usage: gc-write.sh update-session-summary <session_id>   # summary from stdin" >&2
      exit 2
    fi
    python3 "$HOME/.claude/bin/_update_session_summary.py" "$DB" "$SID"
    ;;
  end-session)
    # args: <session_id>. Explicit close, split out of update-session-summary so
    # a mid-session /handoff can summarize without orphaning later prompts.
    SID="$1"
    case "${SID:-}" in
      ''|*[!0-9]*)
        echo "usage: gc-write.sh end-session <session_id>" >&2
        exit 2
        ;;
    esac
    sqlite3 "$DB" "UPDATE sessions SET ended_at=datetime('now') WHERE id=$SID;"
    ;;
  *)
    echo "usage: gc-write.sh {register-session|update-session-summary <id>|end-session <id>}" >&2
    exit 2
    ;;
esac
