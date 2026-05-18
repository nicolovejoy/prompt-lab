---
name: handoff
description: End a session by updating docs and prepping for next time
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(python3:*), Bash(pwd), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Read, Write, Edit, Glob
---

Close out this session. Be concise.

**If any Python step prints a Python traceback (e.g. `TypeError`, `ImportError`, `KeyError`), STOP. Surface the full traceback to the user before continuing to subsequent steps. The persistence python3 one-liners below silently fail to write rows on traceback — do not pretend success.**

## 0. Check for uncommitted changes

```bash
git status --porcelain
```

If there are uncommitted changes, list the changed files and ask the user whether to continue the handoff or stop so they can commit first. If clean, proceed silently.

## 1. Get session info

```bash
~/.claude/bin/gc-read.sh current-session
```

## 2. Do in parallel

- **Capture commits** since session start:
  ```bash
  git log --oneline --since="<started_at>" --format="%H|%s"
  ```
  Insert each: `INSERT OR IGNORE INTO commits (hash, message, session_id) VALUES (...);`

- **Write session summary** (50 words max): what was done, what's next. Pipe the summary via stdin so single quotes / metacharacters don't break escaping:
  ```bash
  ~/.claude/bin/gc-write.sh update-session-summary <session_id> <<'SUMMARY'
  <your 50-word summary here>
  SUMMARY
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
~/.claude/bin/gc-read.sh today-counts
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

## 3.5 Update intentions for this project

Pull the context the synthesizer normally uses:

```bash
~/.claude/bin/gc-read.sh intentions-context
```

This returns the canonical project name, the last 14 days of daily summaries (with their IDs), and currently active intentions (with their IDs).

Synthesize an updated intentions list, drawing on the summaries above + this session's work. Rules:
- Keep 3-8 high-level project goals max (e.g. "Migrate to new DB schema", not "Fix typo in serializer.py")
- Existing intentions: include their `id` and update `status` if needed (active → completed when work is clearly done; stalled when no recent activity)
- New intentions: set `id` to null
- Drop intentions that have been completed and rolled into a weekly rollup

Write to `/tmp/gc-intentions-<project>-<session_id>.json`:

```json
{
  "project": "<canonical project name from gc-read.sh output>",
  "intentions": [
    {"id": <existing-id or null>, "intention": "<text>", "status": "active|completed|stalled|abandoned"}
  ],
  "evidence_summary_ids": [<summary id 1>, <summary id 2>, ...]
}
```

IMPORTANT: use these exact command forms to persist:

```bash
python3 -c "
import json, sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
d = json.load(open('/tmp/gc-intentions-<project>-<session_id>.json'))
s = get_store(); s.migrate()
for item in d['intentions']:
    s.upsert_intention(
        id=item.get('id'),
        project=d['project'],
        intention=item['intention'],
        evidence_summary_ids=d['evidence_summary_ids'],
        status=item['status'],
        model='claude-code',
    )
s.close()
print(f\"Intentions updated for {d['project']} ({len(d['intentions'])} items)\")
"
```

This replaces what the nightly synthesizer used to do for this project — saves an API call per /handoff. The synthesizer is now a safety net: it only runs intentions for projects with a daily summary today but no fresh intentions, which means the nightly batch shrinks dramatically when /handoff has been used.

## 4. Check for weekly rollup

Check if any completed weeks for this project need a rollup:

```bash
~/.claude/bin/gc-read.sh weekly-rollup-check
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

## 5. Commit doc changes if any

Note: Turso sync used to run here. It now runs automatically via the async SessionStart hook (`~/.claude/bin/turso-sync-maybe.sh`) at most once per 8h on each machine. If you need to force a sync right now: `~/src/prompt-lab/.venv/bin/python ~/src/prompt-lab/sync_to_turso.py --days 1`.

GitHub URL upsert used to live here too — moved to a one-time script at `scripts/backfill_project_urls.py`. Re-run it if you add a new project or rename a remote.
