# Roadmap — July 2026

Phased plan with pass/fail criteria. Written 2026-07-14, grounded in a code survey (not in CLAUDE.md, which had drifted on two load-bearing points — see "Corrections" below).

---

## STATE OF PLAY (updated 2026-07-21) — read this first

**Phase 2 (Google OAuth) SHIPPED + live-verified 2026-07-21** (PRs #29, #32) — prod is Google-exclusive (`ADMIN_EMAILS` → admin, `READER_EMAILS` → reader), previews keep password login. Full detail in `docs/phase2-oauth-plan.md`. §2.3/§2.4 cleanup (the `AUTH_SECRET`→beacon fallback removal, issue #30's preview-Google-button fix, this doc sweep) is being done as **"Phase A"**, tracked there — see that plan for current status rather than the stale numbered list below.

**Done previously (2026-07-14):** Ask fixed and verified on prod (§0.1 — no key was minted; the whole "key is dead" premise was wrong). Phase 1 / issue #23 shipped and merged (PR #26) — the metadata layer is live and the status toggle stalled since 2026-05-28 works. recountly deployed, Git-linked, beacon firing for the first time ever (§0.3 — root cause was *never linked*, not a broken webhook). Garm's `GARM_ADMIN_KEY` blocker unblocked via the new `garm-prompt-lab` handoff channel — it was the same `vercel env add` trap documented in §0.1.

**Open, not urgent:** Ask deserves a full page, not a modal — NOT YET FILED; file it if wanted. Ask returns long-form markdown (a ~60-line cross-project digest with headers and nested lists on 2026-07-14) and the modal is too cramped; Nico noted the raw paste read better than the app's own rendering, which is a damning signal. Leaning toward a dedicated `#/ask` route: Ask is dashboard-wide, answers are documents not one-liners, and a route gets deep-linking and back-nav free. Also check whether the modal renders markdown at all or just dumps text. Admin-only surface, so don't over-design.

**Small and open, none urgent:** close #12 (CI green since 2026-07-09); §0.4 beacon fan-out for prntd + musicforge; Preview's Anthropic key is set but unverified (blocked by Vercel deployment protection; only affects Ask on preview deploys).

**Unexplained, worth 10 minutes:** `page_views` has 3 rows for **`free-vite.com`** (2026-07-10/11), but CLAUDE.md says invitekit has no custom domain and fires only as `freevite.vercel.app`. Something serves our beacon from a domain nobody recorded. Confirm before trusting the "no real traffic" note.

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

### 0.3 recountly production deploy — DONE 2026-07-14 (root cause was not what I predicted)

Correct part: the beacon was never broken (it was correctly placed at `src/app/layout.tsx:42`), and a redeploy was the fix. Verified end-to-end — real headed browser → 204 → Turso row, `ts 2026-07-15T00:18:42Z`, `site=recountly.org`.

**Wrong part: I diagnosed a "disconnected Vercel↔GitHub integration." There was never an integration to disconnect.** `GET /v9/projects/<id>` returned `link: NULL`, and the project had **zero preview deployments across its entire 43-day history** — not just since Jun 27. Every deploy it ever had was a hand-run `vercel --prod`. Nothing broke on Jun 27; the workflow moved to GitHub PRs, and on an unlinked project merging a PR deploys nothing. The 17-day gap was simply time since someone last ran the command.

**Where my reasoning failed, and the fix:** I looked only at the recent window ("zero deploys *since Jun 27*") and inferred a break. Had I checked the *whole* history I'd have seen zero previews ever, which cannot mean "the webhook broke" — a removed webhook leaves previews behind from before it broke. **Never-linked and recently-broken are distinguishable, but only by looking past the window you're suspicious about.**

**Three diagnostics retired — all three actively mislead:**
1. **`gh api repos/:owner/:repo/hooks` says nothing about Vercel linkage.** Vercel connects via a **GitHub App**, which creates no repo-level webhooks — it returns empty whether linked or not (still empty now that recountly IS connected). I called this "corroborating"; it was worth exactly zero. Check `link` on `GET /v9/projects/<id>`.
2. **`_vercel/insights` is a stale marker.** `@vercel/analytics` 2.0.1 serves via a randomized anti-adblock path (recountly's: `/7bd029f5969d4043/script.js`, containing `vercel/insights` internally, POSTing to `/<hash>/view`). Analytics was working the whole time; grepping for `_vercel/insights` is a false negative on any current site — including the "both appear together" pass criterion I wrote below, whose Analytics half was meaningless.
3. **`githubCommitSha`/`githubCommitRef` don't imply a git trigger.** The CLI stamps local checkout metadata onto manual deploys — precisely what makes an unlinked project look linked. The tell is `target`: every deploy production, zero previews ever.

**Result:** repo is now connected; main auto-deploys and PRs get previews, both halves verified.

**Consequence worth carrying:** that Turso row is the **only** `recountly.org` row that has ever existed. The beacon had never fired once, so anything reading beacon data for recountly was reading **a hole, not a zero**. A site missing from `#/visitors` means "never instrumented," not "no traffic."

Local hygiene: the `~/src/recountly` clone sat on branch `add-visitor-beacon` with `origin/main` pinned at `955aa48` while real main was `610650a` — a commit not even in the local object store, so local `git grep` reported the beacon absent. `git fetch && git checkout main && git pull` before drawing conclusions from a clone.

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

### DECISION: no `package.json` — hand-roll OAuth in Python (decided 2026-07-14)

The blocker everyone reaches for first is "Google login means Auth.js, Auth.js means Next.js, and `web/` has no `package.json`." Four options were weighed:

**A. Hand-roll the OAuth flow in Python — CHOSEN.** ~150 lines, **zero new dependencies**, no new runtime, and it fits the existing architecture exactly (the app is 11 small `BaseHTTPRequestHandler` files; this adds a 12th). Details below.

**B. Convert `web/` to Next.js — rejected.** Rewrites 11 Python handlers into TypeScript *and* the entire single-file Preact/HTM frontend, and introduces a build step where there is none. Enormous, and almost entirely unrelated to "let Nico sign in with Google." It would swallow the project whole.

**C. Mixed runtime — a few Node/Next auth routes beside the Python API — rejected.** Vercel does support this. But the session cookie would have to be written by TypeScript and read by Python, so both sides must agree on a token format. Auth.js defaults to encrypted JWE, which Python can't easily read; you'd have to force a shared HMAC JWT and hand-verify it in Python anyway — i.e. do option A's work *plus* carry a second runtime and language. Worst of both.

**D. Third-party auth (Clerk / Auth0 / Descope) — rejected.** Same interop problem (JS-first SDKs; Python would verify their JWTs via JWKS), plus a vendor and a bill. Enormous overkill when admin is one person and there is exactly one provider.

**Why A is smaller than it sounds — the key insight: no JWT signature verification is needed.** This is a *confidential client* using the authorization-code flow, so the `id_token` arrives at our server **directly from Google's token endpoint over TLS**, authenticated with our `client_secret` — not via the browser. Google's own docs say a server doing its own code exchange may skip verifying the ID token signature, precisely because the TLS channel to Google *is* the trust anchor. (Signature verification is what you need when a token reaches you through an untrusted channel, e.g. the implicit flow.) So: exchange the code, base64-decode the `id_token` payload, read `email` / `email_verified`. **No crypto library, no JWKS fetch, no `google-auth` dependency, nothing added to `web/requirements.txt`.** `urllib` — already used throughout this repo — is sufficient.

Sketch of the whole flow:
1. `GET /api/login?provider=google` → 302 to Google's authorize URL with `client_id`, `redirect_uri`, `scope=openid email`, and a **signed `state`** (HMAC it with `AUTH_SECRET` using the existing `auth_helper` primitives — this is the CSRF defense and is not optional).
2. Google → `GET /api/callback?code=…&state=…`. Verify `state`'s HMAC first, before touching `code`.
3. `POST https://oauth2.googleapis.com/token` (code + client_id + client_secret + redirect_uri) → response contains `id_token`.
4. Base64-decode the `id_token` payload. Require `email_verified == true`. Map `email` → role.
5. Mint the existing session token (extended to carry `sub`/`email`, not just `role`) and set the cookie.

New env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (1Password + Vercel — and see §0.1's hard-won notes on `vercel env add` before touching that CLI). The redirect URI must be registered in Google Cloud Console for both prod and preview origins.

**Still true and still the real work:** the landmines below (the `AUTH_SECRET` triple-overload and `SameSite=Strict`) are what make Phase 2 non-trivial — not the absence of a `package.json`. Do §2.0 first.
- **`AUTH_SECRET` is overloaded three ways**: admin password (`login.py:22`), HMAC token-signing key (`auth_helper.py:16`), **and the beacon visitor-hash salt** (`beacon.py:73`). Retiring it without care silently rotates every visitor hash and breaks `#/visitors` continuity at the seam.
- **`SameSite=Strict` (`auth_helper.py:78`) breaks the OAuth callback redirect.** Must become `Lax`.
- Token payload carries only `{exp, role}` (`auth_helper.py:19`) — needs `sub`/`email`.
- `vercel.json:4` `includeFiles` must list any new helper module or it won't ship to the functions.
- `verify_token` defaults role to `"admin"` when absent (`auth_helper.py:41`) — a fail-open default that must not survive into an identity-bearing token.

### 2.0 Decouple the beacon salt — do this FIRST, on its own
New `BEACON_SALT` env var, defaulting to `AUTH_SECRET` for one deploy, then set explicitly and remove the fallback.

**Pass:** `visitor_hash` for a fixed `(ip, ua, date)` triple is byte-identical before and after the change; only then proceed.
**Fail:** any hash change — means the `#/visitors` series would break at the cutover.

### 2.1 OAuth flow — SHIPPED 2026-07-21 (PR #29)
As built: `login.py` `do_GET` handles `?provider=google` (the initiate/redirect); `web/api/callback.py` does the code exchange and ID-token verification (no signature check needed — confidential client, TLS direct from Google). The `GET /api/login` session-check contract was preserved. Password form replaced with a "Sign in with Google" link, gated by the 401 body's `password_login`/`google_login` flags (see §2.3.1 below). Superseded the stale line refs this section used to cite (`index.html:663`, "`do_POST` becomes the initiate") — see `docs/phase2-oauth-plan.md` for the as-built file-by-file breakdown.

**Pass:** Google sign-in sets the cookie; `GET /api/login` returns role **and** email. Verified live 2026-07-21.

### 2.2 email→role mapping — SHIPPED 2026-07-21 (PR #29, amended same day in #32)
Env allowlist (`ADMIN_EMAILS`), **not** a table — the table is Garm's job. Amended same day: `READER_EMAILS` added (Elijah, `elovejoy5@gmail.com`) for full read access, no Ask/metadata; admin wins on overlap.

**Pass:** `nlovejoy@me.com` → admin. An unknown email → an explicit 403 with a readable message, never a blank page or a silent admin grant. Verified live.

### 2.3 Cleanup after cutover ("Phase A")
Password login was gated to non-production from day one (no overlap window needed) rather than run behind a flag. Remaining cleanup, done as "Phase A" per `docs/phase2-oauth-plan.md`'s Deploy/cutover step 5:
- Remove the `BEACON_SALT`→`AUTH_SECRET` fallback in `beacon.py` (unset `BEACON_SALT` now fails closed — drops the hit rather than borrowing another secret).
- **2.3.1 — issue #30:** previews showed a "Sign in with Google" button pinned to prod's redirect URI, silently logging you into prod instead of the preview. Fixed by mirroring `password_login` with a `google_login` flag (`VERCEL_ENV == "production"`) in the `GET /api/login` 401 body; the frontend renders the Google button only when it's true.
- `AUTH_READ_SECRET` deleted from Vercel (kills preview *reader* password login — accepted; previews are admin-password-only now).
- `BEACON_SALT` set in Preview/Dev Vercel envs (Nico's manual step).

**Pass:** both preview and prod auth paths work correctly for their environment; `AUTH_READ_SECRET` deleted from Vercel and no code references it; `beacon.py` has no `AUTH_SECRET` dependency.

### 2.4 Docs + tests — done as part of "Phase A"
`scripts/test_web_api.py`, `.env.tpl`, `README.md:85`, `docs/data-and-access.md:37,42`, `CLAUDE.md` (owned by the main session, not touched here).

**Pass:** suite green (74+ tests); `docs/data-and-access.md`'s auth section describes what actually ships (Google-exclusive prod, password-only preview).

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
