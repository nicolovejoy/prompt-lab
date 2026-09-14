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
    python3 "$GC_BIN_DIR/_gc_session_identity.py" register "$PROJECT" "$@"
    ;;
  update-session-summary)
    python3 "$GC_BIN_DIR/_gc_session_identity.py" summary "$PROJECT" "$@"
    ;;
  end-session)
    python3 "$GC_BIN_DIR/_gc_session_identity.py" end "$PROJECT" "$@"
    ;;
  save-daily-summary)
    if [ "$#" -ne 1 ]; then
      echo "usage: gc-write.sh save-daily-summary <json-path>" >&2
      exit 2
    fi
    PROMPT_LAB_DIR="${PROMPT_LAB_DIR:-$HOME/src/prompt-lab}"
    export PROMPT_LAB_DIR
    "$PROMPT_LAB_DIR/.venv/bin/python" "$GC_BIN_DIR/_gc_day_context.py" "$PROJECT" --save "$1"
    ;;
  *)
    echo "usage: gc-write.sh {register-session|update-session-summary <id>|end-session <id>|save-daily-summary <json-path>}" >&2
    exit 2
    ;;
esac
