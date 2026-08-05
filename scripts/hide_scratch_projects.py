#!/usr/bin/env python3
"""Mark non-project directory names as private so the dashboard stops listing them.

The prompt-log hook used to derive a project name from the cwd basename, so every
directory ever worked in minted a "project": `src`, `web`, `public`, `utils`,
`mockups` are subdirectories of real repos, and `tmp`, `backup`, `.claude` are not
repos at all. That left an 80-name project list where most names were noise.

`log-prompt.sh` now resolves the cwd to its git repo (and buckets non-repo work
under `scratch`), so no NEW names of this kind appear. This script cleans up the
ones already recorded.

It sets `private = 1`, which is the cosmetic hide-toggle from #23 — a muted,
hidden treatment in the UI. It deliberately does NOT delete rows: the prompt
history stays queryable, and un-hiding is a one-word edit. `private` is not a
privacy gate and does not gate any API; see docs/data-and-access.md.

Writes go straight to Turso. `project_metadata` is cloud-direct by design and
must never gain a leg in sync_to_turso.py — that absence is what makes drift
between the two stores structurally impossible.

Usage:
  python scripts/hide_scratch_projects.py           # dry run, prints the plan
  python scripts/hide_scratch_projects.py --apply
  python scripts/hide_scratch_projects.py --unhide <name> [<name> ...] --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_api import load_env  # noqa: E402

load_env()

from web.turso_helper import turso_query  # noqa: E402

# Directory names that were never projects. Two kinds, both noise:
# subdirectories of real repos, and directories that aren't repos at all.
SCRATCH_NAMES = [
    # subdirectories of real repos
    "web",
    "src",
    "public",
    "projects",
    "utils",
    "infrastructure",
    "mockups",
    "reports",
    "Include",
    "TeX",
    "Wrappers",
    "bootstrap",
    # not repos at all
    "tmp",
    "tmp_lotus_land_poker",
    "backup",
    ".claude",
    "nico",
    "pi",
    "clicks",
    # throwaway branches and agent worktrees
    "rebase-b1",
    "agent-a3af86ee5636b49cc",
    "agent-a7bd32b71c9a4036d",
    # the bucket the hook now uses for all non-repo work, hidden pre-emptively
    # so it never shows up in the picker in the first place
    "scratch",
]


def current_private() -> dict[str, str]:
    rows = turso_query("SELECT project, private FROM project_metadata")
    return {r["project"]: str(r["private"]) for r in rows}


def set_private(project: str, value: int) -> None:
    # Mirrors web/api/project_metadata.py: upsert that never resets a sibling
    # field. A project with no row yet gets one; an existing row keeps its
    # category/status/public_counts untouched.
    turso_query(
        """INSERT INTO project_metadata (project, private, updated_at)
           VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
           ON CONFLICT(project) DO UPDATE SET
             private = excluded.private,
             updated_at = excluded.updated_at""",
        [project, str(value)],
    )


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    unhide: list[str] = []
    if "--unhide" in args:
        i = args.index("--unhide")
        unhide = [a for a in args[i + 1 :] if not a.startswith("--")]

    targets = [(n, 0) for n in unhide] if unhide else [(n, 1) for n in SCRATCH_NAMES]
    verb, past = ("unhide", "unhidden") if unhide else ("hide", "hidden")

    existing = current_private()
    todo = [(n, v) for n, v in targets if existing.get(n) != str(v)]
    skip = [n for n, v in targets if existing.get(n) == str(v)]

    if skip:
        print(f"already {past} ({len(skip)}): {', '.join(sorted(skip))}")
    if not todo:
        print("nothing to do.")
        return 0

    print(f"\nwill {verb} {len(todo)}:")
    for n, _ in todo:
        print(f"  {n}")

    if not apply:
        print("\ndry run — re-run with --apply to write.")
        return 0

    for n, v in todo:
        set_private(n, v)
    print(f"\n{past} {len(todo)} project(s) in Turso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
