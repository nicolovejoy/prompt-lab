# Health endpoint convention

Every app in the ecosystem exposes:

- `GET /api/health` → `200 {"ok": true}` — no auth, no secrets, no side effects, cheap enough to hit every 5 minutes.
- Optionally a **deep variant** behind a query flag (e.g. `?db=1`) that checks real dependencies (DB reachable, crons fresh) and returns **non-2xx when any fails**, with per-dependency detail in the JSON body.

Reference implementation: Garm — `https://garm.prompt-labs.org/api/health?db=1` returns `{ok, db, howl: {ageSeconds, stale}}` and 503s on a dead DB or a denial-digest cron stale >26h.

prompt-lab's own: `https://prompt-labs.org/api/health?db=1` (`web/api/health.py`) returns `{ok, db}` and 503s when Turso is unreachable. The endpoint must stay unauthenticated — the first health email (2026-07-30) reported prompt-labs.org DOWN because `TARGETS` polled auth-gated `/api/info` and got a 401.

## Consumers

- **UptimeRobot** (immediate alerting, independent infra) — one monitor per app, pointed at the deep URL where one exists, homepage otherwise. A homepage-200 check can pass while the backend is dead; upgrade the monitor URL when the app adopts this convention.
- **Daily summary email** — `web/api/health_report.py` (issue #34), triggered by Vercel cron, polls the `TARGETS` list in that module. Add new targets there as apps expose endpoints.

## Why alerting is external

Garm consumers fail closed (ratified 2026-07-29), so a Garm outage is an ecosystem-wide lockout — and prompt-lab shares the Vercel+Turso+Resend stack with much of the ecosystem. A shared-platform outage takes out watcher and watched together, and email alerts die with Resend. The pager must live on infra we don't share (UptimeRobot now, possibly a Pi watchdog later); the summary email is the trend layer only. (garm handoff channel, 2026-07-29.)
