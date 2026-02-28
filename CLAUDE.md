# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh
```

Opens at http://localhost:5111

## Next Steps

- Verify j/k keyboard nav works correctly in browser after Preact rewrite
- Set up cron job for synthesizer.py (nightly --all) with email notifications
- Allow editing session summaries in dashboard
- Test /report and /review in other repos — confirm no permission prompts after printf fix

## Backlog

- Review /readup in MusicForge - can we remove it now that prompt-lab exists?
