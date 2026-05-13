#!/bin/bash
# SessionStart hook — inject lightweight readup-style context at session start.
#
# Output: a single JSON object with hookSpecificOutput.additionalContext.
# Silent (no JSON) if cwd doesn't look like a real project — avoids noise on
# quick `claude` launches in ~ or /tmp.
#
# Does NOT register a session row or run `git pull` — those stay behind the
# explicit /readup command. To upgrade to a full readup hook, add a call to
# `~/.claude/bin/gc-write.sh register-session` before the JSON emit (and accept
# that every Claude launch will create a session row).

set -u

# Read stdin (hook gets a JSON payload, but we don't need any of its fields)
cat >/dev/null 2>&1 || true

CWD="$(pwd)"
HOME_SRC="$HOME/src"

# Guard: only run in real project dirs under ~/src/ that are git repos
case "$CWD" in
  "$HOME_SRC"/*) ;;
  *) exit 0 ;;
esac
git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

PROJECT="$(basename "$CWD")"
TODAY="$(date "+%A, %B %-d, %Y")"

# Last ended session for this project
LAST_SUMMARY="$(sqlite3 "$HOME/.claude/prompt-history.db" \
  "SELECT substr(summary, 1, 400) || '|' || ended_at FROM sessions WHERE project='$PROJECT' AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)"

# Recent commits + working tree
RECENT_COMMITS="$(git -C "$CWD" log --oneline -5 2>/dev/null)"
DIRTY="$(git -C "$CWD" status --short 2>/dev/null)"

# Bulletin headlines (skip silently if file missing)
BULLETIN="$(grep -E '^## ' "$HOME/src/prompt-lab/BULLETIN.md" 2>/dev/null | head -5)"

# Assemble context
CTX="Session-start context (auto-injected, not a /readup invocation):

Today: $TODAY
Project: $PROJECT
Working dir: $CWD
"

if [ -n "$LAST_SUMMARY" ]; then
  CTX+="
Last session: $LAST_SUMMARY
"
fi

if [ -n "$RECENT_COMMITS" ]; then
  CTX+="
Recent commits:
$RECENT_COMMITS
"
fi

if [ -n "$DIRTY" ]; then
  CTX+="
Uncommitted:
$DIRTY
"
fi

if [ -n "$BULLETIN" ]; then
  CTX+="
Cross-project bulletin (/bulletin for details):
$BULLETIN
"
fi

CTX+="
The user has NOT run /readup yet — they may or may not. Do not preemptively summarize. Use this context to answer their first message in an informed way."

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
