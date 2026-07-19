#!/bin/bash
# gc-read.sh — read-only queries against ~/.claude/prompt-history.db for slash commands.
# Resolves $PWD/basename internally so callers never need shell expansion.
# Allowed in ~/.claude/settings.json via Bash(~/.claude/bin/gc-read.sh *).

set -euo pipefail

DB="$HOME/.claude/prompt-history.db"
PROJECT="$(basename "$PWD")"
POINTER="$HOME/.claude/state/current-session-$PROJECT"
CMD="${1:-}"

# The prompt hook writes the resolved session row id to POINTER on every prompt.
# Prefer it: "newest open row for this project" mis-resolves as soon as a
# mid-session /handoff has closed the row. Falls back to the old query for a
# brand-new session that hasn't submitted a prompt yet.
resolve_session_id() {
  local sid=""
  if [ -f "$POINTER" ]; then
    sid="$(tr -dc '0-9' < "$POINTER" 2>/dev/null || true)"
    # Ignore a pointer to a row that no longer exists (e.g. a restored DB).
    if [ -n "$sid" ] && [ -z "$(sqlite3 "$DB" "SELECT 1 FROM sessions WHERE id=$sid;")" ]; then
      sid=""
    fi
  fi
  if [ -z "$sid" ]; then
    sid="$(sqlite3 "$DB" "SELECT id FROM sessions WHERE project='$PROJECT' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;")"
  fi
  printf '%s' "$sid"
}

case "$CMD" in
  project)
    echo "$PROJECT"
    ;;
  current-session)
    # id|started_at of the current session (contract: slash commands parse this)
    SID="$(resolve_session_id)"
    if [ -n "$SID" ]; then
      sqlite3 "$DB" "SELECT id, started_at FROM sessions WHERE id=$SID;"
    fi
    ;;
  last-summary)
    # summary|ended_at of the most recent ENDED session
    sqlite3 "$DB" "SELECT summary, ended_at FROM sessions WHERE project='$PROJECT' AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1;"
    ;;
  pulse-prompts)
    # last 5 prompts in the current session, truncated to 200 chars
    SID="$(resolve_session_id)"
    if [ -n "$SID" ]; then
      sqlite3 "$DB" "SELECT substr(prompt, 1, 200) FROM prompts WHERE session_id=$SID ORDER BY id DESC LIMIT 5;"
    fi
    ;;
  today-counts)
    # today's prompt/session/commit counts for this project
    sqlite3 "$DB" "SELECT COUNT(*) as prompts FROM prompts WHERE project='$PROJECT' AND date(timestamp) = date('now'); SELECT COUNT(*) as sessions FROM sessions WHERE project='$PROJECT' AND date(started_at) = date('now'); SELECT COUNT(DISTINCT c.hash) as commits FROM commits c JOIN sessions s ON c.session_id = s.id WHERE s.project='$PROJECT' AND date(c.timestamp) = date('now');"
    ;;
  unsummarized-context)
    # Recent unsummarized days for current project, with raw data for inline /readup synthesis.
    # Output: {"total": N, "days": [{date, prompts, commits, sessions}]}.
    # If total == 0 or > 5: days is empty (caller skips; nightly handles bulk cases).
    PROMPT_LAB_DIR="${PROMPT_LAB_DIR:-$HOME/src/prompt-lab}"
    "$PROMPT_LAB_DIR/.venv/bin/python" -c "
import json, sys
sys.path.insert(0, '$PROMPT_LAB_DIR')
from store import get_store
s = get_store()
pairs = [(p, d) for (p, d) in s.get_unsummarized_days() if p == '$PROJECT']
total = len(pairs)
if total == 0 or total > 5:
    print(json.dumps({'total': total, 'days': []}))
else:
    out = []
    for p, d in pairs:
        data = s.get_day_data(p, d)
        out.append({
            'date': d,
            'prompts': [x['prompt'][:500] for x in data.get('prompts', []) if x.get('prompt')][:50],
            'commits': [f\"{c['hash'][:8]}: {c['message']}\" for c in data.get('commits', []) if c.get('message')],
            'sessions': [s2.get('summary', '') for s2 in data.get('sessions', []) if s2.get('summary')],
        })
    print(json.dumps({'total': total, 'days': out}))
"
    ;;
  weekly-rollup-check)
    # completed weeks for this project that don't yet have a weekly rollup
    sqlite3 -header "$DB" "SELECT ds.week_start, ds.days, ds.ids, ds.summaries, ds.prompts, ds.sessions, ds.commits FROM (SELECT date(date, 'weekday 1', '-7 days') as week_start, COUNT(*) as days, GROUP_CONCAT(id) as ids, GROUP_CONCAT(summary, ' | ') as summaries, SUM(prompt_count) as prompts, SUM(session_count) as sessions, SUM(commit_count) as commits FROM daily_summaries WHERE project='$PROJECT' AND date < date('now', 'weekday 1') GROUP BY week_start) ds LEFT JOIN weekly_rollups wr ON wr.project='$PROJECT' AND wr.week_start = ds.week_start WHERE wr.id IS NULL ORDER BY ds.week_start DESC;"
    ;;
  *)
    echo "usage: gc-read.sh {project|current-session|last-summary|pulse-prompts|today-counts|weekly-rollup-check|unsummarized-context}" >&2
    exit 2
    ;;
esac
