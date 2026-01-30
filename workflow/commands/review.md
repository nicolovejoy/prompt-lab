---
name: review
description: Summarize recent work across sessions
allowed-tools: Bash(sqlite3:*), Bash(pwd)
---

Review and summarize recent session work.

## Parse Arguments

Arguments (all optional):
- `<N>` - number of days to look back (default: 7)
- `<project>` - filter by project name (default: all projects)

Examples:
- `/review` - last 7 days, all projects
- `/review 14` - last 14 days, all projects
- `/review 7 musicforge` - last 7 days, musicforge only

## Query Sessions

```bash
sqlite3 ~/.claude/prompt-history.db "
SELECT project, date(started_at) as date, summary
FROM sessions
WHERE summary IS NOT NULL
  AND started_at >= datetime('now', '-<N> days')
  [AND project = '<project>']
ORDER BY started_at DESC;"
```

## Synthesize

Read through the session summaries and provide:

1. **Overview** (2-3 sentences): What was the main focus across these sessions?

2. **By Project**: For each project with sessions:
   - Key accomplishments
   - Current state
   - Open threads/next steps

3. **Patterns** (optional): Any observations about workflow, recurring themes, or insights

Keep it concise - this is a quick orientation, not a detailed report.
