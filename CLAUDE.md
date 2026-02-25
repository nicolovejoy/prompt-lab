# prompt-lab

**Prompt Analyst** — web dashboard for tracking prompts and synthesizer output from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh
```

Opens at http://localhost:5111

## Next Steps

- Set up cron job for synthesizer.py (nightly --all) with email notifications on progress
- Test full workflow end-to-end on fresh machine
- Add tag filtering dropdown
- Allow editing session summaries in dashboard
- Clean up frontend TODOs: fetch error handling, rename #prompts container, remove statClick wrapper
- Consolidate combined_stats into single query with subselects

## Backlog

- Review /readup in MusicForge - can we remove it now that prompt-lab exists?
