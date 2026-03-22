---
name: ask
description: Ask a question about your work history across projects
allowed-tools: Bash(sqlite3:*), Bash(python3:*)
---

Answer the user's question using the knowledge store. The question is: $ARGUMENTS

## 1. Gather context

Run these queries to get relevant data. Adjust date ranges based on what the question is asking about (default to 14 days if unclear).

Recent daily summaries:

```bash
sqlite3 -header ~/.claude/prompt-history.db "SELECT date, project, summary, key_decisions FROM daily_summaries ORDER BY date DESC LIMIT 30;"
```

Active intentions:

```bash
sqlite3 -header ~/.claude/prompt-history.db "SELECT project, intention, status, first_seen, last_seen FROM intentions WHERE status = 'active' ORDER BY last_seen DESC;"
```

Weekly rollups:

```bash
sqlite3 -header ~/.claude/prompt-history.db "SELECT project, week_start, narrative, highlights FROM weekly_rollups ORDER BY week_start DESC LIMIT 12;"
```

Project snapshots:

```bash
sqlite3 -header ~/.claude/prompt-history.db "SELECT project, snapshot_date, data FROM project_snapshots ORDER BY snapshot_date DESC;"
```

## 2. Answer the question

Using the data above, answer the user's question directly. Be specific — cite dates, project names, and details from the data. If the question asks about a specific project, focus on that project's data. If it asks about time or activity, use prompt/session/commit counts from summaries.

Keep the answer concise. Don't dump raw data — synthesize it into a clear answer.
