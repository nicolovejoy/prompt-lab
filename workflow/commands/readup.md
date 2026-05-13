---
name: readup
description: Start a session by understanding project context and recent work
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(date:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session` (this will prompt — writes aren't auto-allowed)
2. Pull remote changes: `git pull --rebase` — if it fails (conflicts, detached HEAD, no upstream), report the error and stop so the user can resolve it before the session starts
3. Read CLAUDE.md (focus on Next Steps)
4. `git log --oneline -5`
5. `date "+Today is %A, %B %-d, %Y"` — state this explicitly at the top of your summary
6. Last session: `~/.claude/bin/gc-read.sh last-summary`

## Then

Start with "Last session (<relative time ago>): <summary>" if a prior session exists. Then summarize in a few lines: what happened recently, where things stand, what's next.

If the user passed arguments with this command, address those — don't suggest a separate task.
