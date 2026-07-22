"""GET  /api/login              — session check (returns role + email)
   GET  /api/login?provider=google — 302 to Google's OAuth authorize URL
   POST /api/login              — verify password, set cookie (non-prod only)
   DELETE /api/login            — clear auth cookie (logout)."""

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse

from auth_helper import (
    REDIRECT_URI,
    clear_cookie_header,
    get_identity,
    make_state,
    set_cookie_header,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if query.get("provider", [None])[0] == "google":
            params = urlencode({
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "openid email",
                "state": make_state(),
            })
            self.send_response(302)
            self.send_header("Location", f"{GOOGLE_AUTH_URL}?{params}")
            self.end_headers()
            return

        # Bare GET: session check. index.html depends on this contract.
        ident = get_identity(self.headers)
        if ident:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "authenticated": True,
                "role": ident["role"],
                "email": ident.get("email"),
            }).encode())
        else:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            is_production = os.environ.get("VERCEL_ENV") == "production"
            self.wfile.write(json.dumps({
                "authenticated": False,
                # Frontend renders the password form only off-production.
                "password_login": not is_production,
                # Frontend renders the Google button only on production — the
                # OAuth redirect URI is pinned to prod, so on a preview it
                # would sign you into prod instead (issue #30).
                "google_login": is_production,
            }).encode())

    def do_POST(self):
        # Password login is preview/dev break-glass only; disabled in prod.
        if os.environ.get("VERCEL_ENV") == "production":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"error": "password login is disabled in production"}).encode())
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        password = body.get("password", "")
        admin_secret = os.environ.get("AUTH_SECRET", "")
        read_secret = os.environ.get("AUTH_READ_SECRET", "")

        # Check admin password first, then reader password
        role = None
        if admin_secret and hmac.compare_digest(password, admin_secret):
            role = "admin"
        elif read_secret and hmac.compare_digest(password, read_secret):
            role = "reader"

        if not role:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "wrong password"}).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", set_cookie_header(role, email=None))
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "role": role}).encode())

    def do_DELETE(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", clear_cookie_header())
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())
