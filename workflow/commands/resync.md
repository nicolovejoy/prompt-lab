---
name: resync
description: Verify project roadmap/issue list against current code state (CLAUDE.md drifts; trust the code, not the docs)
allowed-tools: Bash(gh issue list:*), Bash(gh pr list:*), Bash(git log:*), Bash(git for-each-ref:*), Bash(git cherry:*), Bash(git branch:*), Bash(touch:*), Bash(mkdir:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Read, Agent
---

CLAUDE.md "Next Steps" and open GitHub issues drift from what's actually shipped. **Trust the code, not the docs** — every claim needs verification against current `main`. Citing a CLAUDE.md line as proof is not evidence; commit SHA + file:line is.

## Modes

- **Default (deep)**: full sweep of all Next Steps + all open issues. Run on demand when the roadmap feels stale.
- **`--light`**: only verify items whose source (CLAUDE.md line or issue) was touched in the last 7 days. Used by /readup auto-trigger. Cuts agent work substantially in mature repos.

If `$ARGUMENTS` contains `--light`, run in light mode; otherwise deep.

## Do

1. Open issues: `gh issue list --state open --limit 50 --json number,title,labels,updatedAt`
2. Recently closed: `gh issue list --state closed --search "closed:>$(date -v-14d +%Y-%m-%d 2>/dev/null || date -d '14 days ago' +%Y-%m-%d)" --json number,title,closedAt`
3. Recent commits: `git log --oneline -40` (deep) or `-20` (light)
4. Read CLAUDE.md "Next Steps" section in full
5. **Light mode only:** filter the verification set to items whose CLAUDE.md line was modified in the last 7 days (`git log --since='7 days ago' --name-only -- CLAUDE.md`) or whose issue `updatedAt` is within 7 days. Skip the rest.
6. Launch 2-3 Explore agents IN PARALLEL, each owning a cluster of items. Each must report **DONE / PARTIAL / TODO** with **commit SHA + file:line** as evidence. No CLAUDE.md citations.
7. Stale remote branches: `git for-each-ref refs/remotes/origin --format='%(refname:short)'` + `git cherry origin/main origin/<branch>` to detect merged-but-undeleted.
8. Flag duplicate issues (same bug, two numbers).
9. Touch the marker: `mkdir -p ~/.claude/state && touch ~/.claude/state/resync-$(basename "$PWD").touch`

## Report (Phase 1 — propose only)

- **Shipped-but-still-open** — close candidates with verifying SHA
- **Duplicate pairs** — close older, keep newer
- **Genuine remaining backlog** — the real /roadmap
- **Stale branches** — merged-but-undeleted on origin
- **CLAUDE.md edits** — list specific Next Steps lines that should be deleted or rewritten

## Then wait

Don't close issues, delete branches, or edit CLAUDE.md without explicit approval. User picks from the proposal.

## Relationship to other commands

- `/roadmap` flattens Next Steps + open issues without verifying. `/resync` is the verification layer.
- `/readup` auto-invokes `/resync --light` if the marker is >48h old and there are >3 commits since the marker.
