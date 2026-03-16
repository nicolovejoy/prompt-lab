# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh
```

Opens at http://localhost:5111

## Next Steps

- Check send-review.log after tonight's 2:30am run — first run with tool use structured output
- Verify token_count populates after a few prompts; confirm Stop hook fires on session end
- Review what else to show in Claude Code status line (`~/.claude/statusline-command.sh`) — model name, cost, git branch, session duration?
