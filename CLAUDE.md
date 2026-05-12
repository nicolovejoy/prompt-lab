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
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages, gated by hardcoded `PUBLIC_PROJECTS` allowlist. Adding a project to the allowlist is the deliberate moment its data goes public — review SQLite rows first.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Cross-agent handoff

This repo coordinates with selected-projects (the consumer of `public_session_summaries` / `public_weekly_rollups`, lives at https://pianohouseproject.org) via an append-only shared file at `~/src/.handoff/selected-projects-prompt-lab.md`. Read it at session start alongside `/readup`. New cross-repo asks go there as a new entry under `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome.

## Next Steps

### Auth and sharing
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me
- Investigate how selected-projects currently consumes `public_session_summaries` / `public_weekly_rollups` — if it reads Turso directly, consider migrating it to `/api/public_history` so the allowlist gates both consumers (offer-builder + selected-projects).

### Dashboard polish
- Review project detail layout on mobile (sidebar stacking)
- Add ability to set/toggle project status (active/dormant) from detail page

### Slash command improvements
- Consider adding active intentions/todos to readup output
- Track session duration (ended_at - started_at) and surface in /review
- Add error resilience to handoff synthesis step (don't block on Python failures)

### Backfill and maintenance
- Verify nightly cron generates rollups for all projects
- Migrate other projects' `.env` files to 1Password `.env.tpl` pattern
- Pre-existing schema drift to revisit: `get_overview` references a `token_count` column that doesn't exist on local `sessions`; `get_project_detail` calls `ensure_project` against a `projects` table that's only created by `dashboard/server.py` migration `007`, not by `store.migrate()`. Both fail on a clean store-only install.

### CI/CD follow-ups (fresh from 2026-05-11)
- Watch the first CI run on main (`github.com/nicolovejoy/prompt-lab/actions`) and confirm the deploy job actually shipped to `anomatom.com`. If the Vercel CLI step needs tweaking, fix it before the next push.
- Stale-alias URL UX: `/project/frontend` now renders musicforge data but the URL/title still say "frontend". Consider redirecting `/project/<alias>` → `/project/<canonical>` at the SPA route layer.
- Decide whether to keep the GitHub Actions deploy path forever or eventually switch to Vercel's native git integration (simpler but loses test-gates-deploy semantics). Native is fine if you trust your tests; current setup is more conservative.

### Per-project Anthropic API keys
Separate keys for usage/cost visibility and independent revocation. Verify with `grep -r claude-sonnet-4-20250514 ~/src/` (model migration complete as of 2026-04-14, only SDK internals remain).
- [x] notemaxxing — own Anthropic workspace + key
- [x] prntd — own Anthropic workspace created, key still needs wiring
- [x] musicforge — own Anthropic workspace created (no SDK in code currently)
- [ ] prompt-lab — still using shared key, needs workspace
- [ ] ibuild4you — still using shared key, needs workspace (also watch posture-model behavior on 4.6 vs 4.0)
