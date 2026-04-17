"""POST /api/ask — proxy natural language questions to Claude."""

import json
import os
from http.server import BaseHTTPRequestHandler

from auth_helper import get_role


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        role = get_role(self.headers)
        if not role:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return
        if role != "admin":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Ask requires admin access"}).encode())
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self._json({"error": "ANTHROPIC_API_KEY not configured"}, 500)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        question = body.get("question", "")
        context = body.get("context", "")

        if not question.strip():
            self._json({"error": "question is required"}, 400)
            return

        try:
            from anthropic import Anthropic

            client = Anthropic()
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=(
                    "You answer questions about a developer's work history. "
                    "Be concise and specific — cite dates and project names. "
                    "The data below comes from their knowledge store."
                ),
                messages=[
                    {"role": "user", "content": f"Question: {question}\n\n{context}"}
                ],
            )
            answer = resp.content[0].text
            self._json({"answer": answer})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
