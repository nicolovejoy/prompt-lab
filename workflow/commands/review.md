---
name: review
description: Summarize recent work across sessions
allowed-tools: Bash(sqlite3:*), Bash(pwd)
---

Review and summarize recent session work.

## Parse Arguments

Arguments (all optional, any order):
- `<N>` - number of days to look back (default: 7)
- `<project>` - filter by project name (default: all projects)
- `-v` or `-verbose` - verbose mode for a less technical audience

Examples:
- `/review` - last 7 days, all projects
- `/review 14` - last 14 days, all projects
- `/review 7 my-project` - last 7 days, my-project only
- `/review 3 -v` - last 3 days, verbose
- `/review -verbose 14` - last 14 days, verbose

## Query Sessions

IMPORTANT: Use these exact command forms. Do NOT use shell variables — the command must start with `sqlite3` to match the allowlist:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT project, date(started_at) as date, summary FROM sessions WHERE summary IS NOT NULL AND started_at >= datetime('now', printf('-%d days', <N>)) ORDER BY started_at DESC;"
```

Also query daily summaries for the same window:

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT date, project, summary FROM daily_summaries WHERE date >= date('now', printf('-%d days', <N>)) ORDER BY date DESC;"
```

## Synthesize

Read through the session summaries and daily summaries. Use the daily summaries for high-level context and session summaries for detail.

### Default (concise)

This is a developer orientation — help me quickly get back up to speed.

1. **Overview** (2-3 sentences): What was the main focus across these sessions?

2. **By Project**: For each project with sessions:
   - Key accomplishments
   - Current state
   - Open threads/next steps

3. **Patterns** (optional): Any observations about workflow, recurring themes, or insights

Keep it concise - this is a quick orientation, not a detailed report.

### Verbose (-v)

This is a narrative summary for a smart non-technical audience.

**Header:** `## Work Review — Last <N> day(s)` with today's date

**Body:** One section per project. For each:
- Bold project name as heading
- 2-3 paragraph narrative explaining what was worked on, why, and what was accomplished
- Explain technical concepts briefly — spell out acronyms, say what tools do
- Include context: what problem was being solved, what approach was taken, what the outcome was
- Mention blockers hit and how they were resolved
- If multiple sessions exist for a project, walk through them chronologically

Tone: matter-of-fact. This is a factual record, not a performance review. Do not praise or editorialize about productivity. Do not declare anything "complete" or "done" — work is always ongoing, just at different stages. Describe where things stand, not that they're finished.

End with a **Summary** section: 2-3 sentences on overall themes and patterns across all projects.
