# Prompt Lab — 1Password secret template
# Generate .env.local with: op inject -i .env.tpl -o .env.local

# Required for nightly synthesis (synthesizer.py) and review emails (send-review.py)
ANTHROPIC_API_KEY=op://dev-secrets/prompt-lab-key-1/credential
ANTHROPIC_ADMIN_KEY=op://dev-secrets/admin-cost-tracking-2026-05/credential


# Required for review emails only
RESEND_API_KEY=op://dev-secrets/Resend/api-key
REVIEW_FROM_EMAIL=reviews@send.prompt-labs.org
REVIEW_TO_EMAIL=nlovejoy@me.com

# Turso remote sync (cloud dashboard and mobile access)
TURSO_DATABASE_URL=op://dev-secrets/Turso/url
TURSO_AUTH_TOKEN=op://dev-secrets/Turso/token

# Cloud dashboard auth. Prod is Google-exclusive (see GOOGLE_*/ADMIN_EMAILS/
# READER_EMAILS below); AUTH_SECRET is demoted, not retired — it's still the
# HMAC token-signing key everywhere (auth_helper.py) AND the preview-only
# password login (login.py do_POST is 403'd in production). AUTH_READ_SECRET
# (the old reader password) has been deleted from Vercel — that also retired
# preview password *reader* login; previews are admin-password-only now.
AUTH_SECRET=op://dev-secrets/Prompt Lab Auth/secret

# Beacon visitor-hash salt (web/api/beacon.py). Decoupled from AUTH_SECRET
# (§2.0/§2.3) — no fallback, BEACON_SALT unset drops the hit rather than
# borrow another secret. Must be set in every environment (Production,
# Preview, Development) in the Vercel project env.
BEACON_SALT=op://dev-secrets/Prompt Lab Auth/secret

# Google OAuth (web/api/login.py + callback.py) — prod-exclusive login.
# Vercel: Production only (previews can't do the OAuth round-trip — Google
# won't register a wildcard *.vercel.app redirect URI — so previews keep the
# password path; see AUTH_SECRET above and issue #30).
GOOGLE_CLIENT_ID=op://dev-secrets/Prompt Lab Google OAuth/client_id
GOOGLE_CLIENT_SECRET=op://dev-secrets/Prompt Lab Google OAuth/client_secret
# email->role allowlists, not secrets; comma-separated, case-insensitive,
# admin wins on overlap. Vercel Production only — callback.py is their sole
# reader and previews never serve the OAuth callback.
ADMIN_EMAILS=nlovejoy@me.com
# Read-only dashboard access (no Ask, no metadata edits).
READER_EMAILS=elovejoy5@gmail.com

# Cross-project Todos page: read-only PAT for open-issue search (web/api/todos.py).
# Also set this in the Vercel project env. GITHUB_USER defaults to nicolovejoy.
GITHUB_TOKEN=op://dev-secrets/prompt-lab-github-pat/credential
