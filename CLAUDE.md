# prompt-lab

**Ground Control** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
./dashboard.sh        # main dashboard → localhost:5111
.venv/bin/python mobile/serve.py  # mobile PWA → localhost:8080
```

## Architecture

- `store/` — backend-agnostic KnowledgeStore ABC + SQLite (default) and Turso implementations
- `claude_api.py` — shared Claude API utilities, centralized env loading (.env, .env.local, synthesizer.env)
- `synthesizer.py` — nightly: daily summaries, weekly rollups, intentions, project snapshots
- `send-review.py` — nightly email via Resend, saves to review_snapshots
- `generate-report.py` — bi-monthly markdown report, saves to review_snapshots
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `mobile/` — static PWA (Preact+HTM) reads from Turso, local /ask proxy
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language

## Next Steps

### Deploy mobile PWA to Vercel
- Convert `mobile/serve.py` endpoints to Vercel serverless functions (`api/config.py`, `api/ask.py`)
- Set TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, ANTHROPIC_API_KEY as Vercel env vars
- Deploy `mobile/` as static site with `/api` functions
- Add basic auth or token check so /config doesn't serve credentials to the public
- PWA manifest + icons so it's installable on phone
- Wire a custom domain or use the Vercel default URL

### Wire Turso sync into nightly pipeline
- Add sync step to synthesizer.py `--all` (after snapshots, push to Turso)
- Or add to the launchd schedule as a separate step after synthesizer

### Dashboard improvements
- Add weekly rollups view to main dashboard (localhost:5111)
- Add review snapshots view (browse past emails/reports)
- Show project snapshots on project detail page

### Mobile PWA UX polish
- Generate PWA icons (icon-192.png, icon-512.png)
- Improve card layout and typography
- Add date range selector (currently hardcoded to 7 days for overview)
- Better loading states and error handling

### Backfill and maintenance
- Verify nightly cron generates rollups for all projects (not just /handoff ones)
- Check first automated report on April 1 (generate-report.py via launchd)
