#!/bin/bash
# Fires on Claude Code Stop event — writes final token count to sessions table

CONTEXT_WINDOW=200000

INPUT=$(cat)

# Get transcript path and project
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
HOOK_REAL=$(readlink -f "$0" 2>/dev/null || echo "$0")
HOOK_BIN="$(dirname "$HOOK_REAL")/../bin"
. "$HOOK_BIN/_gc_project.sh"
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
PROJECT=$(gc_resolve_project "$CWD")

if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
    exit 0
fi

# Read final token count from transcript
USAGE=$(python3 -c "
import json, sys
with open('$TRANSCRIPT_PATH') as f:
    lines = f.readlines()
for line in reversed(lines):
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        u = d.get('message', {}).get('usage', {})
        if u:
            total = u.get('input_tokens',0) + u.get('cache_creation_input_tokens',0) + u.get('cache_read_input_tokens',0)
            sid = d.get('sessionId','')
            print(f'{total},{sid}')
            break
    except: pass
" 2>/dev/null)

if [[ -z "$USAGE" ]]; then
    exit 0
fi

TOKENS=$(echo "$USAGE" | cut -d, -f1)
PCT=$(( TOKENS * 100 / CONTEXT_WINDOW ))

# Update sessions table with final token count.
# Resolve the row by the real conversation id (same fix as log-prompt.sh) so a
# stale open row can't absorb this session's token count.
if [[ -n "$PROJECT" && -n "$TOKENS" ]]; then
    CLAUDE_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
    if [[ -z "$CLAUDE_SESSION_ID" ]]; then
        CLAUDE_SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
    fi
    python3 "$HOOK_BIN/_gc_session_identity.py" tokens "$PROJECT" "$CLAUDE_SESSION_ID" "$TOKENS" || exit $?

fi

printf '\nSession ended — final context: %d%% (%d tokens)\n' "$PCT" "$TOKENS" >&2

exit 0
