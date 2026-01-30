---
name: readup
description: Start a session by understanding project context and recent work
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Read, Write, Edit, Glob, AskUserQuestion
---

Orient me on this project.

## Register Session Start

1. Get project name from `pwd` (last path component)
2. Insert new session:
   ```bash
   sqlite3 ~/.claude/prompt-history.db "INSERT INTO sessions (project) VALUES ('<project>');"
   ```

## Curate Last Session's Prompts

Query unrated prompts from last session:
```bash
sqlite3 ~/.claude/prompt-history.db "SELECT id, substr(prompt, 1, 60) FROM prompts WHERE project='<project>' AND utility IS NULL ORDER BY timestamp DESC LIMIT 10;"
```

If prompts exist:
- Show as multi-select: "Keep any prompts from last session?"
- Selected → set utility=4
- Unselected → delete from db

Skip if no unrated prompts.

## Gather Context

1. Read CLAUDE.md (especially Next Steps)
2. Read devlog.md last entry (if exists)
3. Run `git log --oneline -5` for recent commits
4. Run `git status` for uncommitted changes

## Clean Up Docs (while reading)

Fix anything stale:
- Remove completed Next Steps
- Trim outdated info

Keep changes minimal.

## Then

1. Summarize: recent work, current state, Next Steps
2. Ask what to work on

Keep it concise.
