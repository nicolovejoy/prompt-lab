---
name: report
description: Write up a polished report of work done across projects
allowed-tools: Bash(sqlite3:*)
---

Generate a clean work summary report grouped by project.

## Parse Arguments

Arguments (all optional, any order):
- `<N>` - number of days to look back (default: 1)
- `-v` or `-verbose` - detailed report for a less technical audience

Examples:
- `/report` - last 24 hours, concise
- `/report 7` - last 7 days, concise
- `/report 3 -v` - last 3 days, verbose
- `/report -verbose 14` - last 14 days, verbose

## Query Sessions

IMPORTANT: Use these exact command forms. Do NOT use shell variables (MOD=...) — the command must start with `sqlite3` to match the allowlist:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT project, summary, started_at FROM sessions WHERE summary IS NOT NULL AND started_at >= datetime('now', printf('-%d days', <N>)) ORDER BY started_at DESC;"
```

Also query daily summaries for the same window:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT date, summary FROM daily_summaries WHERE date >= date('now', printf('-%d days', <N>)) ORDER BY date DESC;"
```

## Format

Output a markdown report:

**Header:** `## Work Report — Last <N> day(s)` with today's date

Skip projects with no meaningful activity. Group related sessions under the same project name even if the path differs (e.g. `/home/user/src/myproject` and `myproject` are the same project).

### Default (concise)

**Body:** One section per project. For each:
- Bold project name as heading
- 50 words or less summarizing what was accomplished (no next steps, no open threads — only what was done)
- If multiple sessions exist for a project, synthesize them into one summary

Keep the tone factual and direct. This is a shareable summary, not a dev orientation.

### Verbose (-v)

**Body:** One section per project. For each:
- Bold project name as heading
- 2-3 paragraph narrative explaining what was worked on, why, and what was accomplished
- Explain technical concepts briefly — assume the reader is a smart non-engineer
- Include context: what problem was being solved, what approach was taken, what the outcome was
- Mention blockers hit and how they were resolved
- If multiple sessions exist for a project, walk through them chronologically

End with a **Summary** section: 2-3 sentences on overall themes and momentum across all projects.
