"""One-time backfill: detect each project's GitHub URL from its local clone
under ~/src and write it to the `projects` table.

Used to run inline in /handoff on every session — but the URL almost never
changes, so the per-session upsert was pure overhead (and the schema-drift
culprit that motivated the move). Re-run this when:
  - a new project is added under ~/src
  - a remote URL is renamed
  - the projects table is rebuilt

Usage:
  python scripts/backfill_project_urls.py            # scan ~/src/*
  python scripts/backfill_project_urls.py <path>     # one specific project dir
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store


def detect_url(project_dir: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:") :]
    if url.endswith(".git"):
        url = url[:-4]
    return url if "github.com" in url else None


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        targets = [Path(argv[1]).expanduser().resolve()]
    else:
        src = Path.home() / "src"
        targets = sorted(p for p in src.iterdir() if p.is_dir() and (p / ".git").exists())

    s = get_store()
    s.migrate()
    saved = skipped = 0
    for proj_dir in targets:
        name = proj_dir.name
        url = detect_url(proj_dir)
        if not url:
            print(f"  skip {name}: no GitHub origin")
            skipped += 1
            continue
        s.update_project(name, github_url=url)
        print(f"  ok   {name}: {url}")
        saved += 1
    s.close()
    print(f"\n{saved} saved, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
