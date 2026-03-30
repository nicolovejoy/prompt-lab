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


def make_token(role="admin"):
    """Create a signed, time-limited auth token with role."""
    secret = _secret()
    payload = json.dumps({"exp": int(time.time()) + MAX_AGE, "role": role})
    data = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def verify_token(token):
    """Verify token signature and expiry. Returns role or None."""
    secret = _secret()
    if not secret or "." not in token:
        return None
    data, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(data))
        if payload["exp"] <= time.time():
            return None
        return payload.get("role", "admin")
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
    return verify_token(token)


def set_cookie_header(role="admin"):
    """Return Set-Cookie header value for a new auth token."""
    token = make_token(role)
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
