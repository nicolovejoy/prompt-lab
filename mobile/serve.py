#!/usr/bin/env python3
"""Local dev server for the mobile PWA. Serves static files + /config endpoint
that reads Turso credentials from .env so you don't have to paste them."""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_api import load_env

load_env()

MOBILE_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MOBILE_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/config":
            url = os.environ.get("TURSO_DATABASE_URL", "")
            token = os.environ.get("TURSO_AUTH_TOKEN", "")
            if url.startswith("libsql://"):
                url = "https://" + url[len("libsql://"):]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"url": url, "token": token}).encode())
        else:
            super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Mobile PWA: http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
