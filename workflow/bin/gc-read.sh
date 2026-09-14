#!/bin/bash
# gc-read.sh — read-only queries against ~/.claude/prompt-history.db for slash commands.
# Resolves $PWD/basename internally so callers never need shell expansion.
# Allowed in ~/.claude/settings.json via Bash(~/.claude/bin/gc-read.sh *).

set -euo pipefail

DB="$HOME/.claude/prompt-history.db"

# The project is the REPO, not the cwd basename — see _gc_project.sh for why
# (worktrees resolved to `agent-<hash>` and every query silently read empty).
# Sourced from this script's own directory so the repo copy and the installed
# copy under ~/.claude/bin each use their own sibling. NOTE: that means
# _gc_project.sh must be installed alongside gc-read.sh; a missing helper fails
# loudly here rather than falling back, deliberately — a quiet fallback covering
# a dead primary path is this repo's signature bug.
GC_BIN_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
# shellcheck source=./_gc_project.sh
. "$GC_BIN_DIR/_gc_project.sh"
PROJECT="$(gc_resolve_project "$PWD")"

CMD="${1:-}"

# Scoped ownership is resolved from SQLite, never a shared project pointer.
resolve_session_id() {
  python3 "$GC_BIN_DIR/_gc_session_identity.py" resolve-id "$PROJECT"
}

case "$CMD" in
  project)
    echo "$PROJECT"
    ;;
  current-session)
    python3 "$GC_BIN_DIR/_gc_session_identity.py" resolve "$PROJECT" "${@:2}"
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
  today-context)
    PROMPT_LAB_DIR="${PROMPT_LAB_DIR:-$HOME/src/prompt-lab}"
    SID="$(resolve_session_id)"
    if [ -z "$SID" ]; then
      echo "No current session; run readup before gathering handoff context" >&2
      exit 3
    fi
    export PROMPT_LAB_DIR
    "$PROMPT_LAB_DIR/.venv/bin/python" "$GC_BIN_DIR/_gc_day_context.py" "$PROJECT" --session-id "$SID"
    ;;
  today-counts)
    # today's prompt/session/commit counts for this project.
    #
    # 'localtime' on BOTH sides (#48). These columns are written by
    # datetime('now'), which is UTC, and this asks "what did I do today" — a
    # human's question about a local day. Bucketing in UTC made it report 0
    # prompts and 0 sessions every evening after 5pm Pacific, which /handoff
    # then wrote into the session summary as a day with no work in it.
    sqlite3 "$DB" "SELECT COUNT(*) as prompts FROM prompts WHERE project='$PROJECT' AND date(timestamp,'localtime') = date('now','localtime'); SELECT COUNT(*) as sessions FROM sessions WHERE project='$PROJECT' AND date(started_at,'localtime') = date('now','localtime'); SELECT COUNT(DISTINCT c.hash) as commits FROM commits c JOIN sessions s ON c.session_id = s.id WHERE s.project='$PROJECT' AND date(c.timestamp,'localtime') = date('now','localtime');"
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
    # ('weekday 0','-6 days' = the containing week's Monday — 'weekday N' is
    # next-or-SAME, so 'weekday 1','-7 days' filed Mondays a week back, and
    # date('now','weekday 1') meant NEXT Monday, admitting the current week)
    sqlite3 -header "$DB" "SELECT ds.week_start, ds.days, ds.ids, ds.summaries, ds.prompts, ds.sessions, ds.commits FROM (SELECT date(date, 'weekday 0', '-6 days') as week_start, COUNT(*) as days, GROUP_CONCAT(id) as ids, GROUP_CONCAT(summary, ' | ') as summaries, SUM(prompt_count) as prompts, SUM(session_count) as sessions, SUM(commit_count) as commits FROM daily_summaries WHERE project='$PROJECT' AND date < date('now', 'weekday 0', '-6 days') GROUP BY week_start) ds LEFT JOIN weekly_rollups wr ON wr.project='$PROJECT' AND wr.week_start = ds.week_start WHERE wr.id IS NULL ORDER BY ds.week_start DESC;"
    ;;
  *)
    echo "usage: gc-read.sh {project|current-session [id]|last-summary|pulse-prompts|today-context|today-counts|weekly-rollup-check|unsummarized-context}" >&2
    exit 2
    ;;
esac
