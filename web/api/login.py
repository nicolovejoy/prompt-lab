"""POST /api/login — verify password, set auth cookie.
   DELETE /api/login — clear auth cookie (logout)."""

import json
import os
from http.server import BaseHTTPRequestHandler

from auth_helper import (
    clear_cookie_header,
    is_authenticated,
    set_cookie_header,
    unauthorized_response,
)

import hmac


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        password = body.get("password", "")
        secret = os.environ.get("AUTH_SECRET", "")

        if not secret or not hmac.compare_digest(password, secret):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "wrong password"}).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", set_cookie_header())
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def do_DELETE(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", clear_cookie_header())
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def do_GET(self):
        """Check if currently authenticated."""
        if is_authenticated(self.headers):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"authenticated": True}).encode())
        else:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"authenticated": False}).encode())
