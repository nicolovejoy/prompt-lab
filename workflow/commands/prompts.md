---
name: prompts
description: Query past prompts by project, tags, or utility
allowed-tools: Bash(sqlite3:*), Bash(pwd)
---

Search prompt history.

## Parse Arguments

Arguments (all optional):
- `<project>` - filter by project name
- `rated` - only utility 4+
- `tag:<name>` - filter by tag (comma-separated in db)

## Build Query

Base query:
```sql
SELECT
  COALESCE(utility, '-') as util,
  project,
  substr(prompt, 1, 80) as prompt,
  tags
FROM prompts
```

Add WHERE clauses based on arguments:
- If project specified: `WHERE project = '<project>'`
- If `rated`: `WHERE utility >= 4`
- If `tag:<name>`: `WHERE tags LIKE '%<name>%'`

Order and limit:
```sql
ORDER BY id DESC LIMIT 20
```

## Execute

```bash
sqlite3 -separator ' | ' ~/.claude/prompt-history.db "<query>"
```

## Display

Format output as list:
```
[util] project: prompt text...
       tags: tag1, tag2
```

If no results, say "No prompts found."
