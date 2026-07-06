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
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from auth_helper import get_role, is_authenticated
from classify_helper import classify_batch, issue_key
from turso_helper import turso_query

# Cap live classifications per request so the serverless function never blocks
# on a huge first batch. The cache is normally pre-warmed by
# scripts/classify_issues.py, so live requests classify only brand-new issues.
LIVE_CLASSIFY_CAP = 40

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
                "repo": repo,
                "url": it.get("html_url"),
                "labels": [lb.get("name") for lb in it.get("labels", [])],
                "comments": it.get("comments", 0),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
            })

        total = sum(len(v) for v in projects.values())
        payload = {"configured": True, "projects": projects, "total": total}

        params = parse_qs(urlparse(self.path).query)
        if params.get("categorize", ["0"])[0] in ("1", "true"):
            force = params.get("recategorize", ["0"])[0] in ("1", "true")
            may_classify = get_role(self.headers) == "admin" and bool(
                os.environ.get("ANTHROPIC_API_KEY"))
            payload.update(self._categorize(projects, force, may_classify))

        self._send(200, payload)

    def _categorize(self, projects, force, may_classify):
        """Attach a `category` (type of work) to every issue, reading the
        Turso cache first and classifying only the stragglers (capped). Every
        issue ends up with a category — pending ones become 'uncategorized'.
        """
        all_issues = [iss for issues in projects.values() for iss in issues]

        try:
            rows = turso_query(
                "SELECT repo, number, title, category FROM issue_categories")
        except Exception:
            rows = []
        cache = {(r["repo"], int(r["number"])): (r.get("title"), r["category"])
                 for r in rows}

        need = []
        for iss in all_issues:
            hit = cache.get((iss["repo"], iss["number"]))
            if hit and hit[0] == iss["title"] and not force:
                iss["category"] = hit[1]
            else:
                iss["category"] = None
                need.append(iss)

        classified_now = 0
        if need and may_classify:
            batch = need[:LIVE_CLASSIFY_CAP]
            cats = classify_batch([
                {"repo": i["repo"], "number": i["number"],
                 "title": i["title"], "labels": i.get("labels", [])}
                for i in batch])
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for iss in batch:
                cat = cats.get(issue_key(iss["repo"], iss["number"]), "other")
                iss["category"] = cat
                classified_now += 1
                try:
                    turso_query(
                        "INSERT INTO issue_categories "
                        "(repo, number, title, category, classified_at) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(repo, number) DO UPDATE SET "
                        "title=excluded.title, category=excluded.category, "
                        "classified_at=excluded.classified_at",
                        [iss["repo"], iss["number"], iss["title"], cat, now])
                except Exception:
                    pass

        pending = 0
        for iss in all_issues:
            if not iss.get("category"):
                iss["category"] = "uncategorized"
                pending += 1

        return {"categorized": True, "classified_now": classified_now,
                "pending": pending}

    def _send(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
