#!/bin/bash
# Fires on Claude Code Stop event — writes final token count to sessions table

CONTEXT_WINDOW=200000

INPUT=$(cat)

# Get transcript path and project
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
PROJECT=$(echo "$INPUT" | jq -r '.cwd // empty' | xargs basename)

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

# Update sessions table with final token count
if [[ -n "$PROJECT" && -n "$TOKENS" ]]; then
    SESSION_ID=$(sqlite3 ~/.claude/prompt-history.db "SELECT id FROM sessions WHERE project='$PROJECT' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)
    if [[ -n "$SESSION_ID" ]]; then
        sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET token_count=$TOKENS WHERE id=$SESSION_ID;" 2>/dev/null
    fi
fi

printf '\nSession ended — final context: %d%% (%d tokens)\n' "$PCT" "$TOKENS" >&2

exit 0
