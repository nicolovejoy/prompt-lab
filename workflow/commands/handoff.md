---
name: handoff
description: End a session by updating docs and prepping for next time
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Read, Write, Edit, Glob
---

Quick handoff for next session.

## Capture Commits

1. Get project name from `pwd`
2. Get session start time:
   ```bash
   sqlite3 ~/.claude/prompt-history.db "SELECT started_at FROM sessions WHERE project='<project>' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;"
   ```
3. Log commits since session start:
   ```bash
   git log --oneline --since="<timestamp>" --format="%H|%s"
   ```
4. Insert commits (if any):
   ```bash
   sqlite3 ~/.claude/prompt-history.db "INSERT OR IGNORE INTO commits (hash, message) VALUES ('<hash>', '<message>');"
   ```
5. Close session:
   ```bash
   sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET ended_at=datetime('now') WHERE project='<project>' AND ended_at IS NULL;"
   ```

## Update CLAUDE.md

1. Update "Next Steps" section:
   - Remove completed items
   - Add new items from this session
   - Keep 3-5 items max

## Append to devlog.md

Add dated entry:
- Summary of work done (1-2 sentences)
- Commits made (if any)

## Done

Suggest commit if there are changes.
