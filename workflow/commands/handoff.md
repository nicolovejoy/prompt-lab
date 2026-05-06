---
name: handoff
description: End a session by updating docs and prepping for next time
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(python3:*), Bash(pwd), Read, Write, Edit, Glob
---

Close out this session. Be concise.

## 0. Check for uncommitted changes

```bash
git status --porcelain
```

If there are uncommitted changes, list the changed files and ask the user whether to continue the handoff or stop so they can commit first. If clean, proceed silently.

## 1. Get session info

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT id, started_at FROM sessions WHERE project='$(basename $PWD)' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;"
```

## 2. Do in parallel

- **Capture commits** since session start:
  ```bash
  git log --oneline --since="<started_at>" --format="%H|%s"
  ```
  Insert each: `INSERT OR IGNORE INTO commits (hash, message, session_id) VALUES (...);`

- **Write session summary** (50 words max): what was done, what's next. Store it:
  ```bash
  sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET summary='<summary>', ended_at=datetime('now') WHERE id=<session_id>;"
  ```

- **Write public session summary** (1-2 sentences): a portfolio-safe rewrite of the session, suitable for a public project page. Describe what was built, shipped, or decided in plain language.

  OMIT: names of people, internal file paths, frustrations, abandoned approaches, security/auth implementation details, anything client-confidential, internal bug refs, ticket numbers, swearing.

  KEEP: shipped features, public-facing decisions, capabilities added, problems solved (in plain terms).

  If nothing publishable happened (e.g. session was pure exploration that didn't land anywhere, or content is sensitive), write an empty string and the row will be skipped.

  IMPORTANT: use these exact command forms to persist:
  ```bash
  python3 -c "
  import sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
  from store import get_store
  summary = '''<your public summary, or empty string to skip>'''
  if summary.strip():
      s = get_store(); s.migrate()
      s.upsert_public_session_summary(
          project='<project>', session_id=<session_id>,
          started_at='<started_at>', public_summary=summary.strip())
      s.close()
      print('Public session summary saved')
  else:
      print('Public session summary skipped (nothing publishable)')
  "
  ```

- **Update CLAUDE.md** Next Steps: remove done items, add new ones (3-5 max)

- **Update MEMORY.md** if anything changed worth remembering

## 3. Synthesize daily summary

Get today's counts:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT COUNT(*) as prompts FROM prompts WHERE project='$(basename $PWD)' AND date(timestamp) = date('now'); SELECT COUNT(*) as sessions FROM sessions WHERE project='$(basename $PWD)' AND date(started_at) = date('now'); SELECT COUNT(DISTINCT c.hash) as commits FROM commits c JOIN sessions s ON c.session_id = s.id WHERE s.project='$(basename $PWD)' AND date(c.timestamp) = date('now');"
```

Using what you know from this session, write a daily summary to `/tmp/gc-daily-<project>-<session_id>.json` (substitute the actual project basename and session_id from step 1 — this avoids races when handoff runs in multiple repos concurrently) with this structure:

```json
{
  "project": "<basename of pwd>",
  "date": "<today YYYY-MM-DD>",
  "summary": "<2-4 sentence summary of today's work — WHAT was done and WHY>",
  "key_decisions": ["<decision 1>", "<decision 2>"],
  "prompt_count": <n>,
  "session_count": <n>,
  "commit_count": <n>
}
```

IMPORTANT: use these exact command forms to persist the daily summary:

```bash
python3 -c "
import json, sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
d = json.load(open('/tmp/gc-daily-<project>-<session_id>.json'))
s = get_store(); s.migrate()
s.upsert_daily_summary(model='claude-code', **d)
s.close()
print('Daily summary saved for', d['project'], d['date'])
"
```

## 4. Check for weekly rollup

Check if any completed weeks for this project need a rollup:

```bash
sqlite3 -header ~/.claude/prompt-history.db "SELECT ds.week_start, ds.days, ds.ids, ds.summaries, ds.prompts, ds.sessions, ds.commits FROM (SELECT date(date, 'weekday 1', '-7 days') as week_start, COUNT(*) as days, GROUP_CONCAT(id) as ids, GROUP_CONCAT(summary, ' | ') as summaries, SUM(prompt_count) as prompts, SUM(session_count) as sessions, SUM(commit_count) as commits FROM daily_summaries WHERE project='$(basename $PWD)' AND date < date('now', 'weekday 1') GROUP BY week_start) ds LEFT JOIN weekly_rollups wr ON wr.project='$(basename $PWD)' AND wr.week_start = ds.week_start WHERE wr.id IS NULL ORDER BY ds.week_start DESC;"
```

If results come back, generate a weekly rollup for each week. Write to `/tmp/gc-weekly-<project>-<session_id>-<week_start>.json` (substitute actual values — one file per week if multiple):

```json
{
  "project": "<project>",
  "week_start": "<YYYY-MM-DD monday>",
  "narrative": "<3-5 sentence synthesis of the week's work>",
  "highlights": ["<highlight 1>", "<highlight 2>"],
  "daily_summary_ids": [<id1>, <id2>],
  "prompt_count": <sum>,
  "session_count": <sum>,
  "commit_count": <sum>
}
```

IMPORTANT: use these exact command forms to persist:

```bash
python3 -c "
import json, sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
d = json.load(open('/tmp/gc-weekly-<project>-<session_id>-<week_start>.json'))
s = get_store(); s.migrate()
s.upsert_weekly_rollup(model='claude-code', **d)
s.close()
print('Weekly rollup saved for', d['project'], d['week_start'])
"
```

After persisting each weekly rollup, also write a **public weekly rollup** — a portfolio-safe 2-3 sentence synthesis of the week's public-rewritten session summaries. Same omit/keep rules as the per-session public summary. Use the rollup's `session_count` and `commit_count` from the json above.

IMPORTANT: use these exact command forms to persist:

```bash
python3 -c "
import sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
public = '''<your public weekly rollup, or empty string to skip>'''
if public.strip():
    s = get_store(); s.migrate()
    s.upsert_public_weekly_rollup(
        project='<project>', week_of='<week_start YYYY-MM-DD monday>',
        public_summary=public.strip(),
        session_count=<session_count>, commit_count=<commit_count>)
    s.close()
    print('Public weekly rollup saved')
else:
    print('Public weekly rollup skipped (nothing publishable)')
"
```

If no weeks need rollups, skip silently.

## 5. Update project metadata

Auto-detect and save the GitHub URL for this project:

```bash
python3 -c "
import subprocess, sys, os
sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
result = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True)
if result.returncode == 0:
    url = result.stdout.strip()
    if url.startswith('git@github.com:'):
        url = 'https://github.com/' + url[len('git@github.com:'):]
    if url.endswith('.git'):
        url = url[:-4]
    if 'github.com' in url:
        s = get_store(); s.migrate()
        s.update_project(os.path.basename(os.getcwd()), github_url=url)
        s.close()
        print('GitHub URL saved:', url)
"
```

If this fails, skip silently.

## 6. Sync to Turso

Push today's summaries to the cloud dashboard:

```bash
~/src/prompt-lab/.venv/bin/python ~/src/prompt-lab/sync_to_turso.py --days 1
```

If this fails (missing creds, network error), warn but don't block the handoff.

## 7. Commit doc changes if any
