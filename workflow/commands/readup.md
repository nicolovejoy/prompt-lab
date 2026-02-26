---
name: readup
description: Start a session by understanding project context and recent work
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Bash(cd:*), Bash(ls:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

## Do (in parallel)

1. Register session: `sqlite3 ~/.claude/prompt-history.db "INSERT INTO sessions (project) VALUES ('$(basename $PWD)');"`
2. Read CLAUDE.md (focus on Next Steps)
3. `git log --oneline -5`

## Then

Summarize in a few lines: what happened recently, where things stand, what's next.

If the user passed arguments with this command, address those — don't suggest a separate task.
