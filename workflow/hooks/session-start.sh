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

# Machine label, derived from hostname. Update the case below if you rename a host.
HOSTNAME_SHORT="$(hostname -s)"
case "$HOSTNAME_SHORT" in
  *[Mm]ini*) MACHINE="mini" ;;
  *[Mm][Bb][Pp]*|*[Mm]ac[Bb]ook*) MACHINE="laptop" ;;
  *) MACHINE="$HOSTNAME_SHORT" ;;
esac

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
Machine: $MACHINE
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

# Turso staleness check: warn if last sync >24h ago (or missing despite this
# being a project session — meaning we've never synced from this machine).
# Sync cadence is 8h, so 24h = 3 missed cycles.
TURSO_STAMP="$HOME/.claude/.turso-last-sync"
if [ -f "$TURSO_STAMP" ] && [ -z "$(find "$TURSO_STAMP" -mmin -1440 2>/dev/null)" ]; then
  LAST_SYNC="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$TURSO_STAMP" 2>/dev/null || stat -c '%y' "$TURSO_STAMP" 2>/dev/null | cut -d. -f1)"
  CTX+="
⚠️ Turso sync last succeeded $LAST_SYNC on this machine. If you've been using this machine recently, something's broken — check ~/.claude/.turso-last-sync.log for the failure reason. The async sync hook will retry on every session, but it keeps failing.
"
fi

# Neglected custom commands nudge — at most once per 7 days, only if any
# user-installed slash command has gone unused for 30+ days.
NUDGE_STAMP="$HOME/.claude/state/commands-nudge.touch"
NUDGE_FRESH="$(find "$NUDGE_STAMP" -mmin -10080 2>/dev/null)"
if [ -z "$NUDGE_FRESH" ] && [ -d "$HOME/.claude/commands" ]; then
  CUTOFF="$(date -v-30d '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '30 days ago' '+%Y-%m-%d %H:%M:%S')"
  NEGLECTED=""
  for cmd_file in "$HOME/.claude/commands/"*.md; do
    [ -f "$cmd_file" ] || continue
    cmd="$(basename "$cmd_file" .md)"
    case "$cmd" in *.bak.*) continue ;; esac
    last="$(sqlite3 "$HOME/.claude/prompt-history.db" \
      "SELECT MAX(timestamp) FROM prompts WHERE prompt = '/$cmd' OR prompt LIKE '/$cmd %' OR prompt LIKE '/$cmd' || x'0a' || '%';" 2>/dev/null)"
    if [ -z "$last" ] || [ "$last" \< "$CUTOFF" ]; then
      desc="$(awk -F': *' '/^description:/{sub(/^[ \t]+/, "", $2); print $2; exit}' "$cmd_file")"
      [ -z "$desc" ] && desc="(no description)"
      if [ -z "$last" ]; then
        NEGLECTED+="   /$cmd — $desc (never used)
"
      else
        NEGLECTED+="   /$cmd — $desc (last used $last)
"
      fi
    fi
  done
  if [ -n "$NEGLECTED" ]; then
    CTX+="
Custom commands you haven't used in 30+ days (weekly reminder):
$NEGLECTED"
    mkdir -p "$(dirname "$NUDGE_STAMP")"
    touch "$NUDGE_STAMP"
  fi
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
