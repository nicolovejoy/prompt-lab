"""GET /api/todos — open GitHub issues across all repos you own, as a
cross-project todo list.

One authenticated GitHub Search call returns every open issue in repos owned by
GITHUB_USER; we group them by repo (folded through the project alias map so a
renamed repo lands under its canonical project name) and return
{project: [issue, ...]}. No local scan, no Turso table — always fresh.

Env:
  GITHUB_TOKEN  fine-grained or classic PAT with read access to issues. When
                absent the endpoint returns {"configured": false} so the page
                can prompt to set it instead of erroring.
  GITHUB_USER   repo owner to scope the search to. Default: nicolovejoy.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

from auth_helper import is_authenticated
from turso_helper import turso_query

GITHUB_API = "https://api.github.com/search/issues"
DEFAULT_USER = "nicolovejoy"
MAX_PAGES = 3  # 100 issues/page — 300 open issues is plenty for a backlog.


def _alias_to_canonical():
    try:
        rows = turso_query("SELECT alias, canonical FROM project_aliases")
    except Exception:
        return {}
    return {r["alias"]: r["canonical"] for r in rows}


def _repo_name(item):
    # repository_url looks like https://api.github.com/repos/<owner>/<repo>
    url = item.get("repository_url", "")
    return url.rsplit("/", 1)[-1] if url else "unknown"


def _fetch_open_issues(token, user):
    q = f"is:open is:issue user:{user}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "prompt-lab-dashboard",
    }
    items = []
    for page in range(1, MAX_PAGES + 1):
        params = urllib.parse.urlencode(
            {"q": q, "per_page": 100, "page": page, "sort": "updated"})
        req = urllib.request.Request(f"{GITHUB_API}?{params}", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
        batch = body.get("items", [])
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not is_authenticated(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized"}).encode())
            return

        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            self._send(200, {"configured": False, "projects": {}, "total": 0})
            return

        user = os.environ.get("GITHUB_USER", DEFAULT_USER)
        try:
            items = _fetch_open_issues(token, user)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            self._send(502, {"error": f"GitHub HTTP {e.code}", "detail": detail})
            return
        except Exception as e:  # network / parse
            self._send(502, {"error": f"{type(e).__name__}: {e}"})
            return

        a2c = _alias_to_canonical()
        projects = {}
        for it in items:
            # search/issues returns PRs too unless filtered; is:issue handles it,
            # but guard anyway.
            if "pull_request" in it:
                continue
            repo = _repo_name(it)
            proj = a2c.get(repo, repo)
            projects.setdefault(proj, []).append({
                "title": it.get("title"),
                "number": it.get("number"),
                "url": it.get("html_url"),
                "labels": [lb.get("name") for lb in it.get("labels", [])],
                "comments": it.get("comments", 0),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
            })

        total = sum(len(v) for v in projects.values())
        self._send(200, {"configured": True, "projects": projects, "total": total})

    def _send(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
