---
name: readup
description: Start a session by understanding project context and recent work
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Bash(cd:*), Bash(ls:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

## Do (in parallel)

1. Register session: `sqlite3 ~/.claude/prompt-history.db "INSERT INTO sessions (project, hostname) VALUES ('$(basename $PWD)', '$(hostname -s)');"`
2. Pull remote changes: `git pull --rebase` — if it fails (conflicts, detached HEAD, no upstream), report the error and stop so the user can resolve it before the session starts
3. Read CLAUDE.md (focus on Next Steps)
4. `git log --oneline -5`
5. `date "+Today is %A, %B %-d, %Y"` — state this explicitly at the top of your summary
6. Last session: `sqlite3 ~/.claude/prompt-history.db "SELECT summary, ended_at FROM sessions WHERE project='$(basename $PWD)' AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1;"`

## Then

Start with "Last session (<relative time ago>): <summary>" if a prior session exists. Then summarize in a few lines: what happened recently, where things stand, what's next.

If the user passed arguments with this command, address those — don't suggest a separate task.
