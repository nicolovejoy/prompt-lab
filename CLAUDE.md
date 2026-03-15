# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh
```

Opens at http://localhost:5111

## Next Steps

- Verify token_count populates after a few prompts; confirm Stop hook fires on session end
- Review what else to show in Claude Code status line (`~/.claude/statusline-command.sh`) — model name, cost, git branch, session duration?
- Monitor send-review.py JSON parse reliability — fallback triggered on first Sonnet run (March 15); may need structured output or a second parse attempt
