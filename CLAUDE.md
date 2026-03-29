# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh        # local dashboard → localhost:5111
.venv/bin/python mobile/serve.py  # local mobile PWA → localhost:8080
```

## Deploy (cloud dashboard)

```bash
cd web && vercel --prod
```

Env vars needed in Vercel: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `AUTH_SECRET`, `ANTHROPIC_API_KEY`

To self-host: fork the repo, create a Turso database, set the env vars above, deploy `web/` to Vercel.

## Architecture

- `store/` — backend-agnostic KnowledgeStore ABC + SQLite (default) and Turso implementations
- `claude_api.py` — shared Claude API utilities, centralized env loading (.env, .env.local, synthesizer.env)
- `synthesizer.py` — nightly: daily summaries, weekly rollups, intentions, project snapshots
- `send-review.py` — nightly email via Resend, saves to review_snapshots
- `generate-report.py` — bi-monthly markdown report, saves to review_snapshots
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `dashboard/` — local dashboard (Flask), reads from SQLite (raw prompts, sessions, todos)
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)

## Next Steps

### Rework project detail pages
- Redesign timeline view: expand entries on click, show full summary inline
- Improve rollups view: better visual hierarchy, narrative formatting
- Consider removing or deprioritizing Intentions sub-tab (data is noisy/stale)
- Distill key decisions on timeline to short phrases (match card style)

### Wire Turso sync into nightly pipeline
- Add sync step to synthesizer.py `--all` (after snapshots, push to Turso)
- Or add to the launchd schedule as a separate step after synthesizer

### Backfill and maintenance
- Check first automated report on April 1 (generate-report.py via launchd)
- Verify nightly cron generates rollups for all projects
