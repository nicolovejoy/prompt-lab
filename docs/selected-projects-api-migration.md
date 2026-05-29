# Migrating selected-projects to `/api/public_history`

Status: **investigation pending** — hypothesis unverified, no code changes yet.

## Context

prompt-lab exposes project history through two surfaces:

1. **HTTP API** — `GET /api/public_history?project=<name>` (`web/api/public_history.py`), gated by a hardcoded `PUBLIC_PROJECTS` allowlist. Current consumer: `byside` (alias `offer-builder`).
2. **Direct Turso reads** — `public_session_summaries` + `public_weekly_rollups` tables, accessible to anyone holding `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`. Suspected consumer: `selected-projects` (lives at https://pianohouseproject.org, alias `pianohouse`, **not checked out under `~/src/`**).

The CLAUDE.md Next Step ("Investigate how selected-projects currently consumes…") tracks this. This doc captures the analysis so we can pick it up later.

## Why migrate

If the hypothesis holds (selected-projects reads Turso directly):

- **The Turso token is a shared secret across consumers.** Anyone with it can read any row in the public tables. The allowlist lives only at the sync-time filter in `sync_to_turso.py`, not at read time — if a row sneaks into the public tables (bug, new project, manual edit), it's exposed without an explicit per-project check.
- **Two enforcement surfaces drift over time.** Today both surfaces hold "what's public." Tomorrow you add a new public field via the API but forget to filter it at the Turso sync step (or vice versa). One allowlist as the only gate is structurally simpler.

After migration: `PUBLIC_PROJECTS` in `web/api/public_history.py` becomes the single gate. The Turso token is a true backend secret again (only `web/` holds it). The token can then be rotated to invalidate any lingering copies.

## Prerequisite (cheap, do first)

**Confirm how selected-projects actually reads the data** before doing any migration work. Two paths:

a. Find the repo (not under `~/src/`) and grep for `TURSO_DATABASE_URL` / `public_session_summaries` / `public_weekly_rollups`.

b. Use the cross-agent handoff mechanism in `CLAUDE.md:41` — append a question to `~/src/.handoff/selected-projects-prompt-lab.md` (file/dir doesn't exist yet; create them). The question surfaces next time someone works in selected-projects.

If it turns out selected-projects doesn't talk to Turso (or already uses the API), the rest of this doc is moot.

## Migration plan (conditional on hypothesis)

### prompt-lab side — ~5 minutes

1. Optional: review what's in `public_session_summaries` / `public_weekly_rollups` for `project = 'selected-projects'`. Already public via Turso, but worth a glance before flipping the gate.
2. Edit `web/api/public_history.py:20`:
   ```python
   PUBLIC_PROJECTS = {"byside", "selected-projects"}
   ```
3. `cd web && vercel --prod`

### selected-projects side — ~30–60 minutes

1. Find the current Turso query (likely a small client using `@libsql/client` or equivalent).
2. Replace with a server-side fetch:
   ```ts
   const res = await fetch(
     "https://prompt-labs.org/api/public_history?project=selected-projects",
     { next: { revalidate: 3600 } } // if Next.js
   );
   const { sessions, rollups } = await res.json();
   ```
3. Map response shape to whatever the render code expects. API returns:
   ```
   {
     project: string,
     sessions: [{ session_id, started_at, public_summary }],
     rollups:  [{ week_of, public_summary, session_count, commit_count }]
   }
   ```
4. Remove `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from project env (Vercel project settings + local `.env`).
5. Deploy.

### Aftercare — ~5 minutes

- Rotate the Turso auth token to invalidate old copies.
- Update `web/`'s `TURSO_AUTH_TOKEN` env var on Vercel.

**Total wall-clock: ~1 hour, mostly on the selected-projects side.**

## API contract (reference)

From `web/api/public_history.py`:

- `GET /api/public_history?project=<name>` → 200 with `{ project, sessions, rollups }`
- Aliases are resolved before the allowlist check (e.g. `?project=offer-builder` resolves to canonical `byside`).
- Not on allowlist → 404 `{"error": "not found"}`.
- Cache-Control on 200: `public, max-age=3600, stale-while-revalidate=86400`.
- `limit` query param (default 20, max 100) caps `sessions`. Rollups are unbounded but typically small.

CORS: no headers set. The API is intended for server-side fetches (matches both byside's and selected-projects' likely usage in Next.js Server Components). If a future consumer needs browser-side fetch, CORS will need adding.

## Risks / caveats

- **The selected-projects code is not visible from this repo.** All effort estimates above assume a small Turso client to replace. If it's larger or more entangled, the selected-projects side could grow.
- **Token rotation has a coordination cost.** Both `web/` (prompt-lab Vercel project) and any local sync scripts on the laptop/mini need the new token simultaneously. Schedule the rotation for a quiet window.
- **`PUBLIC_PROJECTS` doesn't gate Turso reads.** Anyone with the old token can still read until rotation completes. The migration only closes the leak after rotation, not when the allowlist is updated.

## Suggested handoff entry

To kick off the prerequisite via the cross-agent file, create `~/src/.handoff/selected-projects-prompt-lab.md` with:

```markdown
## Active

### 2026-05-14 — Confirm data source for project history on /about

prompt-lab is investigating whether selected-projects reads Turso directly
(`public_session_summaries`, `public_weekly_rollups`) or via the
`/api/public_history` HTTP endpoint. Please grep the repo for
`TURSO_DATABASE_URL`, `public_session_summaries`, or `public_weekly_rollups`
and report back here. Context:
~/src/prompt-lab/docs/selected-projects-api-migration.md

## Archived

(none yet)
```
