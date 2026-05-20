# Prompt Lab — 1Password secret template
# Generate .env.local with: op inject -i .env.tpl -o .env.local

# Required for nightly synthesis (synthesizer.py) and review emails (send-review.py)
ANTHROPIC_API_KEY=op://dev-secrets/prompt-lab-key-1/credential
ANTHROPIC_ADMIN_KEY=op://dev-secrets/admin-cost-tracking-2026-05/credential


# Required for review emails only
RESEND_API_KEY=op://dev-secrets/Resend/api-key
REVIEW_FROM_EMAIL=reviews@send.anomatom.com
REVIEW_TO_EMAIL=nlovejoy@me.com

# Turso remote sync (cloud dashboard and mobile access)
TURSO_DATABASE_URL=op://dev-secrets/Turso/url
TURSO_AUTH_TOKEN=op://dev-secrets/Turso/token

# Cloud dashboard auth
AUTH_SECRET=op://dev-secrets/Prompt Lab Auth/secret
