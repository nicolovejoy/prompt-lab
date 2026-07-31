# Health endpoint convention

Every app in the ecosystem exposes:

- `GET /api/health` → `200 {"ok": true}` — no auth, no secrets, no side effects, cheap enough to hit every 5 minutes.
- Optionally a **deep variant** behind a query flag (e.g. `?db=1`) that checks real dependencies (DB reachable, crons fresh) and returns **non-2xx when any fails**, with per-dependency detail in the JSON body.

Reference implementation: Garm — `https://garm.prompt-labs.org/api/health?db=1` returns `{ok, db, howl: {ageSeconds, stale}}` and 503s on a dead DB or a denial-digest cron stale >26h.

prompt-lab's own: `https://prompt-labs.org/api/health?db=1` (`web/api/health.py`) returns `{ok, db}` and 503s when Turso is unreachable. The endpoint must stay unauthenticated — the first health email (2026-07-30) reported prompt-labs.org DOWN because `TARGETS` polled auth-gated `/api/info` and got a 401.

## Heartbeats — for recurring jobs, not URLs (issue #45)

A health endpoint answers "is this reachable." It cannot answer "did the nightly job run," and that is the failure class that has actually bitten us — six times in one week, every one a job rather than a URL.

**Alarm on the artifact's freshness, not the job's exit status.** The job's own reporting is precisely what fails: `send-review.py` exited non-zero for 60 consecutive nights and nothing surfaced it, because nobody reads launchd exit codes. So every recurring job declares *I produce artifact X, and X should never be older than N hours*, and something **outside the job** checks it. Outside is load-bearing — a job that dies before reaching any of its own error handling must still trip the check.

Mechanics: the job pings an unguessable URL on success; the monitor holds last-ping + max age and alarms on breach. `heartbeat.py` (`ping(job)`) is the local helper, reading a full URL from `HEARTBEAT_URL_<JOB>`. It never raises and no-ops when unset — a monitoring write must never be able to fail the work it monitors.

Two placement rules, both learned the hard way:

- **Ping after the artifact lands, not at the end of `main()`.** `send-review.py` pings only when Resend accepted the message. A ping on "the process finished" would have reported fresh through the entire 60-night outage.
- **Ping after the last leg, not the first.** `run-cost-pull.sh` pings after the Turso sync, never after the local pull — the dashboard reads Turso, so a ping on the pull would report fresh through exactly the drift that script exists to prevent.

Current jobs and declared max ages:

- `review` — `send-review.py`, nightly 2:30am (mini) — 26h
- `synthesizer` — `synthesizer.py --all`, nightly 2:00am (mini) — 26h
- `cost-pull` — `workflow/run-cost-pull.sh`, nightly 2:30am (mini) — 26h
- `report` — `generate-report.py`, 1st & 15th at 3:00am (mini) — 20d

Garm's Howl digest is deliberately absent: it already reports `howl: {ageSeconds, stale}` in its deep health body, so its freshness rides the existing poll. Prefer that shape where an app already has a health endpoint — a heartbeat monitor is for jobs with nowhere to report.

Scheduled CI is also absent. Nothing here runs on a schedule (`test.yml` is push-only), and "last successful deploy" has no honest max age — not deploying for a week is a normal Tuesday, not a breach.

## Consumers

- **UptimeRobot** (immediate alerting, independent infra) — one monitor per app, pointed at the deep URL where one exists, homepage otherwise. A homepage-200 check can pass while the backend is dead; upgrade the monitor URL when the app adopts this convention.
- **Daily summary email** — `web/api/health_report.py` (issue #34), triggered by Vercel cron, polls the `TARGETS` list in that module. Add new targets there as apps expose endpoints.

## Why alerting is external

Garm consumers fail closed (ratified 2026-07-29), so a Garm outage is an ecosystem-wide lockout — and prompt-lab shares the Vercel+Turso+Resend stack with much of the ecosystem. A shared-platform outage takes out watcher and watched together, and email alerts die with Resend. The pager must live on infra we don't share (UptimeRobot now, possibly a Pi watchdog later); the summary email is the trend layer only. (garm handoff channel, 2026-07-29.)
