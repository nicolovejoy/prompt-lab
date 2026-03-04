---
name: handoff
description: End a session by updating docs and prepping for next time
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(pwd), Read, Write, Edit, Glob
---

Close out this session. Be concise.

## 1. Get session info

```bash
sqlite3 ~/.claude/prompt-history.db "SELECT id, started_at FROM sessions WHERE project='$(basename $PWD)' AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;"
```

## 2. Do in parallel

- **Capture commits** since session start:
  ```bash
  git log --oneline --since="<started_at>" --format="%H|%s"
  ```
  Insert each: `INSERT OR IGNORE INTO commits (hash, message, session_id) VALUES (...);`

- **Write session summary** (50 words max): what was done, what's next. Store it:
  ```bash
  sqlite3 ~/.claude/prompt-history.db "UPDATE sessions SET summary='<summary>', ended_at=datetime('now') WHERE id=<session_id>;"
  ```

- **Update CLAUDE.md** Next Steps: remove done items, add new ones (3-5 max)

- **Update MEMORY.md** if anything changed worth remembering

## 3. Commit doc changes if any
