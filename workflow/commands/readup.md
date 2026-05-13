---
name: readup
description: Start a session — register a session row, sync to remote, read project context
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

Note: the SessionStart hook already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines. **Do not re-fetch any of that.** This command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session` (this will prompt — writes aren't auto-allowed)
2. Remote check (no pull): `git fetch --quiet && git status -sb` — fetch is cheap, never modifies the tree. If status shows "behind N commits", flag it in the summary so the user can decide whether to `git pull --rebase` manually. If status shows "ahead", flag that too. If clean, say nothing.
3. Read CLAUDE.md in full (focus on Next Steps + project conventions). The hook's injected context covers recent activity, but not project intent.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote).

If `git status -sb` showed "behind N commits", end with:
> ⚠️ Behind origin by N commits. Run `git pull --rebase` when ready to integrate.

If the user passed arguments with this command, address those — don't suggest a separate task.
