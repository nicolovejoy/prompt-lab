# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, intentions, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
.venv/bin/python mobile/serve.py  # local mobile PWA → localhost:8080
```

The Flask local dashboard (`dashboard/`) was retired 2026-05-28 — it had gone ~3 months stale and none of the cost-tracking work landed there. The cloud dashboard (`web/`) is the single canonical UI. `todos.py` is kept as the shared scanner but is currently unwired (its only consumer was the local dashboard); rewire it into `web/` when todos return to the UI.

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
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages, gated by hardcoded `PUBLIC_PROJECTS` allowlist. Adding a project to the allowlist is the deliberate moment its data goes public — review SQLite rows first.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with selected-projects (the consumer of `public_session_summaries` / `public_weekly_rollups`, lives at https://PianoHouseProject.org) via an append-only shared file at `~/src/.handoff/selected-projects-prompt-lab.md`. Read it at session start alongside `/readup`. New cross-repo asks go there as a new entry under `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome.

## Next Steps

### Domain migration → prompt-labs.org (SHIPPED 2026-05-29)
Cloud dashboard now lives at **https://prompt-labs.org** (Cloudflare registrar, Vercel-hosted). Replaced anomatom.com, which was dropped from the project (404, no redirect). Vercel project renamed `ground-control` → `prompt-lab` (project ID unchanged: `prj_g6Bd1VG93LUDdKwg5V4d1EaoE4FV`, so GitHub Actions secret needed no change). DB `projects.site_url` updated + synced to Turso. Verified live: 200 + auth-gated API (401). The app is domain-portable (no hardcoded domain in `web/` runtime, host-relative cookies), so any future move is a Vercel-dashboard task, not a code change. Note: prompt-labs**.com** is a $2k squatter — not ours; we own the **.org**.

### Local dashboard retired (SHIPPED 2026-05-29)
The Flask `dashboard/` (port 5111) was removed — ~3mo stale, none of the cost/alias/public_history work landed there. Cloud `web/` is the single UI. Fallout fixed same session: `python-dotenv` lived only in the deleted `dashboard/requirements.txt`, breaking CI; restored via a new root `requirements.txt` (CI + install.sh point at it). `mobile/` PWA left untouched.

### Status toggle (scoped 2026-05-28, not started)
Local dashboard (retired) had a working status `<select>`; the live cloud detail page (`web/index.html` ProjectPage) has none. To build it on cloud: (1) new auth-gated write endpoint in the read-only serverless API, (2) move status ownership to Turso so `sync_to_turso.py` stops clobbering a cloud-set value. Backend `update_project()` already accepts `status`. Not pure-frontend work.

### Todos rewire (opened 2026-05-28)
`todos.py` scanner is now unwired — its only consumer was the retired local dashboard, and `web/` has no todo handling. Rewire into the cloud app when todos return to the UI.

### Auth and sharing
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me
- **selected-projects → `/api/public_history` migration: complete on the code side** (prompt-lab `73c7de9` + `c53c04c`, selected-projects `c895eb6`). Manual cleanup still owed: (1) visual-verify PianoHouseProject.org `/projects/musicforge` Evolution section after the Vercel rebuild, (2) delete `HISTORY_TURSO_DATABASE_URL` + `HISTORY_TURSO_AUTH_TOKEN` from selected-projects Vercel env (keep plain `TURSO_*` — those serve pianohouse's own DB), (3) rotate prompt-lab Turso auth token and update `web/`'s env on Vercel. `docs/selected-projects-api-migration.md` is now historical.

### Responsible AI use paradigm (started 2026-05-17)
- "Machine voice" visual convention shipped on PianoHouseProject.org (`73cea5b` + `7475d88`): italic + muted + `↳ from claude` mono uppercase marker for any AI-authored text, including the Evolution rollups on each project page and a `<MachineNote>` MDX component for one-off blocks. First `/tenets` page in the nav documents the principle.
- Open: grow the `/tenets` list past tenet #1; consider applying the same convention to the cloud dashboard (prompt-labs.org) state summaries / weekly rollup text.

### Dashboard polish
- Review project detail layout on mobile (sidebar stacking) — note: sidebar dropped 2026-05-19 in favor of single-column; mobile audit still useful.
- Add ability to set/toggle project status (active/dormant) from detail page
- Project page UX cleanup (2026-05-19): collapsed text to teasers, dropped duplicate sidebar, capped timeline at 8 with Show More, added axes to CostChart, replaced "Site" link with hostname + self-link suppression. Cost drill-down (2026-05-20): `#/project/<name>/cost` opens a sortable detail table with filters; CostChart got a per-bar hover tooltip showing date + per-model breakdown. Next: figure out a coherent overall hierarchy — currently a header + heatmap + cost + timeline + intentions stack, no clear "above the fold" frame.

### Slash commands (current state, 2026-05-24)

Now installed: `/pulse` (session status), `/roadmap` (project digest), `/bulletin` (cross-project conventions), `/resync` (verify CLAUDE.md + open issues against actual code via parallel Explore agents, two modes: deep + `--light`). All read through `~/.claude/bin/gc-read.sh` wrappers so they bypass the simple_expansion permission gate.

The SessionStart hook (`workflow/hooks/session-start.sh`) auto-injects date + last-session summary + recent commits + bulletin headlines on every Claude launch under `~/src/*`. As of 2026-05-24 it also emits a **weekly nudge** listing custom commands not invoked in 30+ days (rate-limited via `~/.claude/state/commands-nudge.touch`). /readup now only does the things the hook deliberately skips: register session row, `git fetch --quiet && git status -sb`, full CLAUDE.md read, lazy unsummarized-day backfill, and auto-`/resync --light` when the per-project marker is >48h old AND >3 commits have landed.

Known nuance: prompt-history's slash-command counts under-report bare invocations because `log-prompt.sh` skips prompts starting with `<command-`. Rows that DO match (e.g., `/handoff` in "commit, push, /handoff") are conversational references, not invocations. Doesn't affect the nudge (which uses whitelist + 30-day cutoff) but limits any "trending command" analysis.

**Still to do:**
- Track session duration (ended_at − started_at) and surface in /review.

### /handoff trimming (in-progress design discussion, 2026-05-13)

Discussed five potential cuts. Decisions so far:
- **Point 1 — SHIPPED** (commit `342ceae`): dropped Turso sync from /handoff; moved to async SessionStart hook at `~/.claude/bin/turso-sync-maybe.sh` (per-machine, max once per 8h, was 24h). Synchronous hook warns when stale >24h (3 missed cycles). Cuts ~10s + a failure mode from every /handoff.
- **Point 2 — RESOLVED**: synthesizer schema-drift crash fixed in `242d343` (2026-05-13); schema verified healthy on both machines. The original idea — drop weekly rollup from /handoff once the nightly is proven stable — is now an optional cleanup, not a blocker.
- **Point 3 — SHIPPED** (this session): /handoff no longer upserts the GitHub URL. Moved to one-time `scripts/backfill_project_urls.py`; already populated all 15 projects under ~/src.
- **Point 4 — pending discussion**: batch the ~5 remaining `python3 -c "..."` invocations in /handoff into a single helper script. Worth doing only AFTER Point 2 lands.
- **Point 5 — pending discussion**: a Stop hook that captures commits + sets `ended_at` on session rows even when /handoff is skipped. Worth it only if you actually have many abandoned sessions.

### Cross-machine sync

SHIPPED (this session): bin scripts moved into the repo under `workflow/bin/` and `workflow/install.sh` extended to install them to `~/.claude/bin/`. The manual-step block at the end of install.sh now prints the full settings.json additions (allow rules + SessionStart hook entries).

Status by machine:
- **Laptop**: 8h Turso sync cadence; `~/.claude/settings.json` has gc-write/gc-read allows + SessionStart hooks. Operating from the new state.
- **Mini**: synced 2026-05-15 — pulled, install.sh ran, settings.json patched with allows + SessionStart hooks. Restart needed before hooks take effect.

### Synthesizer cost reduction (shipped 2026-05-17)

Three-phase migration shipped this session in response to ~$100/2-week Opus spend on the nightly LaunchAgent:

- **Phase 1** (`598401c`): `OPUS` → `SONNET` across all unattended API call sites (`synthesizer.py`, `send-review.py`, `generate-report.py`). ~5x reduction.
- **Phase 2** (`8bea382`): `/handoff` step §3.5 refreshes intentions inline (`model='claude-code'`, free under subscription). Nightly `synthesize_intentions` now uses `get_projects_needing_intentions_refresh(today)` as a safety net (active project + no intention touched yesterday/today).
- **Phase 3** (`9ab9c25`): `/readup` step §4 backfills up to 5 recent unsummarized days inline. If >5 stale, skips with a note and lets the nightly catch them.
- **Bug-prevention** (`48802e6`): `scripts/test_imports.py` Phase 3 instantiates concrete stores so abstract-method drift breaks the test instead of silently breaking `/handoff`; `handoff.md` got a top-of-file guard telling Claude to stop on Python tracebacks.

### Backfill and maintenance
- Verify nightly synthesizer actually runs on both machines (pre-req for point 2 of /handoff trimming). On the laptop in particular — LaunchAgents pause when the lid is closed.
- Migrate other projects' `.env` files to 1Password `.env.tpl` pattern.
- The schema-drift fixes shipped in `242d343` (`projects` table + `token_count`/`hostname` ALTER) are tested only via `scripts/test_imports.py` (compile check) + `scripts/test_alias_layer.py` (in-memory store). No dedicated regression test that exercises the drift scenario specifically — Task #9 from this session, deferred.

### CI/CD follow-ups
- Stale-alias URL UX: `/project/frontend` now renders musicforge data but the URL/title still say "frontend". Consider redirecting `/project/<alias>` → `/project/<canonical>` at the SPA route layer.
- Decide whether to keep the GitHub Actions deploy path forever or eventually switch to Vercel's native git integration (simpler but loses test-gates-deploy semantics). Native is fine if you trust your tests; current setup is more conservative.

### Browser automation
- Playwright MCP installed at user scope (`claude mcp add playwright -s user`). Available after next Claude restart. Scope convention is in `BULLETIN.md` — production read-only, localhost + preview URLs full access.

### Cost tracking (issue #2 — CLOSED 2026-05-24)

End-to-end live since 2026-05-19; hardened + drill-down 2026-05-20; all 5 workspace mappings seeded 2026-05-24. Architecture, operational checklist, and gotchas in `docs/cost-tracking.md`.

Open follow-ups:
- **Watch ibuild4you spend** — ~$9-10/day for the last week (2026-05-14 to 2026-05-23, ~$113 total). Verify it's intentional usage on `#/project/ibuild4you/cost`; at this pace it'd be ~$300/mo.
- Claude Code Analytics returns 0 actors for the org (external — waiting on Anthropic to flow subscription auth through to org level; no code change needed)
- Manual PRICING refresh cadence in `claude_api.py` (no automation yet)
- Anomaly detection (originally a follow-up in #2) — not implemented. Open a new issue if/when needed.
