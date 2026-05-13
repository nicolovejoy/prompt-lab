---
name: pulse
description: Quick status of the current session — what we're in the middle of, just did, and one suggested next step
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*)
---

Quick status check. Cheap and terse — the user just walked back to this window and forgot the context.

## Do (in parallel)

1. Current session id: `~/.claude/bin/gc-read.sh current-session`
2. Last 5 prompts in this session: `~/.claude/bin/gc-read.sh pulse-prompts`
3. Working tree: `git status --short`
4. Branch + last commit: `git log --oneline -1 && git rev-parse --abbrev-ref HEAD`

## Then

Output exactly this shape, 5 lines max:

- **In progress:** (what the most recent 1–2 prompts + uncommitted files imply)
- **Just did:** (one line — last commit or the prior prompt's outcome)
- **Open:** (what's not yet committed or what the user asked for that isn't done)
- **Suggest:** one concrete next action

No prose intro, no recap of the conversation, no markdown headers beyond the bolded labels. If no current session exists, say so and fall back to `git status` + last commit.
