#!/usr/bin/env python3
"""Local dev server for the mobile PWA. Serves static files + endpoints:
  /config — Turso credentials from .env (auto-configures the PWA)
  /ask    — proxies natural language questions to Claude via the Anthropic API
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claude_api import OPUS, load_env

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
            has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
            self._json_response({"url": url, "token": token, "ask_enabled": has_api})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/ask":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = body.get("question", "")
            context = body.get("context", "")

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                self._json_response({"error": "ANTHROPIC_API_KEY not set"}, 500)
                return

            try:
                from anthropic import Anthropic
                client = Anthropic()
                resp = client.messages.create(
                    model=OPUS,
                    max_tokens=1024,
                    system="You answer questions about a developer's work history. "
                           "Be concise and specific — cite dates and project names. "
                           "The data below comes from their knowledge store.",
                    messages=[{"role": "user", "content": f"Question: {question}\n\n{context}"}],
                )
                answer = resp.content[0].text
                self._json_response({"answer": answer})
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Mobile PWA: http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
