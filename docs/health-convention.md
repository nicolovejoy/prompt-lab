# Health endpoint convention

Every app in the ecosystem exposes:

- `GET /api/health` → `200 {"ok": true}` — no auth, no secrets, no side effects, cheap enough to hit every 5 minutes.
- Optionally a **deep variant** behind a query flag (e.g. `?db=1`) that checks real dependencies (DB reachable, crons fresh) and returns **non-2xx when any fails**, with per-dependency detail in the JSON body.

Reference implementation: Garm — `https://garm.prompt-labs.org/api/health?db=1` returns `{ok, db, howl: {ageSeconds, stale}}` and 503s on a dead DB or a denial-digest cron stale >26h.

prompt-lab's own: `https://prompt-labs.org/api/health?db=1` (`web/api/health.py`) returns `{ok, db}` and 503s when Turso is unreachable. The endpoint must stay unauthenticated — the first health email (2026-07-30) reported prompt-labs.org DOWN because `TARGETS` polled auth-gated `/api/info` and got a 401.

## Heartbeats — for recurring jobs, not URLs (issue #45)

A health endpoint answers "is this reachable." It cannot answer "did the nightly job run," and that is the failure class that has actually bitten us — six times in one week, every one a job rather than a URL.

**Alarm on the artifact's freshness, not the job's exit status.** The job's own reporting is precisely what fails: `send-review.py` exited non-zero for 60 consecutive nights and nothing surfaced it, because nobody reads launchd exit codes. So every recurring job declares *I produce artifact X, and X should never be older than N hours*, and something **outside the job** checks it. Outside is load-bearing — a job that dies before reaching any of its own error handling must still trip the check.

### Mechanics: measure the artifact, don't trust a ping

Every job here already writes a dated row into a table that syncs to Turso, so the freshness check is a `max(date)` query — `HEARTBEATS` in `web/api/health_report.py`, evaluated on each daily run and rendered on `#/health`.

This is deliberately **not** a synthetic ping. A ping is a side-channel claim that the job ran; `max(date)` is the output itself. A ping can succeed while the artifact is missing — which is exactly how the review email looked healthy for 60 nights. Prefer the real artifact wherever one exists.

"Outside the job" is still satisfied: the jobs run under launchd on the mini and write through the Turso sync; the check runs on Vercel and reads. If the mini dies entirely, the tables stop advancing and the next email says so.

Thresholds are **days, not hours** — every artifact is date-granular, so hours would imply precision that isn't there. A threshold must exceed the job's own cadence or it alarms on a healthy run: `2` for a nightly means one missed night is quiet and two is a breach, which is #45's stated bar.

| declared | artifact | stale at |
| --- | --- | --- |
| review email | `review_snapshots` (daily/weekly rows) | 2d |
| synthesizer | `daily_summaries` | 2d |
| weekly rollups | `weekly_rollups` | 10d |
| cost pull + sync | `api_costs` — Anthropic reports a day late, so yesterday is healthy | 3d |
| bi-monthly report | `review_snapshots` (monthly rows) | 20d |

**A failed check reports "could not check", never "fresh."** The pause lookup in the same module fails open on purpose (a Turso outage shouldn't block an email); freshness must fail loud, because absence-reading-as-fine is the bug being fixed. Going quiet when it can't see would manufacture confidence.

Garm's Howl digest is deliberately absent: it already reports `howl: {ageSeconds, stale}` in its deep health body, so its freshness rides the existing poll. Prefer that shape where an app already has a health endpoint.

Scheduled CI is also absent. Nothing here runs on a schedule (`test.yml` is push-only), and "last successful deploy" has no honest max age — not deploying for a week is a normal Tuesday.

### `heartbeat.py` — the fallback for jobs with no artifact

For a job that produces nothing queryable, `heartbeat.ping(job)` posts to a URL from `HEARTBEAT_URL_<JOB>`; it never raises and no-ops when unset, because a monitoring write must never be able to fail the work it monitors. It is wired into all four jobs and **currently dormant** — the artifact checks above cover them better, and UptimeRobot's `HEARTBEAT` monitor type needs a paid plan (verified against the API 2026-07-31; the free-tier comparison table claims otherwise and is wrong).

Its two placement rules still bind if it's ever switched on, and they are the same rules the artifact thresholds encode:

- **Ping after the artifact lands, not at the end of `main()`.** `send-review.py` pings only when Resend accepted the message.
- **Ping after the last leg, not the first.** `run-cost-pull.sh` pings after the Turso sync, never after the local pull — the dashboard reads Turso, so a ping on the pull would report fresh through exactly the drift that script exists to prevent.

Scheduled CI is also absent. Nothing here runs on a schedule (`test.yml` is push-only), and "last successful deploy" has no honest max age — not deploying for a week is a normal Tuesday, not a breach.

## Consumers

- **UptimeRobot** (immediate alerting, independent infra) — one monitor per app, pointed at the deep URL where one exists, homepage otherwise. A homepage-200 check can pass while the backend is dead; upgrade the monitor URL when the app adopts this convention.
- **Daily summary email** — `web/api/health_report.py` (issue #34), triggered by Vercel cron, polls the `TARGETS` list in that module. Add new targets there as apps expose endpoints.

## Why alerting is external

Garm consumers fail closed (ratified 2026-07-29), so a Garm outage is an ecosystem-wide lockout — and prompt-lab shares the Vercel+Turso+Resend stack with much of the ecosystem. A shared-platform outage takes out watcher and watched together, and email alerts die with Resend. The pager must live on infra we don't share (UptimeRobot now, possibly a Pi watchdog later); the summary email is the trend layer only. (garm handoff channel, 2026-07-29.)
