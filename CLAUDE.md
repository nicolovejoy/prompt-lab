# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

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

### Auth and sharing
- Set AUTH_READ_SECRET env var in Vercel to enable reader access for friends
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me

### Dashboard polish
- Review project detail layout on mobile (sidebar stacking)
- Add ability to set/toggle project status (active/dormant) from detail page
- Wire `--states` into the launchd Sunday schedule

### Slash command improvements
- Consider adding active intentions/todos to readup output
- Track session duration (ended_at - started_at) and surface in /review
- Add error resilience to handoff synthesis step (don't block on Python failures)

### Backfill and maintenance
- Verify nightly cron generates rollups for all projects
- Migrate other projects' `.env` files to 1Password `.env.tpl` pattern

### Per-project Anthropic API keys
Separate keys for usage/cost visibility and independent revocation. Verify with `grep -r claude-sonnet-4-20250514 ~/src/` (model migration complete as of 2026-04-14, only SDK internals remain).
- [x] notemaxxing — own Anthropic workspace + key
- [x] prntd — own Anthropic workspace created, key still needs wiring
- [x] musicforge — own Anthropic workspace created (no SDK in code currently)
- [ ] prompt-lab — still using shared key, needs workspace
- [ ] ibuild4you — still using shared key, needs workspace (also watch posture-model behavior on 4.6 vs 4.0)
