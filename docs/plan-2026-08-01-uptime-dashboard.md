# Build plan 2026-08-01 — uptime archive + dashboard, `/api/health` rollout

Agreed 2026-07-31 (session that shipped #45's artifact-freshness layer). This doc is the spec for the next build session — read it plus `docs/health-convention.md` and issue #45 before coding. TDD with sub-agents (red-first into `scripts/test_web_api.py`), one PR per phase, Nico merges.

**The frame, settled and not up for re-litigation:** UptimeRobot is the *sensor* (5-min polling, independent infra, free tier, 3-month retention) and the *pager*. prompt-lab is the *aggregation and reporting* layer — it samples nothing itself and pages for nothing. This is the split ratified in garm's 2026-07-29 handoff and already encoded in `docs/health-convention.md`. Phase 1 exists because UptimeRobot's retention is 3 months and ours is forever.

## API facts, verified live 2026-07-31 — do not re-derive

The docs are thin and partly wrong. Everything below was probed against the real API with a Main API key:

- **v3** (`https://api.uptimerobot.com/v3`, `Authorization: Bearer <key>`) is right for **provisioning**. `scripts/uptimerobot.py` already does this. Valid `type` values: `HTTP, KEYWORD, PING, PORT, HEARTBEAT, DNS, API, UDP, VISUAL_COMPARISON`.
- **v3 has no history endpoints.** `/monitors/{id}/logs`, `/response-times`, `/uptimes`, `/daily-ratios` all 404. `lastDayUptimes` on the monitor object is `{"bucketSize": 0, "histogram": []}` — empty, not useful. `/incidents` exists and returns `200 {"data": []}`.
- **v2 legacy is the only source of history** and works fine on the free plan. `POST https://api.uptimerobot.com/v2/getMonitors` with `{"api_key", "format": "json", "custom_uptime_ratios": "1-7-30", "logs": 1, "response_times": 1}` returns per monitor:
  - `custom_uptime_ratio` — a **string** `"100.000-100.000-100.000"` (1d-7d-30d). Split on `-` and `float()` each. This is the same class of trap as Turso returning aggregates as strings; pin it in a test.
  - `response_times` — `[{"datetime": <unix>, "value": <ms>}, …]`
  - `logs` — incident log, empty while nothing has gone down
  - `all_time_uptime_ratio` is `None` on this plan; don't rely on it.
- Free tier: 50 monitors (9 used), 5-min interval, **10 API requests/minute**, 3-month retention. A daily pull is one request — nowhere near the limit.
- **`HEARTBEAT` monitors require a paid plan** (403 `009-005`, at every interval and grace value). The marketing comparison table says otherwise and is wrong. This is why #45 landed as artifact-freshness instead; don't retry it without a plan upgrade.

## Phase 1 — uptime archive (backend, prompt-lab)

New Turso table `uptime_daily`, **cloud-direct: no local SQLite copy, no leg in `sync_to_turso.py`** — same class as `page_views`, `health_email_state`, `project_metadata`. That absence is what makes drift structurally impossible; do not teach the sync about it.

```
uptime_daily(date TEXT, monitor TEXT, uptime_1d REAL, uptime_7d REAL,
             uptime_30d REAL, avg_response_ms INTEGER, status TEXT,
             PRIMARY KEY (date, monitor))
```

Idempotent DDL in `scripts/create_uptime_daily.py`, following `scripts/create_page_views.py`.

**Where the write happens:** fold the pull into `web/api/health_report.py`'s existing cron path — Vercel Hobby crons are daily and we already have one at `0 15 * * *`. Two hard requirements:

1. **Write on the send path only, never on `?dry=1`.** `dry` is open to any authenticated role (that's what `#/health` reads); letting a reader trigger a write would be a privilege leak. The auth split already exists in `_denial()` — respect it.
2. **A failed pull must never block the email.** Wrap it the way `record_login` is wrapped in `callback.py`: swallow, log, continue. The email is the more important artifact.

New read endpoint `web/api/uptime_overview.py`, auth-gated, mirroring `cost_overview.py`'s shape. **Contract, fixed here so Phase 2 can build in parallel:**

```json
{
  "days": 30,
  "monitors": [
    {"name": "garm.prompt-labs.org/api/health?db=1",
     "uptime_30d": 100.0, "uptime_7d": 100.0, "uptime_1d": 100.0,
     "avg_response_ms": 281, "status": "UP",
     "series": [{"date": "2026-07-31", "uptime": 100.0, "ms": 281}]}
  ],
  "generated_at": "2026-07-31T15:00:00Z"
}
```

Empty `series` is normal and must render — the archive starts at zero rows and fills one day at a time. **Do not backfill**; UptimeRobot's history isn't retrievable per-day through v2, only as rolling ratios, so any backfill would be invented data.

Pass: `scripts/create_uptime_daily.py` is idempotent; a cron-authenticated send writes exactly one row per monitor per day and a second run the same day updates rather than duplicates; `?dry=1` writes nothing; a simulated UptimeRobot outage still sends the email; `/api/uptime_overview` 401s anonymously and returns the contract above for a reader.

## Phase 2 — uptime on `#/health` (frontend, prompt-lab)

Build against the Phase 1 contract above; the two phases touch different files (`web/api/*` vs `web/index.html`) and are parallel-safe.

Add below the existing Heartbeats section:
- Per-monitor uptime %, 1d/7d/30d, with a 30/90/365d window switch matching `#/costs` and `#/activity` grammar.
- A sparkline per monitor off `series`.
- Response-time trend.
- Mobile rules from #21/#22 still bind: horizontal scroll opening at the recent end, hover gated to `hover: hover` pointers with tap-to-select on touch, two-column legends collapsing under 600px.

**`#/health` stays deliberately un-cached** for the live-poll section (a remembered "up" is a stale claim), but the archive section is historical and may use the in-session memo. Don't apply SWR to the live targets.

Pass: with an empty archive the page renders an honest "collecting since <date>" state rather than a broken chart; with rows it draws; no console errors; readable in both themes.

## Phase 3 — `/api/health` rollout (5 repos, ideal fan-out)

One small PR per repo, one sub-agent each, all independent. Implement `docs/health-convention.md`: `GET /api/health` → `200 {"ok": true}`, unauthenticated, no side effects, cheap enough for a 5-minute poll. Add a deep variant only where there's a real dependency worth asserting.

- `byside` — by-side.net (Next.js App Router)
- `bakerylouise-v1` — bakerylouise.com (Next.js; Sanity-backed, so a deep variant could assert Sanity reachability)
- `selected-projects` — pianohouseproject.org (Next.js)
- `musicforge` — musicforge.app (Vite frontend; may need a serverless route rather than a client route)
- `prntd` — prntd.org (Next.js)

**Reference implementation is ibuild4you** (`app/api/health/route.ts`), which returns `{"ok": true, "checks": [{"name", "ok", "ms"}]}` — richer than the convention requires and a good model for the deep variant.

After each merges, repoint its UptimeRobot monitor by editing `HTTP_MONITORS` in `scripts/uptimerobot.py` and running `sync --apply`. Do **not** repoint before the endpoint is live — a 404 target flips the monitor to a permanent false DOWN.

Pass: each URL returns `200 {"ok":true}` unauthenticated in production; monitor repointed and green.

## Phase 4 — un-gate recountly's health endpoint (small, recountly repo)

`https://recountly.org/api/health` exists but returns `401`. Move it outside the auth middleware, then repoint its monitor. Until then it stays on the homepage check — pointing at it now would false-DOWN forever, which is exactly bug #40.

Pass: `curl https://recountly.org/api/health` → `200 {"ok":true}` with no cookie; monitor repointed and green.

## Phase 5 — grow `TARGETS` (small, prompt-lab)

`TARGETS` in `web/api/health_report.py` still polls only garm and prompt-labs.org. Once Phases 3–4 land, add each new `/api/health`. Keep the poll list and the monitor list in agreement — `scripts/uptimerobot.py` and `TARGETS` are two declarations of overlapping intent and will drift; a test asserting every deep-health `TARGETS` URL also appears in `HTTP_MONITORS` is cheap insurance.

## Deferred — do not pick up

#14 design tokens (own session), #27 Garm rollout, `/api/private_history` Tier 1 (awaiting selected-projects), public rollup backlog — **selected-projects (4 weeks) and ibuild4you (6) are drafted, reviewed, and committed; only `--apply` + `sync_to_turso.py` is owed** and it's human-gated. UptimeRobot paid plan / real `HEARTBEAT` monitors.

## Open decisions for Nico

1. **Response-time storage.** The archive above keeps a daily average only. Keeping the raw 5-minute series would allow real latency percentiles but is ~2,600 rows/monitor/day. Recommend: daily average now, revisit if a latency question actually comes up.
2. **Phase 3 scope.** Five repos is five PRs across five codebases. Worth doing all at once, or start with byside + selected-projects (the two you touch most) and let the rest follow?

## Context a fresh session needs

- **`UPTIMEROBOT_API_KEY` is live** in `.env.local` on mini, from 1Password `op://dev-secrets/UptimeRobot/api-key`. It is **not** in Vercel yet — Phase 1's cron-side pull needs it added to Production before the archive will fill. That's a manual `vercel env add` step; see the stdin traps in CLAUDE.md (never strip the newline, never loop it, verify with `vercel env ls`).
- `op inject -i .env.tpl -o .env.local` **is not a working workflow in this repo** and shouldn't be restored. The template describes the union of local and cloud secrets, so regenerating locally tries to materialize cloud-only values. Append single variables instead. Also: `op inject` substitutes `op://` references **inside `#` comments** — a commented reference is still a live reference, and an unresolvable one aborts the whole file.
- The `bi-monthly report` job was dead from 2026-04-01 to 2026-07-31 and is now fixed and verified (ran through launchd, 197s, `reports/2026-07-31-review-30d.md`). Its next natural run is the 1st — **check it fired** rather than assuming.
- 117 tests in `scripts/test_web_api.py`; `invoke()`/`invoke_post()` harness with lowercase header dicts. `_health_mod(up=, hb=)` stubs the health endpoint — `hb` takes `fresh|stale|never|error` and dispatches on SQL, because the pause lookup and the freshness lookups share `turso_query` and must not be conflated (pause fails open, freshness fails loud).
- CI ruff is pinned to `0.15.22` — don't unpin.
- Nine UptimeRobot monitors, all green. prntd is `.org`, not `.com`.
