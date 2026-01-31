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

## Gather Context

1. Read CLAUDE.md (especially Next Steps)
2. Run `git log --oneline -5` for recent commits
3. Run `git status` for uncommitted changes

## Clean Up Docs (while reading)

Fix anything stale:
- Remove completed Next Steps
- Trim outdated info

Keep changes minimal.

## Then

1. Summarize: recent work, current state, next task
2. Suggest ONE focused task for this session

**Ralph Wiggum principle**: One task per session keeps context fresh. Complete it, validate it, commit it. If the task is too big, break it down first.

Keep it concise.
