---
name: readup
description: Start a session — register a session row, sync to remote, read project context
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Read, Write, Edit, Glob
---

Start a session. Be concise.

Note: the SessionStart hook already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines. **Do not re-fetch any of that.** This command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session` (this will prompt — writes aren't auto-allowed)
2. Remote check (no pull): `git fetch --quiet --all --prune && git status -sb` for the current branch, then `git for-each-ref --format='%(refname:short) %(upstream:short) %(upstream:track)' refs/heads | awk '$3 != ""'` to catch other local branches that are ahead/behind their upstream (useful when work happened on another machine). Also list remote branches with no local tracking: `git branch -r --no-merged | grep -v HEAD`. Fetch is cheap, never modifies the tree. If anything is behind/ahead or there are unfamiliar remote branches, flag them in the summary so the user can decide whether to `git pull --rebase` or `git checkout` manually. If everything is clean, say nothing.
3. Read CLAUDE.md in full (focus on Next Steps + project conventions). The hook's injected context covers recent activity, but not project intent.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote). Open with the Machine label from the SessionStart-hook context (e.g. "On mini.") so cross-machine context is immediate.

If any branch (current or otherwise) is behind origin, end with a short ⚠️ block listing each behind branch and the suggested `git pull --rebase` / `git checkout` command. If there are remote-only branches that look like in-progress work from another machine, mention them too.

If the user passed arguments with this command, address those — don't suggest a separate task.
