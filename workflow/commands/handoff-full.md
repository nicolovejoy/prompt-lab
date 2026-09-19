---
name: handoff-full
description: Close a session and refresh the whole-day summary and weekly rollups now
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(python3:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Read, Write
---

Codex: this full-handoff path is unavailable under the DB-denial profile until
its separate host context/synthesis contract passes review. Report that limitation
and stop; do not execute the Claude instructions below, escalate, or queue a routine
handoff as a substitute for this explicit full request.

Claude Code: continue with the existing flow below.

Use only when explicitly requested. Follow `/handoff` (Codex: `$source-command-handoff`)
through saving the session summary and capturing commits, but defer its final
`end-session` until the synthesis below is saved. Do not run document maintenance.
Stop and report any failed operation or traceback; never claim a failed save succeeded.

## Refresh the daily summary

After the session summary and commits by routine handoff have been saved, get the whole
Pacific calendar day as bounded JSON:

```bash
~/.claude/bin/gc-read.sh today-context
```

Synthesize from every session summary, the prompts and commits, and
`existing_daily` (the prior daily prose and decisions), together with this
conversation. Preserve the other agents' work; do not replace the day with an
account of only this session. Copy the exact `counts`, `project`, `date`, and
`context_revision` and `synthesis_session_id` from the output, even if `truncation` reports clipped or
omitted input. Sessions include those that started, ended, or recorded work
that day, plus this conversation if it continued past midnight without a prompt
hook; commits are deduplicated by hash. Raw context is machine-local.

Write `/tmp/gc-daily-<project>-<session_id>.json` using the validated ID:

```json
{
  "project": "<project from today-context>",
  "date": "<date from today-context>",
  "context_revision": "<context_revision from today-context>",
  "synthesis_session_id": <synthesis_session_id from today-context>,
  "model": "<claude-code|codex>",
  "summary": "<2-4 sentence summary of today's work — WHAT was done and WHY>",
  "key_decisions": ["<decision 1>", "<decision 2>"],
  "prompt_count": <n>,
  "session_count": <n>,
  "commit_count": <n>
}
```

Replace `<claude-code|codex>` with whichever you are running as (or the specific Codex model id, e.g. `gpt-6-astra`, if you want finer-grained attribution) — same substitution convention as `<project>`/`<session_id>` above.

IMPORTANT: use these exact command forms to persist the daily summary:

```bash
~/.claude/bin/gc-write.sh save-daily-summary /tmp/gc-daily-<project>-<session_id>.json
```

This checks the context revision and counts under a write lock, then archives
replaced prose before saving. If it reports that the day context changed, fetch
`today-context` again and revise the synthesis using the new input and revision.
Do not bypass the check or merely replace the revision in an old draft. If the
day rolled over, regenerate the draft for the date the new context reports.

## Refresh due weekly rollups

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
s.upsert_weekly_rollup(model='<claude-code|codex>', **d)
s.close()
print('Weekly rollup saved for', d['project'], d['week_start'])
"
```

If no weeks need rollups, skip silently.

> **Note:** `/handoff` deliberately does NOT write the public `public_session_summaries` / `public_weekly_rollups` tables. Public drafts belong to the explicit `/workflow-maintenance` command. Public portfolio data is a deliberate, per-project publish action — never an automatic per-session write.


## Finish

End only the validated session with `~/.claude/bin/gc-write.sh end-session <session_id>`.
Report what was saved and any remaining work. No automatic publication or sync.
