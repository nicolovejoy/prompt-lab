---
name: roadmap
description: Read-only digest of this project's roadmap — Next Steps from CLAUDE.md + open GitHub issues + active intentions
allowed-tools: Bash(~/.claude/bin/gc-read.sh:*), Bash(gh:*), Bash(sed:*), Read
---

Show a terse roadmap for the current project. Read-only — never edits CLAUDE.md, never creates issues. ~15 lines max.

## Do (in parallel)

1. CLAUDE.md Next Steps section: `sed -n '/^## Next Steps/,$p' CLAUDE.md` (skip silently if no such section exists)
2. Open GitHub issues: `gh issue list --state open --limit 10 --json number,title,labels` (may prompt for permission; skip silently if `gh` is unavailable or not a GitHub repo)
3. Active intentions (synthesized from prompt history): `~/.claude/bin/gc-read.sh intentions`

## Then

Output in this exact shape:

```
## <project name> roadmap

Next steps (from CLAUDE.md):
- <top 4–6 items, flattened across subsections, prefer concrete actionable ones over aspirational>

Open issues:
- #<num> <title>
- (or: "none" if empty)

Active intentions (synthesized):
- <top 3, prefer items that match Next Steps themes>
```

Rules:
- Do not invent items not in the sources
- If an intention duplicates a Next Step or issue, omit it
- Prefer items mentioning concrete files/features over vague ones
- No prose intro, no recap, no "Suggest" line (that's /pulse's job)
- If all three sources are empty, say "No roadmap data" and stop
