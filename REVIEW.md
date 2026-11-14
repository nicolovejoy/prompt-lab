# Review instructions

## What failure looks like here

A job keeps running while its output stops, and the absence is recorded as nothing
instead of failure. In a diff, look for an error path that logs and carries on,
returns 0, or writes "0 rows (skip)" when rows should exist; a check that turns an
empty result or an exception into "ok"; and a fallback that quietly covers a dead
primary path. Read CLAUDE.md "The failure shape this repo keeps hitting" first.

## What Important means here

Reserve Important for findings that would break behaviour, leak private data
(raw prompts, commit messages, hostnames, local paths, emails) or hide a
failure. Style, naming and refactoring suggestions are Nit at most.

## Always check

Read the diff against CLAUDE.md "Invariants" as well as these questions.

- Does a change to `sync_to_turso.py` or `store/turso_store.py` give Turso a `prompts`, `sessions` or `commits` table, raw text from one, or a leg for a cloud-direct table?
- Does the `weekly_rollups` leg in `sync_to_turso.py`, or any new leg whose rows are written after the period they describe closes, select by that period (`week_start`) rather than by `created_at`? A period window misses those rows (CLAUDE.md Traps).
- Does the diff add a writer of the `public_*` tables, or feed an existing one (`scripts/publish_public_draft.py`, `scripts/backfill_public_*.py`, the public legs of `sync_to_turso.py`) text that did not come from a reviewed, committed draft? `scripts/unpublish_public.py` only deletes.
- Does an unauthenticated path (`web/api/public_history.py`, `web/api/beacon.py`, `web/beacon_helper.py`) now return or store text that was not scrubbed, such as an ID or email inside a page path?
- Does a new or changed `web/api/` route call `resolve_access`, return 401 on `None`, and filter rows with `allowed()` or `filter_rows()` (`web/access_helper.py`)? Admin-only routes return 403 when `access.projects is not None`. Exempt: `public_history`, `beacon`, `health`, `login`, `callback`, `private_history`, `ask`.
- In `web/api/health_report.py` or `web/artifact_checks.py`, can a failed query, empty table, missing key or exception grade as fresh? It must read "could not check" or stale. A new health target (`TARGETS`, `scripts/uptimerobot.py`) must be unauthenticated and not answered by the SPA catch-all.
- Does a heartbeat grade an artifact that is written even when the job fails? A snapshot row written before the send, an exit status or a ping is not proof of delivery.
- Is a calendar day formed in UTC: `toISOString().slice(0,10)` in `web/index.html`, a bare `date(col)` on a UTC column, or `'weekday 1'` in SQL? (CLAUDE.md Shared conventions and Traps.)
- Does an upsert, replace or delete on `daily_summaries` or `weekly_rollups` skip the `*_superseded` archive in `store/`?
- On the nightly path (`nightly_pipeline.py`, `synthesizer.py`, `send-review.py`, `generate-report.py`) or in `claude_api.py` itself, does a Claude call bypass `call_claude` or use `messages.create`, or does a deadline use `time.time()`? (CLAUDE.md Traps.)
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
- `claude_api.py`: `call_claude` and `load_env`, which every nightly job goes through.
- `workflow/hooks/`, `workflow/bin/_gc_session_identity.py`, `workflow/bin/session-context.sh`, `scripts/prompt_kind.py`: the prompt and session hooks run these in place from the main checkout, so a merge is live in every session.
- `vercel.json`, `.vercelignore`: they stop a root deploy from publishing the whole checkout.

## Do not report

- What `.github/workflows/test.yml` already enforces: ruff lint (pinned), the import smoke check, and the test scripts listed in `test.yml`.
- Anything under `archive/`, `docs/archive/`, `docs/superpowers/`, `web/icons/`, or `scripts/phone/package-lock.json`.
- Style, naming, formatting and refactoring suggestions.

## Cap the nits

Report at most three Nits, and only ones worth a commit. Zero is the normal count; never fill the cap.

## Evidence

Every finding cites `file:line`. A claim about behaviour is read from the code,
never inferred from a name. Tag a bug the diff did not introduce as
Pre-existing. Flag a class of bug once and list every instance in it, rather
than one finding per line.

## Summary format

The first line is a count: `N Important, M Nit, K Pre-existing`. With nothing
to report, the next line is `Nothing to fix.`, then `Needs a human read.` if a
sensitive path was touched, and the review stops. A later round reads only the
new diff and never repeats an earlier finding.
