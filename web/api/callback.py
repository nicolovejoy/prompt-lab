"""GET /api/callback — Google OAuth redirect handler.

Confidential client: the code is exchanged server-side, so the id_token arrives
over TLS direct from Google and needs NO signature verification (settled
decision, docs/phase2-oauth-plan.md). urllib only, no new deps."""

import base64
import html
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

from auth_helper import REDIRECT_URI, set_cookie_header, verify_state

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _exchange_code(code):
    """POST the auth code to Google's token endpoint, return parsed JSON.
    Module-level so tests can patch it."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _decode_id_token(id_token):
    """Base64url-decode the JWT payload (claims). No signature check — see the
    module docstring. JWT segments are unpadded base64url; pad or the decode
    throws."""
    seg = id_token.split(".")[1]
    seg += "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        # Google's error redirect (e.g. user cancels) arrives with no code.
        if query.get("error"):
            return self._error(
                400, f"Google sign-in was cancelled or failed: {query['error'][0]}.")

        # Verify state BEFORE touching the code (CSRF gate).
        state = query.get("state", [None])[0]
        if not state or not verify_state(state):
            return self._error(
                400, "Invalid or expired sign-in state. Please try signing in again.")

        code = query.get("code", [None])[0]
        if not code:
            return self._error(400, "Missing authorization code.")

        try:
            tokens = _exchange_code(code)
        except Exception:
            return self._error(502, "Could not reach Google's token endpoint.")

        id_token = (tokens or {}).get("id_token")
        if not id_token:
            return self._error(502, "Google did not return an id_token.")

        try:
            claims = _decode_id_token(id_token)
        except Exception:
            return self._error(400, "Could not read the Google id_token.")

        if claims.get("aud") != os.environ.get("GOOGLE_CLIENT_ID"):
            return self._error(403, "This sign-in was issued for a different application.")

        if claims.get("email_verified") is not True:
            return self._error(403, "Your Google email address is not verified.")

        email = (claims.get("email") or "").strip()
        admins = [
            e.strip().lower()
            for e in os.environ.get("ADMIN_EMAILS", "").split(",")
            if e.strip()
        ]
        if not email or email.lower() not in admins:
            return self._error(
                403, f"{email or 'This account'} is not authorized to access "
                     "this dashboard.")

        self.send_response(302)
        self.send_header("Set-Cookie", set_cookie_header("admin", email))
        self.send_header("Location", "/")  # fixed target — no open-redirect surface
        self.end_headers()

    def _error(self, status, message):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        # message can carry request-derived text (?error=, email) — escape it.
        self.wfile.write(
            f"<h1>Sign-in failed</h1><p>{html.escape(message)}</p>".encode())
