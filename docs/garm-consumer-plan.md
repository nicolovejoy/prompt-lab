# prompt-lab as a Garm consumer: design record

Status 2026-11-14: the backend is built and the rollout is not done. `GARM_GATING` is off
in Vercel and `READER_EMAILS` is the live gate. Do not roll out without Nico's go. The
task-by-task plan with code is this file's git history.

Goal: readers of prompt-labs.org see only the projects Garm grants them. Admin keeps the
Garm-free login.

## Design

- Reader sign-in resolves the person's Garm grants once and carries the allowed project set in the signed `gc_session` cookie.
- `access_helper.resolve_access()` gates every project-bearing endpoint. It re-resolves when the cookie's grant stamp is older than 10 minutes (`GRANTS_TTL` = 600s), so a revoke lands within about 10 minutes.
- Admin is `ADMIN_EMAILS` and never consults Garm; `projects=None` means unfiltered. A Garm outage must not lock out the tool that diagnoses it.
- `web/garm_helper.py` is the only file that talks to Garm: urllib, 2s timeout, fail closed.
- `GARM_GATING=off` is the kill switch and restores the `READER_EMAILS` all-projects behaviour. The code default is `on`.
- Gate on grant presence, never on the role string.
- A new helper under `web/` must be listed in `includeFiles` in `web/vercel.json`, or every lambda importing it returns 500.

## Decisions (Nico, 2026-08-22)

1. **Namespaced slugs.** Garm project = `prompt-lab.<canonical>`. Dot, not colon: Garm's slug validation rejects `:`. `fetch_grants` strips the prefix and drops grants outside the namespace; `*` is kept.
2. **Garm-only readers.** A reader is anyone with at least one active `prompt-lab.*` grant or `*`. `READER_EMAILS` is read only when gating is off.
3. **`#/health`, `#/visitors` and uptime are admin-only.** They have no project column to filter on.
4. **The project set comes from Garm's list endpoint,** `GET /gnipahellir/grants?email=`, with an unscoped consumer key that garm ratified as a named exception.
5. **Revocation latency is the 10-minute cookie cache.**

## Built

`web/garm_helper.py`, `web/access_helper.py`, `resolve_access` in the `web/api/` endpoints,
and both helpers in `includeFiles`.

## Not done

1. Confirm garm's list endpoint is live and matches the shape above; adjust `fetch_grants` if not.
2. Mint the consumer key and save it as `op://dev-secrets/garm-consumer-prompt-lab/password`.
3. Set `GARM_KEY`, `GARM_URL` (`https://garm.prompt-labs.org`) and `GARM_GATING` (`on`) in Vercel Production. One `vercel env add` per variable, no loop, no `tr`; verify with `vercel env ls`.
4. Seed reader grants in Garm, then `cd web && vercel --prod`.
5. Smoke test, below.
6. A `garm usage` line in the health email: `GET /api/usage?days=1&consumer=prompt-lab` with `GARM_REPORTING_KEY`, which is not in prompt-lab's Vercel env.

Leave `READER_EMAILS` populated after rollout: it is the kill-switch allowlist.

Open copy question: once filtered, a reader's KPI tiles are totals over their own projects.
A caption saying so may be needed.

## Smoke test

1. Sign in at https://prompt-labs.org as admin. Pass: every project and page, as before.
2. In a private window, sign in as a reader holding one grant. Pass: only that project on home, Activity and Costs; no Health or Visitors in the nav; another project's URL shows a "not in your view" message. Fail: any other project's name is visible.
3. Revoke the grant in Garm, wait 10 minutes, reload. Pass: the project is gone.
4. Set `GARM_GATING` to `off` and redeploy. Pass: the `READER_EMAILS` behaviour returns. Set it back to `on`.
