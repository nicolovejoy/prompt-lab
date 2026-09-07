#!/bin/bash
# gc-write.sh — write operations against ~/.claude/prompt-history.db for slash commands.
# Not auto-allowed in settings.json — invocations still prompt for permission.
# Centralizing here so the prompt-shown command line is stable (no $() expansion).

set -euo pipefail

DB="$HOME/.claude/prompt-history.db"

# The project is the REPO, not the cwd basename — see _gc_project.sh for why.
# register-session is the one that mattered most: from a worktree it minted a
# session row under `agent-<hash>`, which the hook then never adopted, so the
# conversation ended up with two rows in two projects.
GC_BIN_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
# shellcheck source=./_gc_project.sh
. "$GC_BIN_DIR/_gc_project.sh"
PROJECT="$(gc_resolve_project "$PWD")"

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
