#!/usr/bin/env python3
"""One-time backfill: populate github_url for projects from git remotes.

Walks ~/src/<project> directories and extracts the GitHub remote URL.
Also sets site_url for known deployed projects.

Usage:
  python backfill_project_urls.py              # populate all
  python backfill_project_urls.py --dry-run    # show what would be set
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from store import get_store

SRC_DIR = Path.home() / "src"

# Known site URLs (manual mapping)
KNOWN_SITES = {
    "prompt-lab": "https://anomatom.com",
    "freevite": "https://freevite.app",
}


def get_github_url(project_dir: Path) -> str | None:
    """Extract GitHub URL from git remote, normalized to https."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_dir, capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        # Convert SSH to HTTPS
        if url.startswith("git@github.com:"):
            url = "https://github.com/" + url[len("git@github.com:"):]
        if url.endswith(".git"):
            url = url[:-4]
        if "github.com" in url:
            return url
        return None
    except Exception:
        return None


def main():
    dry_run = "--dry-run" in sys.argv
    store = get_store()
    store.migrate()

    projects = store.get_all_project_names()
    updated = 0

    for name in sorted(projects):
        project_dir = SRC_DIR / name
        if not project_dir.is_dir():
            continue

        github_url = get_github_url(project_dir)
        site_url = KNOWN_SITES.get(name)

        if github_url or site_url:
            fields = {}
            if github_url:
                fields["github_url"] = github_url
            if site_url:
                fields["site_url"] = site_url

            if dry_run:
                print(f"  {name}: {fields}")
            else:
                store.update_project(name, **fields)
                print(f"  {name}: {fields}")
            updated += 1

    store.close()
    action = "would update" if dry_run else "updated"
    print(f"\n{action} {updated} projects")


if __name__ == "__main__":
    main()
