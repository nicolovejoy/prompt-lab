# Review instructions

## What failure looks like here

A job keeps running while its output stops, and the absence is recorded as
nothing instead of failure. In a diff, look for an error path that logs and
carries on, returns 0, or writes "0 rows (skip)" when rows should exist; a
check that turns an empty result or an exception into "ok"; and a fallback
that quietly covers a dead primary path. Read CLAUDE.md "The failure shape this repo keeps hitting" first.

## What Important means here

Reserve Important for findings that would break behaviour, leak private data
(raw prompts, commit messages, hostnames, local paths, emails) or hide a
failure. Style, naming and refactoring suggestions are Nit at most.

## Always check

Read the diff against CLAUDE.md "Invariants" as well as these questions.

- Does a change to `sync_to_turso.py` or `store/turso_store.py` give Turso a `prompts`, `sessions` or `commits` table, raw text from one, or a leg for a cloud-direct table?
- Does the `weekly_rollups` leg in `sync_to_turso.py`, or any new leg whose rows are written after the period they describe closes, select by that period (`week_start`) rather than by `created_at`? A period window misses those rows (CLAUDE.md Traps).
- Does the diff add a writer of `public_session_summaries` or `public_weekly_rollups`, or feed an existing writer text that did not come from a reviewed, committed draft? The existing writers are `scripts/publish_public_draft.py`, `scripts/unpublish_public.py` (deletes), the `scripts/backfill_public_*.py` one-shots, and the public legs of `sync_to_turso.py`, which copy local rows to Turso.
- Does an unauthenticated path (`web/api/public_history.py`, `web/api/beacon.py`, `web/beacon_helper.py`) now return or store text that was not scrubbed, such as an ID or email inside a page path?
- Does a new or changed route under `web/api/` call `resolve_access`, return 401 on `None`, and filter project rows with `allowed()` or `filter_rows()` from `web/access_helper.py`? An admin-only route instead returns 403 when `access.projects is not None`. Exempt by design: `public_history.py`, `beacon.py`, `health.py`, `login.py` and `callback.py` (unauthenticated), `private_history.py` (service key) and `ask.py` (`get_role`).
- In `web/api/health_report.py` or `web/artifact_checks.py`, can a failed query, an empty table, a missing key or an exception grade as fresh or ok? It must read "could not check" or stale. A new entry in `TARGETS` or `scripts/uptimerobot.py` must be unauthenticated and not a path the SPA catch-all answers with 200.
- Does a heartbeat grade an artifact that is written even when the job fails? A snapshot row written before the send, an exit status or a ping is not proof of delivery.
- Is a calendar day formed in UTC: `toISOString().slice(0,10)` in `web/index.html`, a bare `date(col)` on a UTC column, or `'weekday 1'` in SQL? (CLAUDE.md Shared conventions and Traps.)
- Does an upsert, replace or delete on `daily_summaries` or `weekly_rollups` skip the `*_superseded` archive in `store/`?
- On the nightly path (`nightly_pipeline.py`, `synthesizer.py`, `send-review.py`, `generate-report.py`), does a Claude call bypass `call_claude` in `claude_api.py` or use `messages.create`, or does a deadline use `time.time()`? (CLAUDE.md Traps.)
- In `workflow/run-nightly.sh` or a launchd plist under `workflow/`, is there a `source … &&` chain, or a path that will be deleted? (CLAUDE.md Traps.)
- Is a value read from Turso (`turso_query`, `store/turso_store.py`) summed, compared or charted without `int(x or 0)`? (CLAUDE.md Traps.)

## Sensitive paths

A finding in these is Important by default. When the diff touches any of them,
the summary adds the line `Needs a human read.`, even with no findings.

- `sync_to_turso.py`, `store/turso_store.py`: what reaches the cloud.
- `scripts/publish_public_draft.py`, `scripts/unpublish_public.py`, `scripts/draft_public_refresh.py`, `docs/public-allowlist.txt`, `web/api/public_history.py`, `web/api/beacon.py`, `web/beacon_helper.py`: the public surface.
- `web/access_helper.py`, `web/auth_helper.py`, `web/garm_helper.py`, `web/api/login.py`, `web/api/callback.py`: who can read.
- `web/api/health_report.py`, `web/artifact_checks.py`: the daily health email.
- `nightly_pipeline.py`, `workflow/run-nightly.sh`, `workflow/com.promptlab.nightly.plist`: the nightly run.
- `workflow/hooks/` and `workflow/bin/_gc_session_identity.py`: `log-prompt.sh`, `session-start.sh` and `session-stop.sh` run in place from the main checkout, and `log-prompt.sh` and `session-stop.sh` call that script from there, so a merge is live in every session.
- `vercel.json`, `.vercelignore`: they stop a root deploy from publishing the whole checkout.

## Do not report

- What `.github/workflows/test.yml` already enforces: ruff lint (pinned), the import smoke check, and the test scripts listed in `test.yml`.
- Anything under `archive/`, `docs/archive/`, `docs/superpowers/`, `web/icons/`, or `scripts/phone/package-lock.json`.
- Style, naming, formatting and refactoring suggestions.

## Cap the nits

Report at most three Nits per review.

## Evidence

Every finding cites `file:line`. A claim about behaviour is read from the code,
never inferred from a name. Tag a bug the diff did not introduce as
Pre-existing. Flag a class of bug once and list every instance in it, rather
than one finding per line.

## Summary format

The first line is a count: `N Important, M Nit, K Pre-existing`. With nothing
to report, the review says `Nothing to fix.` and stops. A later round reads
only the new diff and never repeats an earlier finding.
