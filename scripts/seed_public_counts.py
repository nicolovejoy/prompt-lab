"""Seed project_metadata.public_counts — opt projects into the read-time counts
projection served by /api/public_history (the selected-projects sparkline feed).

Dry-run by default; pass --apply to write. Alias-folds each name to its canonical
before upserting so a renamed project can't grow a second row.

public_counts is a real gate (unlike the cosmetic `private` flag): when set,
/api/public_history projects that project's weekly session/commit counts (numeric
columns only, never prose) from the private weekly_rollups table at read time.

Seed set (bundled decisions, handoff 2026-07-20): the current public allowlist
minus am-i-an-ai (site removed lojong), plus split-recording (opted in for counts
only — its prose stays a separate manifest decision).

Run: .venv/bin/python scripts/seed_public_counts.py           # dry-run
     .venv/bin/python scripts/seed_public_counts.py --apply
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from claude_api import load_env  # noqa: E402

load_env()

from turso_helper import resolve_project_names, turso_query  # noqa: E402

SEED = [
    "ibuild4you",
    "musicforge",
    "prntd",
    "prompt-lab",
    "selected-projects",
    "showcase",
    "split-recording",
]


def main():
    apply = "--apply" in sys.argv
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for name in SEED:
        canonical = resolve_project_names(name)[0]
        existing = turso_query(
            "SELECT public_counts FROM project_metadata WHERE project = ?",
            [canonical])
        cur = int(existing[0]["public_counts"] or 0) if existing else 0
        if cur == 1:
            print(f"  ok   {canonical} (already opted in)")
            continue
        if not apply:
            print(f"  WOULD SET public_counts=1  {canonical}")
            continue
        turso_query(
            "INSERT INTO project_metadata (project, public_counts, updated_at) "
            "VALUES (?, 1, ?) "
            "ON CONFLICT(project) DO UPDATE SET public_counts=1, updated_at=?",
            [canonical, now, now])
        print(f"  SET  public_counts=1  {canonical}")

    if not apply:
        print("\nDry run. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
