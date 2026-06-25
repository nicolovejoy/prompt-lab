#!/bin/sh
# Nightly cost job: pull Anthropic Admin cost/usage into the local store, then
# push it to Turso so the cloud dashboard reflects it the same night.
#
# Pull and sync MUST be coupled. The pull writes only to local SQLite; the
# dashboard reads Turso. Running the pull alone (as the LaunchAgent did before
# 2026-06-25) silently drifts the dashboard — local was a month ahead of Turso.
#
# Args (passed by the rendered plist; both have sensible fallbacks for manual
# runs): $1 = python interpreter, $2 = repo dir.
set -e
PY="${1:-python3}"
REPO="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO"

"$PY" pull_api_costs.py
# 7-day window: covers the pull's incremental auto-window plus slack for any
# missed nights, without re-pushing the whole history every run.
"$PY" sync_to_turso.py --days 7
