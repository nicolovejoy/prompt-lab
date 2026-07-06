"""Pre-warm / refresh the issue-type classification cache on Turso.

Fetches every open issue across owned repos (via the `gh` CLI — no token
handling here), classifies any that aren't already cached with a matching
title (one batched Claude call), and upserts into the `issue_categories`
Turso table that web/api/todos.py reads for its "by type" view.

Idempotent + incremental: re-running only classifies new/changed issues.
Pass --all to force reclassification of everything.

Run: .venv/bin/python scripts/classify_issues.py [--all]
"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from claude_api import load_env  # noqa: E402

load_env()

import os  # noqa: E402
from turso_helper import turso_query  # noqa: E402
from classify_helper import classify_batch, issue_key  # noqa: E402

FORCE = "--all" in sys.argv

TABLE = """CREATE TABLE IF NOT EXISTS issue_categories (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    category TEXT NOT NULL,
    classified_at TEXT,
    PRIMARY KEY (repo, number)
)"""


def fetch_issues():
    out = subprocess.run(
        ["gh", "search", "issues", "--owner", os.environ.get("GITHUB_USER", "nicolovejoy"),
         "--state", "open", "--limit", "300", "--json", "title,number,labels,repository"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = json.loads(out)
    issues = []
    for r in rows:
        issues.append({
            "repo": r["repository"]["name"],
            "number": r["number"],
            "title": r["title"],
            "labels": [l["name"] for l in r.get("labels", [])],
        })
    return issues


def main():
    turso_query(TABLE)
    issues = fetch_issues()
    print(f"fetched {len(issues)} open issues")

    cached = {}
    for row in turso_query("SELECT repo, number, title FROM issue_categories"):
        cached[(row["repo"], int(row["number"]))] = row["title"]

    if FORCE:
        todo = issues
    else:
        todo = [i for i in issues
                if cached.get((i["repo"], i["number"])) != i["title"]]
    print(f"{len(todo)} need classification ({len(issues) - len(todo)} already cached)")
    if not todo:
        return

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Batch in chunks so a single call never gets unwieldy.
    CHUNK = 60
    counts = {}
    for start in range(0, len(todo), CHUNK):
        chunk = todo[start:start + CHUNK]
        cats = classify_batch(chunk)
        for i in chunk:
            cat = cats.get(issue_key(i["repo"], i["number"]), "other")
            counts[cat] = counts.get(cat, 0) + 1
            turso_query(
                "INSERT INTO issue_categories (repo, number, title, category, classified_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(repo, number) DO UPDATE SET "
                "title=excluded.title, category=excluded.category, classified_at=excluded.classified_at",
                [i["repo"], i["number"], i["title"], cat, now],
            )
        print(f"  classified {min(start + CHUNK, len(todo))}/{len(todo)}")

    print("category counts (this run):", dict(sorted(counts.items(), key=lambda x: -x[1])))
    total = turso_query("SELECT COUNT(*) n FROM issue_categories")[0]["n"]
    print(f"issue_categories now holds {total} rows")


if __name__ == "__main__":
    main()
