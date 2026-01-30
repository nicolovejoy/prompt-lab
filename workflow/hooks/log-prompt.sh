#!/bin/bash
# Auto-log prompts to SQLite on submission

DEBUG_LOG=~/.claude/hooks/debug.log
echo "$(date): Hook called" >> "$DEBUG_LOG"

# Read JSON from stdin
INPUT=$(cat)
echo "$(date): Input length: ${#INPUT}" >> "$DEBUG_LOG"
echo "$(date): Raw input: $INPUT" >> "$DEBUG_LOG"

# Extract prompt text (jq required)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')
echo "$(date): Prompt length: ${#PROMPT}, first 50: ${PROMPT:0:50}" >> "$DEBUG_LOG"

# Skip if empty or too short
if [ -z "$PROMPT" ] || [ ${#PROMPT} -lt 20 ]; then
    exit 0
fi

# Skip command invocations
if [[ "$PROMPT" == "<command-"* ]]; then
    exit 0
fi

# Get project name from cwd in the input
PROJECT=$(echo "$INPUT" | jq -r '.cwd // empty' | xargs basename)
if [ -z "$PROJECT" ]; then
    PROJECT="unknown"
fi

# Get session_id if available
SESSION_ID=$(sqlite3 ~/.claude/prompt-history.db "SELECT id FROM sessions WHERE project='$PROJECT' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)

# Extract last assistant response from transcript as context
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
CONTEXT=""
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    # Get last assistant text, excluding system reminders (use tail -r for macOS)
    CONTEXT=$(tail -r "$TRANSCRIPT_PATH" 2>/dev/null | \
        jq -r 'select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text' 2>/dev/null | \
        grep -v '^<system-reminder>' | \
        grep -v '^<thinking>' | \
        head -1 | \
        head -c 500)
fi
echo "$(date): Context length: ${#CONTEXT}" >> "$DEBUG_LOG"

# Escape single quotes for SQL
PROMPT_ESCAPED=$(echo "$PROMPT" | sed "s/'/''/g")
CONTEXT_ESCAPED=$(echo "$CONTEXT" | sed "s/'/''/g")

# Insert into database (utility=NULL means unrated)
if [ -n "$SESSION_ID" ]; then
    sqlite3 ~/.claude/prompt-history.db "INSERT INTO prompts (project, prompt, session_id, context) VALUES ('$PROJECT', '$PROMPT_ESCAPED', $SESSION_ID, '$CONTEXT_ESCAPED');" 2>/dev/null
else
    sqlite3 ~/.claude/prompt-history.db "INSERT INTO prompts (project, prompt, context) VALUES ('$PROJECT', '$PROMPT_ESCAPED', '$CONTEXT_ESCAPED');" 2>/dev/null
fi

exit 0
