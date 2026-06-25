# Data & access model

How project data is stored, how public and private data are separated, and who can read each store. Current as of 2026-06-13.

## Storage: one database, three trust tiers

Everything lives in `~/.claude/prompt-history.db` — local SQLite, one copy per machine (mini + laptop) — accessed through the `store/` abstraction (`KnowledgeStore` ABC; SQLite backend by default, Turso HTTP backend for the cloud; `get_store()` selects via the `GROUND_CONTROL_STORE` env var). Tables fall into three tiers by how far they travel:

1. **Raw / private — never leaves your machines.** `prompts`, `sessions`, `commits`. `sync_to_turso.py` deliberately does NOT push raw prompts or sessions. Actual prompt text exists only on mini/laptop.
2. **Processed / private — synced to Turso, auth-gated.** `daily_summaries`, `weekly_rollups`, `project_snapshots`, `review_snapshots`, `project_workspaces`, `api_usage`, `api_costs`, `claude_code_usage`, `project_aliases`. Claude-generated summaries that may contain project detail; visible on the cloud dashboard only after login.
3. **Public — synced to Turso, served with no auth.** `public_session_summaries`, `public_weekly_rollups`. Scrubbed, de-identified text only.

The Turso cloud DB is isolated in its own `promptlab` group (own signing key), so its token can't be derived from any other Turso group.

## Public vs private: what makes "public" safe

Three layers, all holding as of 2026-06-13:

1. **Raw text never syncs** — it can't leak from the cloud because it was never uploaded.
2. **Processed summaries are auth-gated** — synced, but only visible after login.
3. **Public tables are scrubbed-by-construction.** Written ONLY by the reviewed, git-committed `scripts/backfill_public_*.py` one-shots — never by `/handoff` (its public-write steps were removed 2026-06-13), the synthesizer, or sync (`sync_to_turso.py` only propagates existing rows). The safety property is not "human-authored" (backfill text is Claude-authored too) but "**reviewed, git-committed literal, published by a deliberate per-project one-shot**."

The public endpoint has **no read-time allowlist** — it serves whatever rows exist. Safety therefore rests entirely on the write-time discipline above, plus two curation gates with no third drifting copy:

- **Which projects are public** = the consumer's MDX manifest (`selected-projects` `content/projects/*.mdx`), the single source of truth.
- **What's in the producer tables** = reconciled to exactly that manifest. As of 2026-06-13 the public tables hold only the **7-key allowlist**: `am-i-an-ai, ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase`.

**Join-key gotcha:** the `project` column in the public tables is the consumer's **historyKey**, NOT the display slug. `showcase` renders as "rocksculpture", `am-i-an-ai` as "lojong". A slug-based purge would delete the wrong rows — always reconcile against historyKeys. Use `scripts/unpublish_public.py <project> [--apply]` (alias-aware, dry-run by default, deletes from both local + Turso) to pull a project.

**Drift guard:** `scripts/check_public_allowlist.py` is the backstop. It compares the distinct projects in BOTH stores (local + Turso — they diverge, since sync only upserts) against `docs/public-allowlist.txt` (the prompt-lab mirror of the manifest historyKeys), resolves aliases, and reports any public row outside the allowlist. Report-only — never deletes; `--fix` prints (does not run) the `unpublish_public.py` commands. Exit 0 clean / 1 drift / 2 allowlist missing. When the manifest changes, update `docs/public-allowlist.txt` and note the date. (It immediately caught 4 Turso-only strays the manual local-based purge missed — `audio-journal`, `bakerylouise_v1`, `invitekit`, `recountly` — pending purge.)

## Who accesses each store, and how

1. **You, locally** — full read of the SQLite DB on mini/laptop (`sqlite3` is allow-listed in `~/.claude/settings.json`). The pipeline scripts (synthesizer, sync, review email) run on mini via launchd.
2. **Cloud dashboard (https://prompt-labs.org)** — cookie auth (`web/auth_helper.py`): an HMAC-SHA256-signed token, 30-day expiry, `HttpOnly` + `SameSite=Strict` + `Secure` in prod. **Two tiers** (`web/api/login.py`): `admin` (the `AUTH_SECRET` password → full access incl. the Ask/LLM feature) and `reader` (the `AUTH_READ_SECRET` password → browse only). Every `/api/*` route requires a valid cookie (401 otherwise) EXCEPT `public_history`.
3. **Public endpoint** (`GET /api/public_history?project=<name>`, `web/api/public_history.py`) — unauthenticated, anyone, alias-aware, 1-hour cache, serves only the two public tables. Sole consumer: `selected-projects` (https://PianoHouseProject.org).

## How access is granted (secrets)

- **Local dev:** 1Password `dev-secrets` vault → `op://` refs in `.env.tpl` → `op inject` → gitignored `.env.local`. Keys: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `AUTH_SECRET`, `AUTH_READ_SECRET`, `ANTHROPIC_API_KEY`.
- **Production:** Vercel env vars on the `prompt-lab` Vercel project.
- **No separate dev/prod DB** — both point at the one `promptlab`-group Turso DB; the boundary is the credential, not the database.

## Data flow, end to end

```
Claude Code hooks ─→ local SQLite (raw: prompts/sessions/commits)
                         │
   synthesizer / handoff ─→ processed tables (summaries, rollups, costs)
                         │
        sync_to_turso.py ─→ Turso  (processed + public; NEVER raw prompts/sessions)
                         │                    │
   cloud dashboard ──────┘ (auth-gated)       └──→ /api/public_history (no auth)
   prompt-labs.org                                  → selected-projects / PianoHouseProject.org

   scripts/backfill_public_*.py ─→ public_* tables (reviewed, per-project, deliberate)
```
