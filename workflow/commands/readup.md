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

## 4. Backfill recent unsummarized days (lazy synthesis)

Pull recent unsummarized days for this project:

```bash
~/.claude/bin/gc-read.sh unsummarized-context
```

The output is `{"total": N, "days": [...]}`. Behavior:

- `total == 0` → skip silently.
- `total > 5` → print one line ("N unsummarized days; nightly synthesizer will catch them") and skip. Avoids piling a long batch into a session-start command.
- `total ∈ [1, 5]` → for each entry in `days`, synthesize a daily summary from its `prompts`/`commits`/`sessions` (focus on WHAT was done and WHY, 2-4 sentences, 1-3 key decisions). Write to `/tmp/gc-daily-<project>-<session_id>-<date>.json` with shape:

```json
{
  "project": "<basename of pwd>",
  "date": "<the day from the helper>",
  "summary": "<2-4 sentence summary>",
  "key_decisions": ["<decision 1>", "<decision 2>"],
  "prompt_count": <len(day.prompts)>,
  "session_count": <len(day.sessions)>,
  "commit_count": <len(day.commits)>
}
```

Persist each via:

```bash
python3 -c "
import json, sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
d = json.load(open('/tmp/gc-daily-<project>-<session_id>-<date>.json'))
s = get_store(); s.migrate()
s.upsert_daily_summary(model='claude-code', **d)
s.close()
print('Daily summary saved for', d['project'], d['date'])
"
```

This saves the nightly synthesizer from running for these days (~$0.02-0.04 each at Sonnet rates). The nightly remains as safety net for projects you don't open via /readup.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote). Open with the Machine label from the SessionStart-hook context (e.g. "On mini.") so cross-machine context is immediate.

If any branch (current or otherwise) is behind origin, end with a short ⚠️ block listing each behind branch and the suggested `git pull --rebase` / `git checkout` command. If there are remote-only branches that look like in-progress work from another machine, mention them too.

If the user passed arguments with this command, address those — don't suggest a separate task.
