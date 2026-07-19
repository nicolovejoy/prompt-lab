#!/bin/bash
# Auto-log prompts to SQLite on submission

DEBUG_LOG=~/.claude/hooks/debug.log

# Read JSON from stdin
INPUT=$(cat)

# Extract prompt text (jq required)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -n "$CLAUDE_HOOK_DEBUG" ]; then
    echo "$(date): Hook called" >> "$DEBUG_LOG"
    echo "$(date): Input length: ${#INPUT}" >> "$DEBUG_LOG"
    echo "$(date): Prompt length: ${#PROMPT}, first 50: ${PROMPT:0:50}" >> "$DEBUG_LOG"
fi

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

DB=~/.claude/prompt-history.db
PROJECT_ESCAPED=$(echo "$PROJECT" | sed "s/'/''/g")

# === Session identity ===
# Bind this prompt to the REAL Claude Code conversation. The old resolver took
# "newest open row for this project", so a mid-session /handoff (which closed
# the row) silently re-filed every later prompt onto an unrelated stale session.
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
CLAUDE_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
if [ -z "$CLAUDE_SESSION_ID" ] && [ -n "$TRANSCRIPT_PATH" ]; then
    # Transcripts live at ~/.claude/projects/<slug>/<session-uuid>.jsonl
    CLAUDE_SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)
fi

SESSION_ID=""
if [ -n "$CLAUDE_SESSION_ID" ]; then
    CSID=$(echo "$CLAUDE_SESSION_ID" | sed "s/'/''/g")

    # Self-heal the schema so a machine that hasn't run store.migrate() yet
    # still binds correctly instead of silently falling back.
    if ! sqlite3 "$DB" "SELECT claude_session_id FROM sessions LIMIT 1;" >/dev/null 2>&1; then
        sqlite3 "$DB" "ALTER TABLE sessions ADD COLUMN claude_session_id TEXT;" 2>/dev/null
    fi

    # Upsert by claude_session_id. The UPDATE adopts the unbound row /readup's
    # register-session just created (recent, still open, no prompts yet) so the
    # hook and /readup don't each create a row for one conversation.
    SESSION_ID=$(sqlite3 "$DB" "
        UPDATE sessions SET claude_session_id='$CSID'
         WHERE id = (SELECT id FROM sessions
                      WHERE project='$PROJECT_ESCAPED'
                        AND claude_session_id IS NULL
                        AND ended_at IS NULL
                        AND started_at >= datetime('now','-12 hours')
                        AND NOT EXISTS (SELECT 1 FROM prompts
                                         WHERE prompts.session_id = sessions.id)
                      ORDER BY started_at DESC LIMIT 1)
           AND NOT EXISTS (SELECT 1 FROM sessions
                            WHERE project='$PROJECT_ESCAPED'
                              AND claude_session_id='$CSID');
        INSERT INTO sessions (project, claude_session_id, hostname)
             SELECT '$PROJECT_ESCAPED', '$CSID', '$(hostname -s)'
              WHERE NOT EXISTS (SELECT 1 FROM sessions
                                 WHERE project='$PROJECT_ESCAPED'
                                   AND claude_session_id='$CSID');
        SELECT id FROM sessions
         WHERE project='$PROJECT_ESCAPED' AND claude_session_id='$CSID'
         ORDER BY id DESC LIMIT 1;" 2>/dev/null)
fi

# Fallback: no derivable session id — keep the old behavior rather than
# dropping the prompt on the floor.
if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(sqlite3 "$DB" "SELECT id FROM sessions WHERE project='$PROJECT_ESCAPED' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)
fi

# Pointer file so slash commands resolve the same row without threading an id
# through the model. gc-read.sh / gc-write.sh read it, falling back to the old
# query when it's absent.
if [ -n "$SESSION_ID" ]; then
    mkdir -p ~/.claude/state 2>/dev/null
    echo "$SESSION_ID" > ~/.claude/state/current-session-"$PROJECT" 2>/dev/null
fi

# Extract last assistant response from transcript as context
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
if [ -n "$CLAUDE_HOOK_DEBUG" ]; then
    echo "$(date): Context length: ${#CONTEXT}" >> "$DEBUG_LOG"
fi

# Capture hostname for multi-machine tracking
MACHINE=$(hostname -s)

# Escape single quotes for SQL
PROMPT_ESCAPED=$(echo "$PROMPT" | sed "s/'/''/g")
CONTEXT_ESCAPED=$(echo "$CONTEXT" | sed "s/'/''/g")

# Auto-register project if not already known
sqlite3 ~/.claude/prompt-history.db "INSERT OR IGNORE INTO projects (name) VALUES ('$PROJECT');" 2>/dev/null

# Insert into database (utility=NULL means unrated)
if [ -n "$SESSION_ID" ]; then
    sqlite3 ~/.claude/prompt-history.db "INSERT INTO prompts (project, prompt, session_id, context, hostname) VALUES ('$PROJECT', '$PROMPT_ESCAPED', $SESSION_ID, '$CONTEXT_ESCAPED', '$MACHINE');" 2>/dev/null
else
    sqlite3 ~/.claude/prompt-history.db "INSERT INTO prompts (project, prompt, context, hostname) VALUES ('$PROJECT', '$PROMPT_ESCAPED', '$CONTEXT_ESCAPED', '$MACHINE');" 2>/dev/null
fi

# === Context Usage Alert ===
CONTEXT_WINDOW=200000
STATE_FILE="/tmp/claude-context-thresholds"

if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
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

    if [[ -n "$USAGE" ]]; then
        TOKENS=$(echo "$USAGE" | cut -d, -f1)
        SID=$(echo "$USAGE" | cut -d, -f2)
        PCT=$(( TOKENS * 100 / CONTEXT_WINDOW ))
        DECILE=$(( PCT / 10 ))

        # Load last alerted decile for this session (0 = none)
        LAST_DECILE=$(grep "^$SID:" "$STATE_FILE" 2>/dev/null | tail -1 | cut -d: -f2)
        LAST_DECILE=${LAST_DECILE:-0}

        if (( DECILE > LAST_DECILE && DECILE > 0 )); then
            NOTIFY="Context at ${PCT}% (${TOKENS} tokens)"
            printf '\n⚠️  %s\n' "$NOTIFY" >&2
            grep -v "^$SID:" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null
            echo "$SID:$DECILE" >> "${STATE_FILE}.tmp"
            mv "${STATE_FILE}.tmp" "$STATE_FILE"
        fi

        # Write latest token count to sessions table
        if [[ -n "$SESSION_ID" && -n "$TOKENS" ]]; then
            sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET token_count=$TOKENS WHERE id=$SESSION_ID;" 2>/dev/null
        fi
    fi
fi

exit 0
