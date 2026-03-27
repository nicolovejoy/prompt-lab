---
name: readup
description: Start a session by understanding project context and recent work
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Bash(cd:*), Bash(ls:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

## Do (in parallel)

1. Register session: `sqlite3 ~/.claude/prompt-history.db "INSERT INTO sessions (project, hostname) VALUES ('$(basename $PWD)', '$(hostname -s)');"`
2. Read CLAUDE.md (focus on Next Steps)
3. `git log --oneline -5`
4. `date "+Today is %A, %B %-d, %Y"` — state this explicitly at the top of your summary

## Then

Summarize in a few lines: what happened recently, where things stand, what's next.

If the user passed arguments with this command, address those — don't suggest a separate task.
