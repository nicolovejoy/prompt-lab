"""Cookie-based auth for Vercel serverless functions."""

import base64
import hashlib
import hmac
import json
import os
import time
from http.cookies import SimpleCookie

COOKIE_NAME = "gc_session"
MAX_AGE = 30 * 86400  # 30 days


def _secret():
    return os.environ.get("AUTH_SECRET", "")


def make_token():
    """Create a signed, time-limited auth token."""
    secret = _secret()
    payload = json.dumps({"exp": int(time.time()) + MAX_AGE})
    data = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def verify_token(token):
    """Verify token signature and expiry."""
    secret = _secret()
    if not secret or "." not in token:
        return False
    data, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(data))
        return payload["exp"] > time.time()
    except Exception:
        return False


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
    return token and verify_token(token)


def set_cookie_header():
    """Return Set-Cookie header value for a new auth token."""
    token = make_token()
    parts = [
        f"{COOKIE_NAME}={token}",
        f"Max-Age={MAX_AGE}",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
    ]
    # Add Secure flag in production (HTTPS)
    if os.environ.get("VERCEL"):
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header():
    """Return Set-Cookie header value to clear the auth cookie."""
    return f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"


def unauthorized_response():
    """Return a 401 JSON response dict."""
    return {
        "statusCode": 401,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "unauthorized"}),
    }
