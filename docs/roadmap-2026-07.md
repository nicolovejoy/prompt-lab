# Roadmap — July 2026

Phased plan with pass/fail criteria. Written 2026-07-14, grounded in a code survey (not in CLAUDE.md, which had drifted on two load-bearing points — see "Corrections" below).

Sequencing rationale: Phase 2 (identity) is the keystone — it unblocks #10 and prompt-lab's own Garm consumption. Phase 1 is done first anyway because it's fully buildable today, is smaller, and clears the status-toggle item that has been stalled since 2026-05-28. Phase 5 is fill-in work with no dependencies.

---

## Corrections to CLAUDE.md found while planning

**1. Issue #23's premise is inverted.** CLAUDE.md:175 says to "move status ownership to Turso so `sync_to_turso.py` stops clobbering a cloud-set value." That bug cannot occur:

- `sync_to_turso.py` never writes the `projects` table (grep matches only `project_aliases`, `project_snapshots`, `project_workspaces`).
- Turso has no `projects` table at all — `store/turso_store.py:720` returns `set()` with the comment "No projects table in Turso".
- `web/` never reads `projects` either (zero `FROM/INTO/UPDATE projects` matches under `web/`).

The real gap is the inverse: `projects` is local-SQLite-only and **never reaches the cloud**. #23 is a *create-in-Turso* task, not a *stop-clobbering* task. Also, `status` and `category` **already exist** in `store/sqlite_store.py:159-167`; only `private` is new.

**2. `web/api/projects.py` no longer exists.** CLAUDE.md:181 calls it "dead UI code." It's already gone — `web/api/` has 11 handlers, none named `projects.py`.

---

## Phase 0 — Unblock (mostly Nico's hands)

### 0.1 Fix `ANTHROPIC_API_KEY` on Vercel — Ask is down (DONE 2026-07-14)

**No key needed minting.** The prior session's plan ("the key is dead, mint a new one — Anthropic never re-reveals a value, so `prompt-lab-key-1` is unrecoverable") was half wrong, and the correction matters for next time:

- `prompt-lab-key-1` in 1Password is **alive** — verified by authenticating against `/v1/messages` (HTTP 200) on 2026-07-14. Its value was never lost; single-reveal applies to the *Anthropic console*, not to a value already saved in 1Password at creation.
- It is what `.env.tpl:5` points `ANTHROPIC_API_KEY` at, which is why the nightly synthesizer and review emails never broke — only the cloud dashboard did.
- Vercel held a **different, older** key: its `ANTHROPIC_API_KEY` var was created 109 days ago vs. the op item's ~30. That older copy is what 401s.

Fix was to copy the good value into Vercel, not to mint. **One command per environment — do not loop, and do not strip the newline:**

```
cd ~/src/prompt-lab/web && op read "op://dev-secrets/prompt-lab-key-1/credential" | vercel env add ANTHROPIC_API_KEY production --force -y
```

Repeat verbatim for `preview` and `development`, running each on its own, then `vercel --prod`.

**Two traps, both hit for real on 2026-07-14:**

1. **Never pipe through `tr -d '\n'`.** It looks prudent (avoid a trailing newline in the value) and it is exactly wrong. `vercel env add` does not take the value as an argument — it opens an **interactive `? Value?` prompt** and reads one line from stdin. The newline is the *submit*, not part of the value; the prompt discards it as the line terminator. Strip it and the CLI accepts all 108 characters, then blocks forever waiting for an Enter that never arrives, writes nothing, and exits with no error. The symptom is a `? Value?` line with asterisks and **no `Overrode`/`Added` confirmation**.
2. **Don't wrap it in a `for` loop.** The first iteration's interactive prompt takes over the TTY and consumes the rest of the loop's stdin, so iterations 2+ get an empty `? Value?` and silently write nothing. Observed exactly: production was written, preview and development were not.

**Verify the write, don't assume it.** `vercel env ls` shows each var's age — after a successful write it reads seconds, not days. A partial write shows up as a split: `ANTHROPIC_API_KEY | Production | 45s ago` on one row and `ANTHROPIC_API_KEY | Development, Preview | 109d ago` on another. Env vars are applied at deploy time, so a redeploy is required for any change to take effect.

**Pass:** Ask on https://prompt-labs.org returns an answer; `vercel logs prompt-labs.org --status-code 500 --json` shows no new 401s from `api.anthropic.com`.
**Fail:** still 401 → stray newline, or saved to only one environment.

**Lesson for the next credential scare:** check whether the secret store already holds a working value *before* concluding a key is unrecoverable, and compare the age of the Vercel var against the op item — a 109-vs-30-day gap was the tell that these were two different keys, not one dead one. Test the local key first: if the nightly pipeline is healthy, the key is fine and only the cloud copy is stale.

The op record is **`prompt-lab-key-1`** — already canonical in `.env.tpl:5`; don't create a second record (Vercel has its own env store and never reads `.env.tpl`). Do **not** use `ANTHROPIC_ADMIN_KEY-4-prompt-lab` or `admin-cost-tracking-2026-05` — both are Admin-API-only, invalid for `/v1/messages`.

Known consequence: local and production now share one key, so revoking it kills both. Accepted for now; mint a Vercel-only key if that isolation is ever wanted.

### 0.2 Close #12
CI has been green on `main` since the 2026-07-09 ruff fix; the last 5 runs all succeeded. The issue is stale.

**Pass:** #12 closed, referencing the fixing commit.

### 0.3 recountly production deploy — not a beacon bug
The beacon **is** on recountly's main (`src/app/layout.tsx:42`), correctly placed in the single root layout. The reason it isn't firing: **recountly has not deployed to production since 2026-06-27** (17 days). `vercel ls` shows zero deployments of any kind since — no previews either, though PRs #12 and #13 both merged after that date. Since Git integration auto-creates a preview per PR push, producing none points at a **disconnected Vercel↔GitHub integration**, not a failing build (there are no ERROR-state deploys). Prod HTML confirms it: `https://recountly.org` serves neither `beacon.js` nor `_vercel/insights` — a bundle predating both PRs.

Nico: check recountly's Git settings at https://vercel.com/nico-lovejoys-projects and redeploy main.

**Pass:** recountly.org HTML contains `prompt-labs.org/beacon.js` **and** `_vercel/insights` (both appearing together confirms the stale-deploy diagnosis), and a `page_views` row with `site=recountly.org` lands in Turso.

Local hygiene, unrelated to prod: the `~/src/recountly` clone sits on branch `add-visitor-beacon` with `origin/main` pinned at `955aa48` — GitHub's real main is `610650a`, which isn't even in the local object store. `git fetch && git checkout main && git pull` before touching that repo.

### 0.4 Finish the beacon fan-out — prntd + musicforge
The last two holds from issue #9. Both trees are workable now:

- **prntd** — Next App Router, `src/app/layout.tsx`, clean tree, up to date. Same one-line `<Script src="https://prompt-labs.org/beacon.js" strategy="afterInteractive" />` as the other six repos.
- **musicforge** — Vite, not Next. Entry is `frontend/index.html` (a plain `<script defer src>` tag); `frontend/src/main.tsx` also exists. Tree has a dirty `lilypond-data` **submodule** only — no tracked-file edits, so it does not block a layout change.

**Pass:** one PR per repo, merged; a real-browser load of each site lands a `page_views` row with the correct Origin-derived `site`. Curl alone is not a pass — the cross-origin `sendBeacon` is the thing under test.

---

## Phase 1 — Project metadata layer (#23)

Turso-native `project_metadata`, dashboard-written, never synced. This is exactly the shape of the existing `issue_categories` table (DDL in `scripts/classify_issues.py:34-41`, upsert in `web/api/todos.py:169-176`, absent from both `TursoStore.migrate()` and `sync_to_turso.py`).

Why that shape and not "teach sync to skip these columns": the beacon set the precedent deliberately (`web/api/beacon.py:1-6`) — *eliminate the sync leg* for dashboard-writable data rather than add skip-logic to it. No local counterpart means drift is structurally impossible, which is the lesson from the month-long cost-pipeline drift.

### 1.1 `scripts/create_project_metadata.py`
Idempotent DDL, mirroring `scripts/create_page_views.py`:

```sql
CREATE TABLE IF NOT EXISTS project_metadata (
    project    TEXT PRIMARY KEY,
    category   TEXT,
    private    INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT
);
```

**Pass:** runs twice with no error; table present in Turso.

### 1.2 `web/api/project_metadata.py`
`GET` (any valid cookie) + `POST` (admin only). Upsert via `turso_query`, project name folded through `resolve_project_names()` so aliases don't create duplicate rows. Gate with `is_authenticated()` / `get_role()` from `web/auth_helper.py` — the `todos.py:126` pattern.

**Pass:** unauthenticated → 401; reader POST → 403; admin POST → 200 and the row lands; GET reflects it.
**Fail:** an alias (e.g. `offer-builder`) creating a second row alongside `byside`.

### 1.3 Wire the reads
`web/api/overview.py` and `web/api/project.py` join `project_metadata` so status/category/private reach the dashboard. Note `TursoStore.get_overview` hardcodes `"project_statuses": {}` (`turso_store.py:764`) and `get_project_detail` hardcodes `status/category/notes` (`turso_store.py:722-735`) — but `web/` bypasses the store layer entirely and issues raw SQL, so the fix belongs in the endpoints, not the store.

**Pass:** `/api/overview` returns a populated `project_statuses` map sourced from Turso.

### 1.4 Frontend
Status `<select>` on ProjectPage (the item stalled since 2026-05-28), category display, `private` hide-toggle on home.

**Pass:** change status in the UI → hard reload → it persists. A `private` project is visually marked and hidden behind a toggle.

### 1.5 Tests
Add to `scripts/test_web_api.py`.

**Pass:** full suite green.

### Guards — read before building
- **`private` is cosmetic ONLY.** It is not the public-data gate. That gate is the `public_session_summaries` / `public_weekly_rollups` tables + `docs/public-allowlist.txt` + the consumer's MDX manifest. A `private` column that *looks* authoritative but isn't is the main hazard in this phase — it is the same "third drifting copy of what's public" mistake that `PUBLIC_PROJECTS` already was, and that was deleted for exactly this reason (2026-06-03). State it in the endpoint docstring and in `docs/data-and-access.md`.
- **Do not add `projects` to `sync_to_turso.py`.** Local `projects` stays local and authoritative for the local pipeline; Turso `project_metadata` is cloud-owned. Two tables, no sync leg, no drift.
- **Category is display-only, not a sharing unit** (per #23).
- `store/base.py:339` `update_project(name, **fields)` needs no signature change; only the allowlist at `sqlite_store.py:798` would need `private` — and only if the local store needs to know about it at all, which it may not.

---

## Phase 2 — Google login (#10 prerequisite, #24 prerequisite)

The keystone. Per `docs/garm-needs-assessment.md:21`, prompt-lab has "no per-user identity at all" — two shared passwords. **This is not swapping one login for another; it's introducing a principal where none exists.** No users table, no email column, nothing keyed by person anywhere in the schema.

### Landmines found in the survey — all of these bite before any OAuth code runs

- **`web/` is plain static HTML + Python serverless.** No `package.json` anywhere in the repo, no Next.js, no build step. **There is no NextAuth/Auth.js path.** Either hand-roll the OAuth code exchange in Python, or convert `web/` to Next.js first. **Recommend hand-rolling** — the app is 11 small `BaseHTTPRequestHandler` files; a framework conversion is a much larger, unrelated project that would swallow this one.
- **`AUTH_SECRET` is overloaded three ways**: admin password (`login.py:22`), HMAC token-signing key (`auth_helper.py:16`), **and the beacon visitor-hash salt** (`beacon.py:73`). Retiring it without care silently rotates every visitor hash and breaks `#/visitors` continuity at the seam.
- **`SameSite=Strict` (`auth_helper.py:78`) breaks the OAuth callback redirect.** Must become `Lax`.
- Token payload carries only `{exp, role}` (`auth_helper.py:19`) — needs `sub`/`email`.
- `vercel.json:4` `includeFiles` must list any new helper module or it won't ship to the functions.
- `verify_token` defaults role to `"admin"` when absent (`auth_helper.py:41`) — a fail-open default that must not survive into an identity-bearing token.

### 2.0 Decouple the beacon salt — do this FIRST, on its own
New `BEACON_SALT` env var, defaulting to `AUTH_SECRET` for one deploy, then set explicitly and remove the fallback.

**Pass:** `visitor_hash` for a fixed `(ip, ua, date)` triple is byte-identical before and after the change; only then proceed.
**Fail:** any hash change — means the `#/visitors` series would break at the cutover.

### 2.1 OAuth flow
`login.py` `do_POST` becomes the initiate/redirect; new `web/api/callback.py` does the code exchange and ID-token verification. Preserve the `GET /api/login` session-check contract — `index.html:663` depends on it. Replace the password form at `index.html:511-545` with a "Sign in with Google" link.

**Pass:** Google sign-in sets the cookie; `GET /api/login` returns role **and** email.

### 2.2 email→role mapping
Start with an env allowlist (`ADMIN_EMAILS`), **not** a table. The table is Garm's job — building a local grants table here would be the thing Garm exists to delete.

**Pass:** `nlovejoy@me.com` → admin. An unknown email → an explicit 403 with a readable message, never a blank page or a silent admin grant.

### 2.3 Overlap, then remove the password path
Keep password login behind a flag for one deploy as break-glass.

**Pass:** both paths work during overlap; after removal, `AUTH_READ_SECRET` is deleted from Vercel and no code references it.

### 2.4 Docs + tests
`scripts/test_web_api.py:649,708` (sets `AUTH_SECRET="test-secret"`), `.env.tpl`, `README.md:85`, `docs/data-and-access.md:37,42`, `CLAUDE.md:19`.

**Pass:** suite green; `docs/data-and-access.md`'s two-tier-auth section describes what actually ships.

---

## Phase 3 — Login visibility (#10)

**This phase starts with a decision, not a build.** The plan of record says to add `login` to the beacon's `event` allowlist and ride the existing pipeline. That is probably wrong: the beacon is **anonymous by construction** (no cookies, no raw IP, a daily-rotating `visitor_hash`), and the entire point of #10 is knowing *who* signed in. Attaching an email to it would quietly destroy the property that makes `page_views` safe.

So the likely shape is a **separate `login_events` table carrying an email** — a deliberate, documented departure from `docs/measurement-policy.md`'s "never a stable identifier" rule, not a free ride on existing infrastructure. Decide before building.

**Pass:** one auditable record per sign-in with the email; a last-N-logins panel; `docs/measurement-policy.md` amended to record the exception and its rationale.
**Fail:** an email landing in `page_views`.

---

## Phase 4 — Garm consumption + People admin page (#24)

**Blocked** on Phase 2 and on ibuild4you shipping the `garm` repo + `/gnipahellir`. The build plan lives at `~/src/garm/docs/build-plan.md`; the spec is `docs/garm-needs-assessment.md`. prompt-lab owns the People admin UI (prompt-labs.org); the Garm side stays API-only for now.

Check `~/src/.handoff/ibuild4you-prompt-lab.md` for status before starting.

**Pass:** a grant made in the People page is honored by a `/gnipahellir` check for `(email, project)`; hierarchy resolves server-side; a denied check is logged for future Howl.

---

## Phase 5 — Design tokens (#14)

~150 scattered `font-size` magic numbers (24 distinct `rem` values) in `web/index.html` → a token scale. No dependencies; fill-in work between phases. The 2026-07-09 readability pass deliberately deferred this and filed #14 rather than entrench the ad-hoc values further.

**Pass:** no raw `font-size` outside the token block; a rendered diff of home / project / costs shows no unintended visual change.

---

## Known follow-ups, unfiled

- `CostChart` (project detail) and the home activity chart still carry the hover-only tooltip + non-collapsing two-column legend pattern that #21/#22 fixed on `#/visitors` and `#/costs`. Noted 2026-07-13, never filed.
- Nico flagged that the mobile-forward UX pass cost something on desktop/web and said he'd share specifics. Still outstanding — ask rather than assume the mobile work is clean. (An uncommitted edit to CLAUDE.md deletes this note; it is preserved here until he says it's resolved.)
