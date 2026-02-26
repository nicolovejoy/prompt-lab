---
name: report
description: Write up a polished report of work done across projects
allowed-tools: Bash(sqlite3:*)
---

Generate a clean work summary report grouped by project.

## Parse Arguments

Arguments (all optional):
- `<N>` - number of days to look back (default: 1)

Examples:
- `/report` - last 24 hours
- `/report 7` - last 7 days
- `/report 30` - last 30 days

## Query Sessions

Build the modifier as a variable to avoid shell heuristic flags on the sqlite3 command:

```bash
MOD="-<N> days" && sqlite3 ~/.claude/prompt-history.db "SELECT project, summary, started_at FROM sessions WHERE summary IS NOT NULL AND started_at >= datetime('now', '$MOD') ORDER BY started_at DESC;"
```

Also query daily summaries for the same window:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT date, summary FROM daily_summaries WHERE date >= date('now', '$MOD') ORDER BY date DESC;"
```

## Format

Output a markdown report:

**Header:** `## Work Report — Last <N> day(s)` with today's date

**Body:** One section per project. For each:
- Bold project name as heading
- 50 words or less summarizing what was accomplished (no next steps, no open threads — only what was done)
- If multiple sessions exist for a project, synthesize them into one summary

Skip projects with no meaningful activity. Group related sessions under the same project name even if the path differs (e.g. `/Users/nico/src/home-assistant` and `home-assistant` are the same project).

Keep the tone factual and direct. This is a shareable summary, not a dev orientation.
