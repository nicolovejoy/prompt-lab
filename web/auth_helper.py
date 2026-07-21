"""Cookie-based auth for Vercel serverless functions."""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from http.cookies import SimpleCookie

COOKIE_NAME = "gc_session"
MAX_AGE = 30 * 86400  # 30 days
STATE_MAX_AGE = 600  # 10 min — OAuth CSRF state window

# Shared by login.py + callback.py. Kept here (not a new module) so callback.py
# needs no extra vercel.json includeFiles entry — see docs/phase2-oauth-plan.md.
REDIRECT_URI = "https://prompt-labs.org/api/callback"


def _secret():
    return os.environ.get("AUTH_SECRET", "")


def _sign(payload):
    """urlsafe_b64(json).hexhmac, joined by a dot."""
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(_secret().encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def _unsign(token):
    """Verify signature, return the decoded payload dict or None."""
    secret = _secret()
    if not secret or not token or "." not in token:
        return None
    data, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(data))
    except Exception:
        return None


def make_token(role="admin", email=None):
    """Create a signed, time-limited auth token. The `email` key is ALWAYS
    present (null for password logins) — that's what distinguishes new-shape
    tokens from legacy {exp, role} cookies."""
    return _sign({"exp": int(time.time()) + MAX_AGE, "role": role, "email": email})


def verify_token(token):
    """Verify signature + expiry, return the full payload dict or None.
    Requires both `role` and `email` KEYS present (key-presence, not truthiness):
    drops the fail-open role default AND rejects legacy {exp, role} cookies."""
    payload = _unsign(token)
    if payload is None:
        return None
    try:
        if "role" not in payload or "email" not in payload:
            return None
        if payload["exp"] <= time.time():
            return None
        return payload
    except Exception:
        return None


def get_cookie(headers):
    """Extract gc_session cookie from request headers."""
    cookie_header = headers.get("cookie", "")
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    if COOKIE_NAME in cookie:
        return cookie[COOKIE_NAME].value
    return None


def is_authenticated(headers):
    """Check if request has a valid auth cookie."""
    token = get_cookie(headers)
    return verify_token(token) is not None if token else False


def get_role(headers):
    """Return the user's role ('admin' or 'reader'), or None if not authenticated."""
    token = get_cookie(headers)
    if not token:
        return None
    payload = verify_token(token)
    return payload["role"] if payload else None


def get_identity(headers):
    """Return the full auth payload dict (role + email), or None."""
    token = get_cookie(headers)
    if not token:
        return None
    return verify_token(token)


def make_state():
    """Signed CSRF state for the OAuth round-trip. Signed but deliberately NOT
    browser-bound (no state cookie) — accepted trade-off, see the plan doc."""
    return _sign({"exp": int(time.time()) + STATE_MAX_AGE, "nonce": uuid.uuid4().hex})


def verify_state(state):
    """Return the state payload dict if valid + unexpired, else None."""
    payload = _unsign(state)
    if payload is None:
        return None
    try:
        if payload["exp"] <= time.time():
            return None
        return payload
    except Exception:
        return None


def set_cookie_header(role="admin", email=None):
    """Return Set-Cookie header value for a new auth token."""
    token = make_token(role, email)
    parts = [
        f"{COOKIE_NAME}={token}",
        f"Max-Age={MAX_AGE}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",  # Lax, not Strict: Strict drops the cookie on the
        # cross-site-initiated top-level nav back from Google (see plan doc).
    ]
    # Add Secure flag in production (HTTPS)
    if os.environ.get("VERCEL"):
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header():
    """Return Set-Cookie header value to clear the auth cookie."""
    return f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"


def unauthorized_response():
    """Return a 401 JSON response dict."""
    return {
        "statusCode": 401,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "unauthorized"}),
    }
