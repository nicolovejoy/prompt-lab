# Phase 2 — Google OAuth implementation plan

Written 2026-07-21 (mini). Execution plan for §2.1–§2.4, grounded in a fresh read of the actual code (`web/auth_helper.py`, `web/api/login.py`, `web/index.html`, `web/vercel.json`, `scripts/test_web_api.py`). §2.0 (beacon salt) already shipped (`70ec871`).

Companion to `docs/roadmap-2026-07.md` Phase 2 — that has the *why* (option A vs B/C/D, the "no signature verification" insight). This has the *what*, file by file, with the four open decisions now settled.

---

## Settled decisions (2026-07-21)

1. **Reader tier → admin-only until Garm.** `ADMIN_EMAILS` env allowlist only. No `READER_EMAILS`. Any verified Google email not in `ADMIN_EMAILS` → readable 403. Reader tier is Garm's job; building a second allowlist here is the thing Garm exists to delete.
2. **Preview auth → keep the password path preview-only.** Google won't register wildcard `*.vercel.app` redirect URIs, so preview deploys can't do the OAuth round-trip. The password `POST /api/login` survives, gated to non-production only, as the way into previews. Production uses Google exclusively.
3. **Legacy `{exp, role}` cookies → reject on deploy.** `verify_token` requires the new `{exp, role, email}` shape. Old cookies fail verification → one re-login for Nico. This immediately kills the fail-open `role` default (no overlap window where it lingers).
4. **email→role → env allowlist, not a table.** `ADMIN_EMAILS` (comma-separated). `nlovejoy@me.com` → admin.

---

## Prep Nico owes BEFORE live verify (none of it exists yet)

Verified 2026-07-21: no `GOOGLE_*`/`CLIENT` vars in Vercel, no matching item in 1Password `dev-secrets`. The Google Cloud OAuth client has not been created. **All code below can be written and unit-tested without these**, but live verification is blocked until they exist.

1. **Google Cloud OAuth client** (console.cloud.google.com → APIs & Services → Credentials → Create OAuth client ID → Web application):
   - Authorized redirect URI: `https://prompt-labs.org/api/callback`
   - (Preview origins deliberately omitted — decision 2. No `*.vercel.app` wildcard.)
   - Yields a client ID and client secret.
2. **1Password** (`op item create`, run by Nico — hook blocks it for the agent): store both under one item, e.g. `Prompt Lab Google OAuth` with fields `client_id` and `client_secret`. Pin the exact `op://dev-secrets/...` paths for `.env.tpl`.
3. **Vercel env** — `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`, Production only (previews don't use Google). **Heed roadmap §0.1 traps:** one `vercel env add` per var, no `tr -d '\n'`, no `for` loop, verify with `vercel env ls` (fresh write reads seconds-old). Prime with `op read >/dev/null` first to dodge the op-session-timeout empty-stdin failure.
4. **`ADMIN_EMAILS`** — set in Vercel (Production + Preview) to `nlovejoy@me.com` (comma-separated if more later).
5. `.env.tpl` — add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (→ the new 1P item), `ADMIN_EMAILS`.

---

## File-by-file implementation

### `web/auth_helper.py`
- **`make_token(role, email=None)`** — payload becomes `{exp, role, email}`. `email` is `None` for password logins (preview break-glass) and the Google address for OAuth logins. The `email` key is ALWAYS present in the payload, even when null — that's what distinguishes new-shape tokens from legacy.
- **`verify_token(token)`** — return the **full payload dict** (`{role, email, exp}`) or `None`, NOT just the role string. Require **both the `role` and `email` KEYS present** (key-presence, not truthiness — `email: null` is valid). This simultaneously (a) drops the fail-open `.get("role", "admin")` (current line 41) and (b) rejects legacy `{exp, role}` cookies, which have `role` but no `email` key — requiring only `role` would NOT reject them (decision 3 would silently not happen).
- **`get_role` / `is_authenticated`** — adapt to the dict return. `get_role` returns `payload["role"]`; add `get_identity(headers)` returning the dict (email + role) for `GET /api/login`.
- **`set_cookie_header(role, email=None)`** — thread `email` through to `make_token`. **`SameSite=Strict` → `Lax`** (both `set_cookie_header` line 78 and `clear_cookie_header` line 88). Precise reason: the callback *sets* the cookie fine under Strict; what Strict breaks is *sending* it on top-level navigations in the cross-site-initiated chain (Lax's carve-out is exactly top-level GET navigations). Don't "optimize" back to Strict because the callback appeared to work — the same-origin session-check fetch masks the breakage intermittently.
- **New HMAC `state` helpers** — `make_state()` / `verify_state(state)`: HMAC over `{exp, nonce}` with `AUTH_SECRET` (token-signing key, reuse the existing primitive), ~10 min expiry. This is the CSRF defense on the OAuth round-trip; not optional. **Accepted trade-offs (documented, not bugs):** state is signed but not browser-bound (no state-cookie double-submit) and replayable within its window — a login-CSRF attacker can only mint a session for an email in `ADMIN_EMAILS`, so with one admin the risk is nil. If Garm-era multi-user ever lands, add the state cookie (~5 lines).

### `web/api/login.py`
- **`do_GET`** — branch on `?provider=google`: build Google's authorize URL (`client_id`, `redirect_uri=https://prompt-labs.org/api/callback`, `scope=openid email`, `response_type=code`, signed `state`), 302 to it. **Bare `GET /api/login` (no query) keeps the existing session-check contract** — returns `{authenticated, role, email}` — because `index.html:685` depends on it. The **401 body gains `{"password_login": true|false}`** (`VERCEL_ENV != "production"`) so the frontend knows whether to render the password form — no build-time preview detection, no dead password box on prod (settles the "decide during impl" from the earlier draft).
- **`do_POST`** (password path) — **gate to non-production only**: if `os.environ.get("VERCEL_ENV") == "production"`, return 403 (password login disabled in prod). Otherwise behave as today (admin/reader password → cookie, `email=None`) so previews stay reachable.
- **`do_DELETE`** (logout) — unchanged.

### `web/api/callback.py` (NEW, ~90 lines, urllib only)
1. **Handle Google's error redirect first:** `?error=access_denied` (user cancels consent) arrives with no `code` — return a readable 4xx page, never a KeyError 500.
2. Parse `code` + `state` from query. **Verify `state` HMAC first**, before touching `code`. Bad/expired state → 400.
3. `POST https://oauth2.googleapis.com/token` with `code`, `client_id`, `client_secret`, `redirect_uri`, `grant_type=authorization_code` (urllib, form-encoded). Response JSON contains `id_token`. Non-200 from Google → readable 502-ish error, not a traceback.
4. **base64-decode the `id_token` payload — no signature verification** (confidential client, token arrived over TLS direct from Google — settled DECISION in roadmap). Implementation note: JWT segments are unpadded base64url — pad with `+ "=" * (-len(seg) % 4)` or `urlsafe_b64decode` throws. Read `email`, `email_verified`, `aud`.
5. **Require `aud == GOOGLE_CLIENT_ID`** — one line, closes token-substitution edge cases the TLS argument doesn't cover.
6. Require `email_verified == true`. Else readable 403.
7. `email in ADMIN_EMAILS` → role `admin`; else → readable 403 (decision 1: no reader tier yet). Unknown email must be an explicit, readable 403 — never a blank page, never a silent admin grant.
8. Mint cookie via `set_cookie_header("admin", email)`, 302 to `/` (fixed target — no open-redirect surface).

### `web/vercel.json`
- Add `callback.py`'s needs to `includeFiles` if it imports a new helper. It imports `auth_helper` (already listed) — so likely **no change**, but confirm: `includeFiles` currently is `{auth_helper.py,turso_helper.py,classify_helper.py}`. `callback.py` needs only `auth_helper` → fine. (If a new shared `oauth_helper.py` is factored out, add it here.)

### `web/index.html`
- **Login component (≈533–567)** — primary action becomes a **"Sign in with Google"** link → `window.location = '/api/login?provider=google'`. The password form renders **only when the session-check 401 body says `password_login: true`** (i.e. non-production) — App threads that flag into `Login`. Prod shows Google only; previews show both.
- **Session check (≈685)** — `api('/api/login')` now yields `{role, email}`. **Fix the client-side fail-open while here:** line 685 is literally `setRole(d.role || 'admin')` — the same default-to-admin pattern this phase exists to kill. Change to `setRole(d.role)` (server always returns `role` now). Capture `password_login` from the 401 catch path for the Login component.
- Optional: show the signed-in email in the header (`Header`, ≈613) next to Log out.

---

## Tests (`scripts/test_web_api.py`)

There are currently **no login/auth_helper tests** — add a `# === auth_helper.py / login / callback ===` section:
- `make_token`/`verify_token` round-trip carries `email`; tampered sig → `None`; expired → `None`; **legacy `{exp, role}`-only token (no `email` key) → `None`** (pins decision 3 — this is exactly why `verify_token` requires the `email` key, not just `role`).
- **Password-minted token (`email=None`) still verifies** — pins the key-presence-not-truthiness rule; without this test the legacy-rejection change silently breaks preview logins.
- `verify_token` on a token with no `role` → `None` (pins the fail-open removal).
- `make_state`/`verify_state` round-trip; tampered/expired state → falsy (pins CSRF).
- `login do_GET ?provider=google` → 302 with a Location containing `accounts.google.com`, our `client_id`, the redirect URI, and a `state` param.
- `login do_POST` password path → **403 when `VERCEL_ENV=production`**, 200+cookie otherwise (pins decision 2). **Save/restore `VERCEL_ENV`** — the suite is one process; leaking it 403s every later password test.
- Bare `GET /api/login` unauthenticated → 401 body includes `password_login` (true when non-prod, false when prod).
- `callback`: valid `state` + stubbed token exchange returning an `id_token` for `nlovejoy@me.com` (`email_verified:true`, correct `aud`) → 302 + admin cookie; unknown email → 403; `email_verified:false` → 403; wrong `aud` → 403; bad `state` → 400; `?error=access_denied` → readable 4xx, no crash. (Stub the `urllib` token POST via `patch`.)
- Update the two `os.environ.setdefault("AUTH_SECRET", ...)` sites (760, 819) if the new token shape needs it — they're beacon tests, likely untouched.

Run: `.venv/bin/python scripts/test_web_api.py` — must stay green.

---

## Deploy / cutover sequence

1. Land code + tests (PR). All unit tests green **without** live Google creds.
2. Nico does the prep (Google Cloud client, 1P, Vercel `GOOGLE_CLIENT_ID`/`_SECRET`/`ADMIN_EMAILS` Production).
3. `cd web && vercel --prod`.
4. **Live verify** (self-contained, see below).
5. §2.3 cleanup after verify: password path already prod-gated; delete `AUTH_READ_SECRET` from Vercel (verified: only `login.py:23` reads it — **note this also kills preview *reader* login; previews become admin-password-only**, consistent with decision 1), remove the `BEACON_SALT`→`AUTH_SECRET` fallback in `beacon.py`, **set Preview/Dev `BEACON_SALT`** (still unset — see CLAUDE.md §2.0 note). `AUTH_SECRET` is **demoted, not retired**: post-cutover it remains the HMAC token-signing key everywhere and the break-glass password in preview. Rotating it invalidates all cookies and in-flight `state` tokens.
6. §2.4 docs sweep: `.env.tpl`, `README.md:85`, `docs/data-and-access.md:37,42`, `CLAUDE.md:19`, roadmap STATE OF PLAY.

---

## Live verification (fill in after deploy)

1. Open `https://prompt-labs.org` in a logged-out browser → should show "Sign in with Google", no password box.
2. Click it → Google consent → back to `https://prompt-labs.org` logged in as admin. **Pass:** dashboard loads, Ask button visible (admin-only).
3. `GET https://prompt-labs.org/api/login` (DevTools/curl with the cookie) returns `{authenticated:true, role:"admin", email:"nlovejoy@me.com"}`.
4. Sign out → cookie cleared, back to login.
5. A non-`ADMIN_EMAILS` Google account → readable 403, not a blank page, not admin.

---

## Landmines (from roadmap, restated so they're not missed)

- `AUTH_SECRET` triple-overload: password (`login.py:22`), token-signing (`auth_helper.py:16`), beacon salt (`beacon.py:73`). §2.0 split the beacon salt out already, so touching `AUTH_SECRET` here no longer moves visitor hashes. Do **not** reintroduce a beacon dependency.
- `SameSite=Strict` → `Lax` is load-bearing for the callback redirect. Miss it and the cookie silently drops after Google bounces back.
- `verify_token`'s fail-open `role="admin"` default must not survive into an identity token — and neither may `index.html:685`'s client-side twin (`d.role || 'admin'`).
- **Legacy rejection hinges on requiring the `email` KEY, not just `role`** — legacy cookies have `role`. And key-presence, not truthiness, or preview password cookies (`email: null`) break.
- `state` helpers live in `auth_helper.py`, not a new module — or `vercel.json` `includeFiles` needs editing.
- Roadmap §2.1's line refs are stale (`index.html:663`; "do_POST becomes the initiate") — this plan supersedes; sweep the roadmap in §2.4 so the two don't fight.
- `vercel env add` traps: one call per var, no newline-strip, no loop, verify with `vercel env ls` (roadmap §0.1).
