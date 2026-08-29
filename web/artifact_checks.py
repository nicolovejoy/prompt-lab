"""Artifact-freshness declarations, shared by two readers on purpose.

The Vercel health email (web/api/health_report.py) runs these against Turso
and grades the age. nightly_pipeline.py runs the same SQL against the LOCAL
store at the end of a run and stamps the results into the run record as
`claims` — "here is what existed locally when I finished".

Both readers must name the same artifacts or the cross-check is meaningless:
comparing a claim against a differently-scoped remote query would answer a
question nobody asked. That is why this list has one home.

What the cross-check buys, and it is the point of the whole mechanism: today
the health email sees only Turso, so when local holds a row the cloud lacks
it reports "stale" and cannot say whether the job failed to PRODUCE or failed
to PUBLISH — different bugs, different fixes. With claims it can say which.

`uptime_daily` is deliberately absent: it is cloud-direct, written by the
Vercel cron itself, and has no local counterpart for the pipeline to claim.
health_report.py appends it to its own HEARTBEATS list.

Thresholds are DAYS, not hours — every artifact here is date-granular.
"""

from __future__ import annotations

# (label, sql, max_age_days)
ARTIFACT_CHECKS = [
    ("review email",
     "SELECT max(date) AS d FROM review_snapshots "
     "WHERE review_type IN ('daily_email', 'weekly_email')", 2),
    ("synthesizer", "SELECT max(date) AS d FROM daily_summaries", 2),
    ("weekly rollups", "SELECT max(week_start) AS d FROM weekly_rollups", 10),
    # Anthropic's Admin API reports a day behind, so yesterday is the normal
    # newest row — 2 would alarm on a healthy pipeline.
    ("cost pull + sync", "SELECT max(date) AS d FROM api_costs", 3),
    ("bi-monthly report",
     "SELECT max(date) AS d FROM review_snapshots "
     "WHERE review_type = 'monthly_report'", 20),
]
