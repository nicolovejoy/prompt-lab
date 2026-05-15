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

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with selected-projects (the consumer of `public_session_summaries` / `public_weekly_rollups`, lives at https://pianohouseproject.org) via an append-only shared file at `~/src/.handoff/selected-projects-prompt-lab.md`. Read it at session start alongside `/readup`. New cross-repo asks go there as a new entry under `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome.

## Next Steps

### Auth and sharing
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me
- Verify selected-projects' consumer pattern (direct Turso vs `/api/public_history`) and execute the migration if needed. Plan + effort estimate (~1hr) captured in `docs/selected-projects-api-migration.md`; selected-projects isn't checked out under `~/src/`, so first step is confirming the consumer.

### Dashboard polish
- Review project detail layout on mobile (sidebar stacking)
- Add ability to set/toggle project status (active/dormant) from detail page

### Slash commands (current state, 2026-05-13)

Now installed: `/pulse` (session status), `/roadmap` (project digest), `/bulletin` (cross-project conventions). All read through `~/.claude/bin/gc-read.sh` wrappers so they bypass the simple_expansion permission gate. `/pulse` is a 5-line digest tied to the current open session; `/roadmap` flattens CLAUDE.md Next Steps + open GH issues + active intentions; `/bulletin` reads `BULLETIN.md` at the repo root.

The SessionStart hook (`workflow/hooks/session-start.sh`) auto-injects date + last-session summary + recent commits + bulletin headlines on every Claude launch under `~/src/*`. /readup now only does the things the hook deliberately skips: register session row, `git fetch --quiet && git status -sb` (no auto-pull), full CLAUDE.md read.

**Still to do:**
- Auto-allow `Bash(~/.claude/bin/gc-write.sh *)` on the mini (already on laptop as of 2026-05-13).
- Track session duration (ended_at − started_at) and surface in /review.

### /handoff trimming (in-progress design discussion, 2026-05-13)

Discussed five potential cuts. Decisions so far:
- **Point 1 — SHIPPED** (commit `342ceae`): dropped Turso sync from /handoff; moved to async SessionStart hook at `~/.claude/bin/turso-sync-maybe.sh` (per-machine, max once per 8h, was 24h). Synchronous hook warns when stale >24h (3 missed cycles). Cuts ~10s + a failure mode from every /handoff.
- **Point 2 — UNBLOCKED on laptop, pending one verified nightly run**: synthesizer was crashing on schema drift. Laptop ran today (2026-05-13 02:25) before the `242d343` fix shipped at 13:14, so those crashes are stale. Schema is verified healthy on laptop now (`migrate()` + `get_day_data()` both succeed). Watch the 2026-05-14 02:00 laptop run; if clean, drop weekly rollup from /handoff. **Mini verification still TBD** — check its synthesizer.log + run the same `migrate()/get_day_data()` smoke test after pulling tomorrow.
- **Point 3 — SHIPPED** (this session): /handoff no longer upserts the GitHub URL. Moved to one-time `scripts/backfill_project_urls.py`; already populated all 15 projects under ~/src.
- **Point 4 — pending discussion**: batch the ~5 remaining `python3 -c "..."` invocations in /handoff into a single helper script. Worth doing only AFTER Point 2 lands.
- **Point 5 — pending discussion**: a Stop hook that captures commits + sets `ended_at` on session rows even when /handoff is skipped. Worth it only if you actually have many abandoned sessions.

### Cross-machine sync

SHIPPED (this session): bin scripts moved into the repo under `workflow/bin/` and `workflow/install.sh` extended to install them to `~/.claude/bin/`. The manual-step block at the end of install.sh now prints the full settings.json additions (allow rules + SessionStart hook entries).

Status by machine:
- **Laptop (this session's working machine)**: `~/.claude/bin/turso-sync-maybe.sh` patched to 8h cadence; `~/.claude/settings.json` has the `gc-write.sh` auto-allow. Already operating from the new state.
- **Mini**: needs `git pull && bash workflow/install.sh`, then paste the printed settings.json snippet (or just the new `gc-write.sh` allow + confirm the SessionStart hook entries exist).

### Backfill and maintenance
- Verify nightly synthesizer actually runs on both machines (pre-req for point 2 of /handoff trimming). On the laptop in particular — LaunchAgents pause when the lid is closed.
- Migrate other projects' `.env` files to 1Password `.env.tpl` pattern.
- The schema-drift fixes shipped in `242d343` (`projects` table + `token_count`/`hostname` ALTER) are tested only via `scripts/test_imports.py` (compile check) + `scripts/test_alias_layer.py` (in-memory store). No dedicated regression test that exercises the drift scenario specifically — Task #9 from this session, deferred.

### CI/CD follow-ups
- Stale-alias URL UX: `/project/frontend` now renders musicforge data but the URL/title still say "frontend". Consider redirecting `/project/<alias>` → `/project/<canonical>` at the SPA route layer.
- Decide whether to keep the GitHub Actions deploy path forever or eventually switch to Vercel's native git integration (simpler but loses test-gates-deploy semantics). Native is fine if you trust your tests; current setup is more conservative.

### Browser automation
- Playwright MCP installed at user scope (`claude mcp add playwright -s user`). Available after next Claude restart. Scope convention is in `BULLETIN.md` — production read-only, localhost + preview URLs full access.

### Cost tracking (issue #2)
- Filed `nicolovejoy/prompt-lab#2`: auto cost tracking across projects after a ~$50 exploited-API-key incident on notemaxxing. MVP would be a nightly pull from Anthropic Admin API (`/v1/organizations/usage_report`) into a new `api_costs` table, rendered on project detail + overview. Blocked on the remaining workspace migrations (prompt-lab, ibuild4you) and a new `ANTHROPIC_ADMIN_KEY` in 1Password.

### Per-project Anthropic API keys
Separate keys for usage/cost visibility and independent revocation. Verify with `grep -r claude-sonnet-4-20250514 ~/src/` (model migration complete as of 2026-04-14, only SDK internals remain).
- [x] notemaxxing — own Anthropic workspace + key
- [x] prntd — own Anthropic workspace created, key still needs wiring
- [x] musicforge — own Anthropic workspace created (no SDK in code currently)
- [ ] prompt-lab — still using shared key, needs workspace
- [ ] ibuild4you — still using shared key, needs workspace (also watch posture-model behavior on 4.6 vs 4.0)
