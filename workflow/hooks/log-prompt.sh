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

# Skip only genuinely empty input.
#
# There used to be a `${#PROMPT} -lt 20` filter here. It threw away every short
# prompt — "yes", "go ahead", "ship it", "no, the other one" — which is most of
# what steering a session looks like. The damage wasn't the missing rows, it
# was the SHAPE of the loss: days spent supervising read as quiet, days spent
# writing specs read as busy, and prompt_count feeds the trajectory heatmap and
# the KPI tiles. The charts presented a filtered signal as an activity record.
# Its fingerprint was still in the data on 2026-08-14: min(length(prompt)) over
# the whole table was exactly 20, with zero rows below.
#
# Everything is stored now and labelled instead (see `kind` below), because a
# label can be recomputed and a discarded row cannot.
if [ -z "$PROMPT" ]; then
    exit 0
fi

# Skip command invocations and harness-generated task notifications
if [[ "$PROMPT" == "<command-"* || "$PROMPT" == "<task-notification>"* ]]; then
    exit 0
fi

# Get project name from cwd in the input. Agent worktrees live at
# <repo>/.claude/worktrees/agent-<hash> — attribute those to the repo,
# not the throwaway worktree dir.
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
case "$CWD" in
    */.claude/worktrees/*) CWD="${CWD%%/.claude/worktrees/*}" ;;
esac

# The project is the REPO, not the directory. Taking the cwd basename minted a
# project for every directory ever worked in — `src`, `web`, `public`, `utils`,
# `mockups` are all just subdirectories of real repos, and they accounted for
# most of an 80-name project list. --git-common-dir (not --show-toplevel)
# because a linked worktree's toplevel is the worktree; the common dir is
# always the main repo's .git, so worktrees attribute correctly even when they
# don't live under the .claude/ path stripped above.
#
# Exit code 128 specifically means "not a git repository" — those go to one
# `scratch` bucket instead of minting a name per directory. Any OTHER failure
# (git missing, or the Xcode license prompt that broke every git call on this
# laptop on 2026-08-05) MUST fall back to the old basename behavior: a broken
# git must never silently relabel real project work as scratch.
REPO_NAME=""
if command -v git >/dev/null 2>&1 && [ -n "$CWD" ]; then
    GIT_COMMON=$(git -C "$CWD" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
    GIT_RC=$?
    if [ "$GIT_RC" -eq 0 ] && [ -n "$GIT_COMMON" ]; then
        REPO_NAME=$(basename "$(dirname "$GIT_COMMON")")
    elif [ "$GIT_RC" -eq 128 ]; then
        REPO_NAME="scratch"
    fi
fi
PROJECT="${REPO_NAME:-$(basename "$CWD" 2>/dev/null)}"
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

# Extract the last assistant response as context. Paired with kind='approval'
# this is what answers "what did I actually say yes to?" — the prompt alone is
# the word "yes", the answer is in the message above it.
#
# This used to be `head -1 | head -c 500`, which kept the first LINE of the
# last message: an average of 124 characters, usually a lead-in sentence rather
# than the proposal being approved. Now the whole message is taken and the
# TRAILING 2000 chars kept, because a message ends with its ask.
#
# base64 is doing real work here: `tail -r` reverses the transcript so the
# first record out is the most recent, but a message spans many lines, so
# `head -1` on raw text truncates it. Encoding each message to a single line
# makes "first record" and "first line" the same thing again.
CONTEXT=""
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    CONTEXT_B64=$(tail -r "$TRANSCRIPT_PATH" 2>/dev/null | \
        jq -r 'select(.type == "assistant")
               | [.message.content[]? | select(.type == "text") | .text]
               | join("\n")
               | select(length > 0)
               | @base64' 2>/dev/null | \
        head -1)
    if [ -n "$CONTEXT_B64" ]; then
        CONTEXT=$(printf '%s' "$CONTEXT_B64" | base64 --decode 2>/dev/null | \
            grep -v '^<system-reminder>' | \
            grep -v '^<thinking>' | \
            tail -c 2000)
    fi
fi

# Coarse label so selection happens at read time instead of at write time.
# One implementation lives in scripts/prompt_kind.py and is shared with
# scripts/backfill_prompt_kind.py, so the live rules and the backfill rules
# cannot drift apart. This file is normally reached through a symlink in
# ~/.claude/hooks, so resolve to the real repo before looking for it.
HOOK_REAL=$(readlink -f "$0" 2>/dev/null || echo "$0")
KIND_PY="$(dirname "$HOOK_REAL")/../../scripts/prompt_kind.py"
KIND=""
if [ -f "$KIND_PY" ]; then
    KIND=$(printf '%s' "$PROMPT" | python3 "$KIND_PY" 2>/dev/null)
fi
# An unreachable classifier must never cost us the row — log unlabelled.
[ -z "$KIND" ] && KIND="spec"
if [ -n "$CLAUDE_HOOK_DEBUG" ]; then
    echo "$(date): Context length: ${#CONTEXT}" >> "$DEBUG_LOG"
fi

# Capture hostname for multi-machine tracking
MACHINE=$(hostname -s)

# Escape single quotes for SQL. printf rather than echo: with the length filter
# gone, a prompt can now legitimately be exactly "-n" or "-e", which echo would
# swallow as a flag instead of storing.
PROMPT_ESCAPED=$(printf '%s' "$PROMPT" | sed "s/'/''/g")
CONTEXT_ESCAPED=$(printf '%s' "$CONTEXT" | sed "s/'/''/g")

# Auto-register project if not already known
sqlite3 "$DB" "INSERT OR IGNORE INTO projects (name) VALUES ('$PROJECT');" 2>/dev/null

# The `prompts` table predates store/sqlite_store.py's migrate path (it was
# created by the Flask dashboard, retired 2026-05-28), and this hook is bash —
# it never calls migrate(). So add the column defensively. Without this, on any
# DB lacking `kind` EVERY insert below fails and every prompt is lost silently,
# which is precisely the failure shape this repo keeps re-learning.
# Already-exists is an expected error, not a problem.
sqlite3 "$DB" "ALTER TABLE prompts ADD COLUMN kind TEXT;" 2>/dev/null

# Insert into database
if [ -n "$SESSION_ID" ]; then
    INSERT_ERR=$(sqlite3 "$DB" "INSERT INTO prompts (project, prompt, session_id, context, hostname, kind) VALUES ('$PROJECT', '$PROMPT_ESCAPED', $SESSION_ID, '$CONTEXT_ESCAPED', '$MACHINE', '$KIND');" 2>&1 >/dev/null)
else
    INSERT_ERR=$(sqlite3 "$DB" "INSERT INTO prompts (project, prompt, context, hostname, kind) VALUES ('$PROJECT', '$PROMPT_ESCAPED', '$CONTEXT_ESCAPED', '$MACHINE', '$KIND');" 2>&1 >/dev/null)
fi

# A failed insert used to go to /dev/null, so a broken hook and a quiet day
# looked identical from the data. Record it unconditionally — this log existing
# at all is the alarm.
if [ -n "$INSERT_ERR" ]; then
    mkdir -p ~/.claude/hooks 2>/dev/null
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) prompt insert failed [$PROJECT]: $INSERT_ERR" \
        >> ~/.claude/hooks/log-prompt-errors.log
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
