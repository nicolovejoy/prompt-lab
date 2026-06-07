# Cost tracking (issue #2)

Per-project Anthropic API spend and Claude Code activity, pulled nightly from
the Admin API, synced to Turso, rendered on each project's detail page.

## Architecture

```
                 ┌─────────────────────────────┐
                 │ Anthropic Admin API         │
                 │ (ANTHROPIC_ADMIN_KEY)       │
                 └──────────────┬──────────────┘
                                │ 3 endpoints
       ┌────────────────────────┼────────────────────────────┐
       │                        │                            │
  /usage_report/messages   /cost_report (by         /usage_report/claude_code
  (tokens × model)         workspace_id,             (per-user-per-day, one
                           description, daily)       request per date)
       │                        │                            │
       ▼                        ▼                            ▼
  api_usage                api_costs                  claude_code_usage
  (per-model               (per-description           (per-actor activity
   tokens + computed        list-price USD,            + estimated costs;
   USD via PRICING)         parsed dimensions)         currently empty —
                                                       see "Open" below)
       │                        │                            │
       └────────────────────────┴────────────────────────────┘
                                │ sync_to_turso.py
                                ▼
                          Turso (cloud)
                                │
                                ▼
                  GET /api/cost_timeline?project=…
                                │
                                ▼
                      CostChart (30d bar chart)
                      CostDetailPage (drill-down,
                          #/project/<name>/cost)
```

## Operational checklist

A fresh install or new machine needs all four steps. Once seeded, the
LaunchAgent (`workflow/com.promptlab.api-costs.plist`, daily at 02:30) handles
incremental pulls.

1. **Mint an admin key.** Console → Settings → Admin Keys; format `sk-ant-admin-…`.
   Store in 1Password at `op://dev-secrets/admin-cost-tracking-2026-05/credential`
   and surface it as `ANTHROPIC_ADMIN_KEY` in the local env (`.env.local`).

2. **Seed `project_workspaces`.** Edit the mappings in
   `scripts/seed_project_workspaces.py` and run it. The table maps each
   Anthropic `workspace_id` to a canonical project name many-to-one; unmapped
   data lands in `__unmapped__` (the pull script prints any new unmapped IDs
   at the end of each run, so you'll notice).

3. **First pull.** `python pull_api_costs.py` with no args uses the auto-window
   (since `min(MAX(pulled_at))` across the three cost tables, minus a 1h buffer;
   7-day fallback when tables are empty). For a manual backfill, pass
   `--start YYYY-MM-DD --end YYYY-MM-DD`.

4. **Sync to Turso.** `python sync_to_turso.py` (or `--dry-run` to preview).
   Batched upserts, idempotent on `INSERT OR REPLACE`. The dashboard then
   picks up the new data on its next request — no separate redeploy needed.

## Critical gotchas

- **Admin API amounts are in cents, not dollars.** Both `cost_report` and
  `claude_code` endpoints return `amount` in "lowest units" of the currency.
  `pull_api_costs.py` divides by 100 at parse time so `cost_reported_usd`
  and `estimated_cost_usd` are genuinely USD. Background:
  [memory/project_admin_api_costs.md][1]. Tested in
  `scripts/test_cost_pipeline.py`.

- **Turso HTTP float encoding is asymmetric.** Floats go as raw JSON numbers,
  integers go as strings. `_turso_value()` in `store/turso_store.py` handles
  this; don't change without re-reading [memory/project_turso_float_encoding.md][2].

- **`amount`-aggregated `cost_report` rows already include Claude Code
  subscription-equivalent tokens** at list price. If you're trying to
  reconcile against the Console invoice, subtract `claude_code_usage` rows
  where `customer_type='subscription'`.

- **PRICING is manual.** `claude_api.py:PRICING` lists Haiku 4.5, Sonnet 4.6,
  Opus 4.6, Opus 4.7. New families need a manual entry; the pull script
  warns once per process when it encounters an unknown model so the warning
  surfaces in `pull_api_costs.log`. A `model` close to a known family is
  matched via prefix fallback (`claude-sonnet-4-X` matches `claude-sonnet-4-6`'s
  pricing) — fine for minor version bumps, not for new generations.

- **`pulled_at` is insertion time, not data date.** `MIN(MAX(pulled_at))` is
  used for the auto-window; if a previous run partially failed, the table
  that didn't get written has an older `pulled_at` and the next run
  re-fetches the lagging window.

## Tables (canonical schema in `store/sqlite_store.py`)

- `api_usage` — UNIQUE(date, workspace_id, model). Token counts + computed USD.
- `api_costs` — UNIQUE(date, workspace_id, description). Reported USD with
  parsed `model`, `cost_type`, `token_type`, `service_tier`, `context_window`,
  `inference_geo`.
- `claude_code_usage` — UNIQUE(date, actor_kind, actor_id, model). Per-actor
  metrics repeated across model rows for the same actor on the same day —
  duplication is intentional; aggregation queries must SUM.
- `project_workspaces` — PK workspace_id. Many-to-one mapping to project.

## Dashboard endpoint

`GET /api/cost_timeline?project=<name>&since=<date>&until=<date>&include=claude_code&detail=1`

- Auth-gated (`is_authenticated` cookie/header check). Cost data is never
  exposed via `/api/public_history`.
- Default response: `{costs: [...], usage: [...]}` grouped by (date, model).
- `?include=claude_code` adds `claude_code: [...]` grouped by
  (date, customer_type, model).
- `?detail=1` adds `detail: [...]` ungrouped by token_type, service_tier,
  context_window, etc., for the CostDetailPage drill-down at
  `#/project/<name>/cost`.

## Per-project Anthropic workspaces (status)

All active projects now have their own Anthropic workspace + API key, mostly
so each project's cost shows up under its own `workspace_id` in the Admin API
output. Shared keys collapse traffic into `__default__` and lose attribution.

- [x] notemaxxing — workspace + key live, seeded 2026-05-24
- [x] prntd — workspace created, seeded 2026-05-24 (key wiring TBD)
- [x] musicforge — workspace created, seeded 2026-05-24 (no SDK in code yet)
- [x] prompt-lab — seeded 2026-05-17
- [x] ibuild4you — seeded 2026-05-17

All workspace → project mappings live in `scripts/seed_project_workspaces.py`. Re-run after adding a new mapping; idempotent.

## Open

- **Claude Code Analytics returns 0 actors** for the "Cooking with Nico" org.
  Claude Code subscription auth may still be tied to the individual account
  rather than the org. If/when it flows through, `claude_code_usage`
  populates automatically — no code change needed.

- **PRICING refresh cadence.** No automation; refresh manually when a new
  Claude family ships. The unknown-model WARN in `pull_api_costs.log` is the
  signal.

- **Drill-down filters.** `CostDetailPage` has model + token-type filters and
  a window selector. Future: per-day expandable rows showing which
  descriptions made up that day's cost.

[1]: ../../../.claude/projects/-Users-nico-src-prompt-lab/memory/project_admin_api_costs.md
[2]: ../../../.claude/projects/-Users-nico-src-prompt-lab/memory/project_turso_float_encoding.md
