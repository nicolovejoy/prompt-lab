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

# Cloud dashboard auth
AUTH_SECRET=op://dev-secrets/Prompt Lab Auth/secret

# Beacon visitor-hash salt (web/api/beacon.py). Same value as AUTH_SECRET on
# purpose — it pins the salt so retiring AUTH_SECRET in the Phase 2 OAuth
# migration doesn't rotate every visitor hash. Also set in the Vercel project env.
BEACON_SALT=op://dev-secrets/Prompt Lab Auth/secret

# Google OAuth (web/api/login.py + callback.py). 1P item does not exist yet —
# create it after minting the Google Cloud OAuth client (redirect URI
# https://prompt-labs.org/api/callback). Vercel: Production only (previews use
# the password path). ADMIN_EMAILS is not a secret; comma-separated,
# case-insensitive. Set it in Vercel Production + Preview.
GOOGLE_CLIENT_ID=op://dev-secrets/Prompt Lab Google OAuth/client_id
GOOGLE_CLIENT_SECRET=op://dev-secrets/Prompt Lab Google OAuth/client_secret
ADMIN_EMAILS=nlovejoy@me.com

# Cross-project Todos page: read-only PAT for open-issue search (web/api/todos.py).
# Also set this in the Vercel project env. GITHUB_USER defaults to nicolovejoy.
GITHUB_TOKEN=op://dev-secrets/prompt-lab-github-pat/credential
