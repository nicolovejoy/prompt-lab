# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, and themes across projects. Data from `~/.claude/prompt-history.db`.

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
- `claude_api.py` — shared Claude API utilities, centralized env loading (.env, .env.local)
- `synthesizer.py` — nightly: daily summaries, weekly rollups, project snapshots
- `send-review.py` — nightly email via Resend, saves to review_snapshots
- `generate-report.py` — bi-monthly markdown report, saves to review_snapshots
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- **Data & access model: see `docs/data-and-access.md`** — the single coherent description of the three storage tiers (raw/private, processed/private, public), how public vs private is differentiated, the two-tier cloud auth, and how secrets grant access. Read it first when reasoning about what's stored where or who can see it.
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages. No read-time allowlist: it serves whatever rows exist in `public_session_summaries` / `public_weekly_rollups`, which are safe-by-construction (written only by the hand-authored `scripts/backfill_public_*.py` with scrubbed, de-identified text — never by `/handoff`, the synthesizer, or raw sync). Reconciled 2026-06-13 to exactly the consumer's 7-key historyKey manifest (`am-i-an-ai, ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase`); the table `project` column is the consumer's historyKey, NOT the display slug. The invariant to preserve is "never write un-scrubbed text into the public_* tables." Curation of *which* projects appear publicly is the consumer's job — the `selected-projects` MDX manifest (`content/projects/*.mdx`) is the single source of truth for the public site. Unknown project → empty `200`.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with selected-projects (the consumer of `public_session_summaries` / `public_weekly_rollups`, lives at https://PianoHouseProject.org) via an append-only shared file at `~/src/.handoff/selected-projects-prompt-lab.md`. Read it at session start alongside `/readup`. New cross-repo asks go there as a new entry under `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome.

## Next Steps

### Intentions fully removed (REMOVED 2026-06-24; deprecated 2026-06-23)
First froze *generation* (2026-06-23); then removed the feature entirely (2026-06-24) after Nico manually purged the rows — the data was noise (bloated past its 3-8/project target: musicforge 180 "active", ibuild4you 97) and nothing rendered it after the dashboard redesign. **Gone now, not reversible:** the `intentions` table (dropped local; **Turso copy still needs a manual `turso db shell promptlab "DROP TABLE IF EXISTS intentions;"`** — blocked from automation, harmless meanwhile since nothing reads it), all store methods (`get_intentions`/`upsert_intention`/`get_projects_needing_intentions_refresh` + the `_dedupe_intentions` helper), `web/api/intentions.py`, the `synthesizer.py --intentions` flag + `synthesize_intentions()`, the intentions sync in `sync_to_turso.py`, the `/roadmap` + `gc-read.sh` intentions subcommands, the mobile PWA's IntentionsTab, and the orphaned `themes.intention_ids` column. Tests updated (test_web_api dropped the intentions/rollups/summaries endpoint sections; test_alias_layer dropped the `_dedupe_intentions` tests); all green. If goal-tracking ever returns, build it fresh — the old completion/abandon logic never fired.

### prompt-labs.org de-indexed from search (SHIPPED 2026-06-22)
Policy A (DE-INDEX) for the auth-gated dashboard: added `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` on `/(.*)` in `web/vercel.json` + `<meta name="robots">` in `web/index.html`; `robots.txt` already `Disallow: /`. Verified live (header + robots.txt + served meta). Not Next.js so no `app/robots.ts` layer. Doesn't touch `/api/public_history` (server-to-server, not browsed).

### Public-data drift guard (SHIPPED standalone 2026-06-13; wiring + purge pending)
`scripts/check_public_allowlist.py` audits both stores' public_* tables against `docs/public-allowlist.txt` (mirror of the consumer's 7-key historyKey manifest), alias-aware, report-only (`--fix` prints unpublish commands, never runs them). Built after this session reconciled the public tables to the manifest (removed `/handoff` writes, purged byside + 12 strays — see RESOLVED note below). **Open follow-ups:** (1) **wire it in** (deferred to next session, per Nico): non-fatal post-sync check in `sync_to_turso.py` (drift is introduced at sync time) + a `/readup` surface (prompt-lab only) so a hit is actually seen — standalone alone relies on remembering, which already failed once. (2) **Purge 4 Turso-only strays the guard caught** that the local-based purge missed: `audio-journal`, `bakerylouise_v1` (underscore variant), `invitekit`, `recountly` — run `scripts/unpublish_public.py <p> --apply` for each (not yet authorized). When the manifest changes, update `docs/public-allowlist.txt` + its date.

### Shared-conventions sync across all repos (SHIPPED 2026-06-13)
`workflow/claude-md-shared.md` is the single source of truth for Nico's cross-repo output rules (clickable URLs, numbered questions, self-contained smoke-test instructions, no marker before copy-paste command blocks). `workflow/bin/sync-claude-md.sh` materializes it into a target `CLAUDE.md` between `<!-- SHARED-CONVENTIONS:BEGIN/END -->` markers — `--apply` splices only inside the markers (bespoke content untouched; creates CLAUDE.md if absent), `--check` reports `in sync`/`missing`/`drift`/`absent` via a content-hash stamp in the BEGIN marker. **Design decision: compile-to-committed-text, NOT CLAUDE.md `@import`** — verified (via claude-code-guide) that `@import` is a Claude Code *harness* feature only; cloud/headless/third-party readers see the literal `@path`, and `~/`-anchored imports break in cloud. Committed plain text is the only thing that reaches every environment. `install.sh` distributes the source to `~/.claude/claude-md-shared.md` + the script to `~/.claude/bin/`; `/readup` step 6 runs `--check` and warns on drift but **never auto-writes** (materializing into a checked-in file stays the user's explicit call). Rolled out to 30 repos (the 5 without a CLAUDE.md skipped); both machines updated. **Edit→propagate loop:** edit `claude-md-shared.md` → `./workflow/install.sh` → re-run `--apply` per repo. Caveats: (1) only binds in envs that read each repo's committed CLAUDE.md, so a repo never re-synced stays stale; (2) notemaxxing's lint-staged may have reformatted its block at commit → could show cosmetic `drift`; (3) 6 repos committed onto feature branches (block reaches their main on merge); (4) of the 30, only prompt-lab is pushed — rest are local commits awaiting per-repo push.

### Public-data surface simplified (SHIPPED 2026-06-03)
Removed the `PUBLIC_PROJECTS` read-time allowlist from `web/api/public_history.py` (PR #4, deployed). It was a third, drifting copy of "what's public" alongside the public_* table rows and the consumer's manifest. New model: the endpoint serves whatever exists in `public_session_summaries` / `public_weekly_rollups`, which are **safe-by-construction** (written only by `scripts/backfill_public_*.py` with scrubbed text). The single source of truth for *which* projects are public is now the **selected-projects MDX manifest** (`content/projects/*.mdx`). Added `scripts/unpublish_public.py <project> [--apply]` — alias-aware, dry-run-by-default tool that deletes a project's public rows from **both** local SQLite and Turso (sync only upserts, so deletes must hit Turso directly; byside had 4 local but 17 Turso rows). Unpublished byside end-to-end. Also fixed selected-projects' dead `anomatom.com` → `prompt-labs.org` API fallback in `lib/history.ts` (merged to its main). Consequence: every project with scrubbed rows is now URL-reachable (incl. client projects — all verified de-identified); use `unpublish_public.py` to pull any one. Note: `docs/selected-projects-api-migration.md` now describes the allowlist as the intended single gate — superseded/stale.

### Vibe-coding lessons doc + public page (SHIPPED 2026-06-06)
`docs/vibe-coding-lessons.md` — a 14-lesson field guide on working with Claude, extracted from real `key_decisions`/prompt history. Public GitHub links only on actually-public repos (verified prntd/ibuild4you/prompt-lab PUBLIC; byside/musicforge private → prose-only, unlinked). **Issue #3 CLOSED:** shipped as a public page at PianoHouseProject.org `/vibe-coding-lessons` (selected-projects repo, not prompt-labs.org). Lives there as `content/vibe-coding-lessons.mdx` + `app/vibe-coding-lessons/page.tsx`, top-nav "lessons". Key correction: the page first **overclaimed Nico's authorship** (machine-written prose in human-voice type, backwards from tenet #1) — rewrote with an honest machine-voice `<MachineNote>` (Claude wrote the lessons by mining Nico's real prompts; [real] prompts are his words) and cut it 60%. Added a Nico-voiced caveat to tenet #1 that clean who's-speaking separation may be unachievable. **Open follow-up: selected-projects #4** — gate the page behind auth with a teaser (deferred, needs the magic-link auth work on main). Note: shipped via isolated PRs off main (#2 create, #3 rewrite) after a two-agent collision where a concurrent selected-projects session committed a duplicate onto its local feature branch — logged in `~/src/.handoff/selected-projects-prompt-lab.md`.

### /handoff public-write steps removed — invariant now clean (RESOLVED 2026-06-13)
Chose option (a): deleted the "public session summary" + "public weekly rollup" steps from `/handoff` (`workflow/commands/handoff.md`). `public_session_summaries` / `public_weekly_rollups` are now written ONLY by the hand-reviewed, git-committed `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or sync (`sync_to_turso.py` only *propagates* existing local rows to Turso). Key finding that settled it: the "safe-by-construction" property is **not** "human-authored" (the backfill text is Claude-authored too — see `backfill_public_promptlab.py` docstring); it's "**reviewed, git-committed literal, published by a deliberate per-project one-shot**." `/handoff`'s live DB writes had neither the review gate nor the per-project opt-in, fired for every repo incl. client work, and auto-propagated to public Turso on next sync. They were also effectively dead (blocked every run by the auto-approver), and the backfill scripts are hardcoded one-shots (not incremental), so public data was never auto-fresh anyway — removing the steps lost nothing that worked. If fresh public data is wanted later, the right path is the draft-to-artifact hybrid (have `/handoff` draft scrubbed text into a reviewable backfill artifact rather than the DB), not live writes.

### Domain migration → prompt-labs.org (SHIPPED 2026-05-29)
Cloud dashboard now lives at **https://prompt-labs.org** (Cloudflare registrar, Vercel-hosted). Replaced anomatom.com, which was dropped from the project (404, no redirect). Vercel project renamed `ground-control` → `prompt-lab` (project ID unchanged: `prj_g6Bd1VG93LUDdKwg5V4d1EaoE4FV`, so GitHub Actions secret needed no change). DB `projects.site_url` updated + synced to Turso. Verified live: 200 + auth-gated API (401). The app is domain-portable (no hardcoded domain in `web/` runtime, host-relative cookies), so any future move is a Vercel-dashboard task, not a code change. Note: prompt-labs**.com** is a $2k squatter — not ours; we own the **.org**.

### Local dashboard retired (SHIPPED 2026-05-29)
The Flask `dashboard/` (port 5111) was removed — ~3mo stale, none of the cost/alias/public_history work landed there. Cloud `web/` is the single UI. Fallout fixed same session: `python-dotenv` lived only in the deleted `dashboard/requirements.txt`, breaking CI; restored via a new root `requirements.txt` (CI + install.sh point at it). `mobile/` PWA left untouched.

### Status toggle (scoped 2026-05-28, not started)
Local dashboard (retired) had a working status `<select>`; the live cloud detail page (`web/index.html` ProjectPage) has none. To build it on cloud: (1) new auth-gated write endpoint in the read-only serverless API, (2) move status ownership to Turso so `sync_to_turso.py` stops clobbering a cloud-set value. Backend `update_project()` already accepts `status`. Not pure-frontend work.

### Todos rewire (opened 2026-05-28)
`todos.py` scanner is now unwired — its only consumer was the retired local dashboard, and `web/` has no todo handling. Rewire into the cloud app when todos return to the UI.

### offer-builder → byside rename (SHIPPED 2026-05-30)
prompt-lab side of byside's GH #13 done end-to-end. Added alias `offer-builder → byside` (`scripts/alias.py`), synced to Turso, set `projects.github_url` → `nicolovejoy/byside`, and regenerated the project snapshot so the dashboard GitHub link is correct. Key finding: `web/` **never reads the `projects` table** — the home list comes from `/api/overview`, which is already alias-aware (`_resolve()`), so the dashboard groups under canonical `byside` with no code change. `web/api/projects.py` (`/api/projects`) is dead UI code (not referenced by `index.html`). The rename stays non-destructive: rows keep logging as `offer-builder` (dir unchanged), folded at read time. Byside's `/changelog` was still pointing at dead `anomatom.com` — flagged to that agent (now resolved on their side).

### Auth and sharing
- Consider contextual Ask/Reviews on project pages (inline, not nav bar)
- Migrate to Google login (OAuth) and track logins per user; admin = just me
- **selected-projects → `/api/public_history` migration: complete, manual cleanup done 2026-06-05** (prompt-lab `73c7de9` + `c53c04c`, selected-projects `c895eb6`). All three owed cleanups landed this session: (1) visual-verified PianoHouseProject.org `/projects/musicforge` Evolution section via Playwright — live, current data, machine-voice marker present; (2) deleted `HISTORY_TURSO_DATABASE_URL` + `HISTORY_TURSO_AUTH_TOKEN` from selected-projects Vercel (Preview + Production), kept plain `TURSO_*` (pianohouse's own DB) — this removed the actual exposed copy of the ground-control token; (3) **rotated** the ground-control Turso token on web's Vercel (Production/Preview/Development) and verified the new token connects (`SELECT 1` → 200). `docs/selected-projects-api-migration.md` is historical.
  - **Old token invalidated — issue #5 CLOSED 2026-06-06.** Chose the *isolate* path over a group-wide rotation: created a new Turso group `promptlab` and migrated the DB into it (dump via `turso db shell ground-control ".dump"` → `turso db create promptlab --group promptlab --from-dump`; note `--from-dump` silently no-ops, had to `turso db shell promptlab < dump.sql` to actually load). Verified all 13 tables row-for-row, repointed web's Vercel env (`TURSO_DATABASE_URL` → `libsql://promptlab-nicolovejoy.aws-us-west-2.turso.io`, `TURSO_AUTH_TOKEN` → new) + both machines' repo `.env.local` (op item **`Turso`** url+token fields updated; the separate `prompt-lab-turso-token` op item is redundant), then **destroyed `ground-control`** — which neutralizes the old per-DB token (its target DB is gone). `pianohouse` + `prntd` stay in `default`, untouched. The new `promptlab` group has its own signing key, so prompt-lab data is now cryptographically isolated from any future `default`-group token. **Gotchas found:** (1) a stale repo `.env` on the laptop loaded *before* `.env.local` (load_env is first-wins) and pinned the old URL — `rm .env` fixed it; (2) `~/.claude/synthesizer.env` is the **legacy** creds source and is effectively dead — `load_env` (claude_api.py:18) reads `REPO_DIR/.env.local` first by *absolute* path so it always wins even under launchd; mini is the only machine that runs the nightly LaunchAgents (`com.promptlab.{synthesizer,review,report}`). Follow-up DONE 2026-06-06: key-diff confirmed `.env.local` is a strict superset of `synthesizer.env` (all 7 keys present, plus `ANTHROPIC_ADMIN_KEY`), so `synthesizer.env` was dropped from `load_env`'s list (claude_api.py) + purged from README/error-messages/cost-tracking docs. The hook still *blocks* `synthesizer.env` (defense-in-depth) and `.gitignore` still lists it. Laptop's copy deleted; mini's pending a manual `rm ~/.claude/synthesizer.env`.

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

**Synced shell config (2026-05-31):** `workflow/shell/gc-shell.zsh` holds machine-agnostic zsh bits (currently an iTerm2 precmd hook that puts the cwd in the tab/window title, updating on every `cd`). `install.sh` copies it to `~/.claude/shell/` and idempotently appends a `source` line to `~/.zshrc` — chosen over syncing the whole `.zshrc` so machine-specific config (nvm, paths) isn't clobbered. **Mini follow-up:** `git pull` + run `install.sh` to pick it up (the mini already has a near-identical inline precmd; the sourced one will override it harmlessly).

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

<!-- SHARED-CONVENTIONS:BEGIN v=d5e16e653242 — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->
## Shared conventions

<!-- These are Nico's cross-repo output rules. They're materialized into each repo's
CLAUDE.md so every agent (local, cloud, third-party) sees them as plain text. Source
of truth: prompt-lab/workflow/claude-md-shared.md — edit there and re-sync, never here. -->

- **Clickable URLs.** When pointing at any web destination (dashboard, repo, PR, deploy, settings, docs, localhost), print the full bare URL — `https://example.com` or `http://localhost:8080` — on its own, never just the page's name and never a markdown `[label](url)` link. Nico's terminal auto-linkifies raw `https://` text, so a bare URL is one-click and stays copyable.

- **Number your questions.** Any time you ask Nico more than one question, present them as a numbered list (1., 2., 3.) so he can answer by number with no ambiguity. A single standalone question needs no number.

- **Self-contained smoke-test instructions.** When you ask Nico to manually test or verify an app or website, assume zero carried-over context — he should never scroll back or recall a URL/path/credential from earlier. Always include: the exact URL (full `https://…` or `http://localhost:…`, restated even if mentioned above), the precise steps in order, and what a pass vs. fail looks like. Repetition here is a feature, not clutter.

- **No marker before a copy-paste command block.** Nico's terminal renders markdown bullets (`-`, `*`, `•`) as `●`, which breaks paste into zsh. The line directly above a fenced command block must be a plain-text label ending in a colon — never a bullet, dash, asterisk, or number. For loud copy targets, lead the label with `📋` + bold `COPY THE BELOW`, then a colon, then the block.
<!-- SHARED-CONVENTIONS:END -->
