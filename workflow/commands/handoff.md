---
name: handoff
description: End a session by updating docs and prepping for next time
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Read, Write, Edit, Glob
---

Quick handoff for next session.

## Capture Commits

1. Get project name from `pwd`
2. Get session ID and start time:
   ```bash
   sqlite3 ~/.claude/prompt-history.db "SELECT id, started_at FROM sessions WHERE project='<project>' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;"
   ```
3. Log commits since session start:
   ```bash
   git log --oneline --since="<timestamp>" --format="%H|%s"
   ```
4. Insert commits (if any):
   ```bash
   sqlite3 ~/.claude/prompt-history.db "INSERT OR IGNORE INTO commits (hash, message, session_id) VALUES ('<hash>', '<message>', <session_id>);"
   ```

## Generate Session Summary

Write a brief summary (50-100 words max) covering:
- What was accomplished this session
- What's coming up next
- Any key insights or decisions made

Base this on the conversation context, commits made, and any changes to files.

Store the summary:
```bash
sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET summary='<escaped_summary>' WHERE id=<session_id>;"
```

## Close Session

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
- The session summary
- Commits made (if any)

## Done

Suggest commit if there are changes.
