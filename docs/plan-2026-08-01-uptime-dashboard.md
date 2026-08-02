# Uptime archive + dashboard — build plan (HISTORICAL)

Written 2026-07-31, executed the same evening. **Superseded 2026-08-02** — this is
kept as the record of what was specified and why, not as a live spec. For current
status and remaining work, read `CLAUDE.md`; for the narrative, `docs/history.md`.

## What shipped

- **Phase 1 — uptime archive.** `uptime_daily` on Turso, written by the health cron's
  send path. `scripts/create_uptime_daily.py` (idempotent DDL),
  `web/api/uptime_overview.py` (auth-gated read). PR #46 `842cafd`.
- **Phase 2 — uptime on `#/health`.** Per-monitor ratios, per-day strip, response-time
  trend. PR #47 `96ace9d`.
- **Phase 3, partially.** `byside` and `selected-projects` got `/api/health` and their
  monitors were repointed (`1742464`).

## What remains

`musicforge`, `prntd`, `bakerylouise-v1` still need `/api/health` (Phase 3), and
`TARGETS` still needs growing plus the test asserting it agrees with `HTTP_MONITORS`
(Phase 5). **Phase 4 is cancelled** — recountly became Raconte, a native iOS app, so
there is nothing left to poll; its monitor was dropped from `HTTP_MONITORS`
2026-08-02 and must be deleted by hand in the UptimeRobot UI.

**Correction to this doc's own framing:** Phase 3 was written as "one small PR per
repo, one sub-agent each." That was wrong, and the phrasing is the trap — cross-repo
work goes through `~/src/.handoff`, because the repo boundary is the ownership
boundary. See CLAUDE.md.

## Design decisions worth keeping

**The frame.** UptimeRobot is the *sensor* (5-min polling, independent infra) and the
*pager*. prompt-lab is the *aggregation and reporting* layer — it samples nothing and
pages for nothing. Phase 1 exists only because UptimeRobot's retention is 3 months and
ours is forever.

**Schema** — cloud-direct, no local copy, no leg in `sync_to_turso.py`:

```
uptime_daily(date TEXT, monitor TEXT, uptime_1d REAL, uptime_7d REAL,
             uptime_30d REAL, avg_response_ms INTEGER, status TEXT,
             PRIMARY KEY (date, monitor))
```

**Two hard requirements on the write**, both now test-pinned: it happens on the send
path only, never on `?dry=1` (which is open to any authenticated role, so a reader
must not be able to trigger a write); and a failed pull must never block the email.
The pull also runs *ahead* of the pause check — pausing the email for a week must not
punch a week-long hole in the archive.

**Do not backfill.** UptimeRobot exposes rolling ratios, not per-day history, so any
backfill would be invented data. A day with no row renders grey, never 0%.

**The `#/health` live-target section stays un-cached** — a remembered "up" is a stale
claim. The archive section is historical and may use the in-session memo.

**Response-time storage: daily average only.** Keeping the raw 5-minute series would
allow real latency percentiles at ~2,600 rows/monitor/day. Revisit only if a latency
question actually comes up.

## API facts, verified live 2026-07-31 — do not re-derive

The published docs are thin and partly wrong. Everything below was probed against the
real API with a Main API key.

- **v3** (`https://api.uptimerobot.com/v3`, `Authorization: Bearer <key>`) is right for
  **provisioning** — `scripts/uptimerobot.py` uses it. Valid `type` values:
  `HTTP, KEYWORD, PING, PORT, HEARTBEAT, DNS, API, UDP, VISUAL_COMPARISON`.
- **v3 has no history endpoints.** `/monitors/{id}/logs`, `/response-times`,
  `/uptimes`, `/daily-ratios` all 404. `lastDayUptimes` is `{"bucketSize": 0,
  "histogram": []}` — empty, not useful. `/incidents` returns `200 {"data": []}`.
- **v2 legacy is the only source of history** and works on the free plan.
  `POST https://api.uptimerobot.com/v2/getMonitors` with `{"api_key", "format":
  "json", "custom_uptime_ratios": "1-7-30", "logs": 1, "response_times": 1}` returns
  per monitor:
  - `custom_uptime_ratio` — a **string** `"100.000-100.000-100.000"` (1d-7d-30d).
    Split on `-` and `float()` each. Same trap class as Turso returning aggregates as
    strings; pinned in a test.
  - `response_times` — `[{"datetime": <unix>, "value": <ms>}, …]`
  - `logs` — incident log, empty while nothing has gone down
  - `all_time_uptime_ratio` is `None` on this plan; don't rely on it.
- Free tier: 50 monitors (8 used), 5-min interval, **10 API requests/minute**, 3-month
  retention. A daily pull is one request.
- **`HEARTBEAT` monitors require a paid plan** (403 `009-005`, at every interval and
  grace value). The marketing comparison table says otherwise and is wrong. This is why
  #45 landed as artifact freshness instead; don't retry it without a plan upgrade.

## The `/api/health` convention

Spec is `docs/health-convention.md`: `GET /api/health` → `200 {"ok": true}`,
unauthenticated, no side effects, cheap enough for a 5-minute poll. Add a deep variant
(`?db=1`) only where there's a real dependency worth asserting; it returns non-2xx when
that dependency is down. Reference implementation is ibuild4you's
`app/api/health/route.ts`.

Never repoint a monitor before the endpoint is live: the SPA catch-all serves
`index.html` with a 200 for unknown paths, so a 404 target becomes a permanent false
UP (bug #40).
