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
2. Read devlog.md last entry (if exists)
3. Run `git log --oneline -5` for recent commits
4. Run `git status` for uncommitted changes
5. Check for IMPLEMENTATION_PLAN.md - if exists, show current/next task
6. Check for specs/ directory - note what specs exist

## Clean Up Docs (while reading)

Fix anything stale:
- Remove completed Next Steps
- Trim outdated info

Keep changes minimal.

## Then

1. Summarize: recent work, current state, next task
2. If IMPLEMENTATION_PLAN.md exists: show the next uncompleted task
3. Suggest ONE focused task for this session

**Ralph Wiggum principle**: One task per session keeps context fresh. Complete it, validate it, commit it. If the task is too big, break it down first.

If no plan exists and the project would benefit from one, suggest:
- Creating specs/ for requirements
- Creating IMPLEMENTATION_PLAN.md with prioritized tasks

Keep it concise.
