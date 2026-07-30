# Build plan 2026-07-30 — health page, KPI drill-downs, login events

Agreed 2026-07-29 (session that shipped #34 slice 1). This doc is the spec for the next build session — read it plus issues #34/#31/#10/#28 before coding. TDD with sub-agents (red-first into `scripts/test_web_api.py`), one PR per phase, Nico merges.

## Phase 1 — `#/health` page (#34 remainder, small)

Reuse `web/api/health_report.py` — no new serverless function:
- Loosen `?dry=1` to ANY authenticated role (readers see status; send path stays cron/admin). Test-pin: reader + `?dry=1` → 200; reader without `dry` → 403 (not 401 — distinguish "may not trigger send").
- Frontend `#/health`: top-nav "Health" link. Per-target cards from `dry` payload (name, up/down, HTTP status, latency ms, note — garm's shows db + howl staleness), a "paused until <date>" banner when `paused_until` is set, manual ↻ re-poll. Live-poll on page load like Todos (endpoint polls targets at request time, ~1-2s — show loading state).
- NOT this phase: UptimeRobot read-API uptime overlay (needs an API key minted + stored; do when wanted).

Pass: reader account sees target status on prod; send path untouched (cron still fires).

## Phase 2 — #31 KPI drill-downs + `#/activity` (the big one)

Per the issue, in order:
1. **Affordance first**: diagnose why the spend tile's existing `to: '#/costs'` reads as not-linked; add a visible cue (arrow glyph / hover lift) to every linked tile.
2. **`#/activity` page** mirroring `#/costs`: stacked-by-project daily chart, 30/90/365d windows, metric switch (sessions | prompts | commits), sortable per-project table (7d/30d per metric). Tiles deep-link with metric preselected (`#/activity/sessions` etc.).
   - Data: daily_summaries counts per project/day (what `activity_by_project` already reads) — covers 365d. New auth-gated, alias-folded `web/api/activity_timeline.py` with `?days=` (mirror `cost_overview.py`'s shape); don't overload `/api/overview` (its payload is SWR-cached for home paint, keep it lean).
3. **Active/dormant tile**: recommend the cheap option — tile toggles an inline expansion under the tile row reusing the dormant chip-list component for both lists (status-aware per #23, click-through rows, dormant muted). Build `#/projects` as a page only if inline feels cramped. ← Nico may override.

Pass: every Pulse tile visibly clickable and lands somewhere that decomposes its number; #/activity charts match #/costs interaction grammar (windows, hover/tap per #21/#22 mobile rules).

## Phase 3 — #10 login-event visibility (small, if room)

Decision needed (see Open decisions): beacon `login` event vs. tiny `login_events` table.
Recommended: **beacon event, no identity** — add `"login"` to `ALLOWED_EVENTS` in `web/api/beacon.py`, fire server-side from `callback.py` on successful login with `path=/login/<role>` (role, never email — measurement policy: no stable identifiers in page_views). Surfaces in `#/visitors` for free. With two users, role ≈ who; revisit a real audit table only if that stops being true.

Pass: a real Google sign-in lands one `login` row in page_views; bot/preview noise excluded (beacon's existing drops apply).

## Phase 4 — #28 session-row merge (local, no deploy, if room)

One-time cutover artifact, now past the ~week Nico wanted to wait. Script modeled on `scripts/close_stale_sessions.py`: dry-run default, `--execute`; finds unbound 2026-07-19 rows whose prompt span abuts a bound row (same project), re-points prompts, drops the shell. Snapshot `~/.claude/prompt-history.db` first. split-recording 645→731 already hand-done — skip it.

Pass: dry-run lists only genuine duplicates; after `--execute`, no orphan shells, prompt counts conserved.

## Deferred (do not pick up)
#14 design tokens (own session), #27 Garm rollout (other repos), `/api/private_history` Tier 1 (awaiting selected-projects reply), public rollup backlog (human-gated drafting), UptimeRobot overlay on #/health.

## Open decisions for Nico
1. Phase 2.3: inline expansion under the tiles (recommended) or a full `#/projects` page?
2. Phase 3: anonymous beacon `login` event with role-only path (recommended) or a `login_events` table with email (a real "who" audit log, different privacy posture)?
3. Phase order OK? (1 → 2 → 3 → 4; 2 is most of the session.)

## Context from 2026-07-29 the fresh session needs
- Health email is LIVE: cron `0 15 * * *`, first send expected 2026-07-30 ~8am Pacific — check it arrived before building Phase 1; if it didn't, debugging that comes first (`vercel logs`, `?dry=1` as admin).
- CI ruff is pinned to 0.15.22 (`.github/workflows/test.yml`) — don't unpin.
- Phase 2 OAuth fully closed out (#33 merged, BEACON_SALT in all envs). Auth model: Google-only prod, ADMIN_EMAILS/READER_EMAILS, reader=full read.
- 83 tests in `scripts/test_web_api.py`; `invoke()`/`invoke_post()` harness with case-sensitive lowercase header dicts.
