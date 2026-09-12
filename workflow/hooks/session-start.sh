#!/bin/bash
# SessionStart hook — inject lightweight readup-style context at session start.
#
# Output: a single JSON object with hookSpecificOutput.additionalContext.
# Context-gathering logic lives in workflow/bin/session-context.sh (shared
# with agents that have no hook mechanism, e.g. Codex — see /readup step 0).
# This wrapper's only job is invoking that script and JSON-wrapping its
# output for the Claude Code hook protocol.
#
# Does NOT register a session row or run `git pull` — those stay behind the
# explicit /readup command.

set -u

# Read stdin (hook gets a JSON payload, but we don't need any of its fields)
cat >/dev/null 2>&1 || true

# Resolve our own real location so we can find the sibling bin script
# in-repo — this hook runs from $REPO_DIR/workflow/hooks/ (registered by
# absolute repo path in settings.json, never copied to ~/.claude/hooks/),
# same idiom log-prompt.sh uses for its own sibling script (HOOK_REAL).
HOOK_REAL=$(readlink -f "$0" 2>/dev/null || echo "$0")
SESSION_CONTEXT="$(dirname "$HOOK_REAL")/../bin/session-context.sh"

CTX="$("$SESSION_CONTEXT")"

# Guard: if context is empty (cwd guard failed), exit with no output
if [ -z "$CTX" ]; then
  exit 0
fi

if [ -n "$CTX" ]; then
  CTX+="

The user has NOT run /readup yet — they may or may not. Do not preemptively summarize. Use this context to answer their first message in an informed way."
fi

# Emit hook output JSON. Python handles the escaping cleanly.
python3 -c "
import json, sys
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'SessionStart',
    'additionalContext': sys.stdin.read()
  }
}))
" <<< "$CTX"
