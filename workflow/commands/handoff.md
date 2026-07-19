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
  This writes the summary only — it does NOT end the session. Step 7 does that,
  last, so that work continuing after a mid-session `/handoff` still logs to the
  right row.

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

If no weeks need rollups, skip silently.

> **Note:** `/handoff` deliberately does NOT write the public `public_session_summaries` / `public_weekly_rollups` tables. Those are written ONLY by the hand-reviewed, git-committed `scripts/backfill_public_*.py` one-shots (see CLAUDE.md `web/api/public_history.py` invariant). Public portfolio data is a deliberate, per-project publish action — never an automatic per-session write.

## 5. Commit doc changes if any

Note: Turso sync used to run here. It now runs automatically via the async SessionStart hook (`~/.claude/bin/turso-sync-maybe.sh`) at most once per 8h on each machine. If you need to force a sync right now: `~/src/prompt-lab/.venv/bin/python ~/src/prompt-lab/sync_to_turso.py --days 1`.

GitHub URL upsert used to live here too — moved to a one-time script at `scripts/backfill_project_urls.py`. Re-run it if you add a new project or rename a remote.

## 6. Cross-repo handoff channel

If this session produced anything a peer repo (selected-projects, prntd) needs to know — a question, a change to a shared contract, a follow-up — post it to the handoff log instead of letting it evaporate:

```
~/.claude/bin/handoff.sh append <file> "### YYYY-MM-DD prompt-lab → <peer>: <subject>

<body>"
```

Files: `selected-projects-prompt-lab.md`, `prntd-prompt-lab.md` (in `~/src/.handoff`). The wrapper inserts at the top of `## Active` and pushes atomically. If you instead hand-edited a handoff file (e.g. moved an acted-on entry to `## Archived`), flush it with `~/.claude/bin/handoff.sh sync`. Non-zero exit means the note was kept locally but not pushed (3 = conflict, resolve in `~/src/.handoff`; 4 = offline, re-run `sync` later) — surface it, don't ignore it. Nothing to coordinate → skip silently.

## 7. End the session

Last step, after everything else has been written:

```bash
~/.claude/bin/gc-write.sh end-session <session_id>
```

Use the same `<session_id>` from step 1. This stamps `ended_at`. It is safe to run
`/handoff` again later in the same conversation — prompts are bound to the real
Claude Code session id, so a closed row keeps receiving them and re-running just
refreshes the summary and end time.
