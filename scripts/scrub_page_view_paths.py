"""Scrub ID-like path segments from already-stored `page_views` rows.

The beacon endpoint applies `scrub_path` before storing; this applies the same
function to rows written before that change. `page_views` is cloud-direct
(Turso only). Dry run by default: prints each `old -> new` with its row count
and writes nothing. Pass --apply to run the UPDATEs. Prints paths only.

Run: .venv/bin/python scripts/scrub_page_view_paths.py [--apply]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from beacon_helper import scrub_path  # noqa: E402
from turso_helper import turso_query  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="run the UPDATEs (default is a dry run)")
    args = parser.parse_args(argv)

    rows = turso_query(
        "SELECT path, COUNT(*) AS n FROM page_views GROUP BY path"
    )
    changes = []
    for r in rows:
        old = r["path"]
        new = scrub_path(old)
        if new != old:
            changes.append((old, new, int(r["n"])))

    for old, new, n in changes:
        print(f"{old} -> {new}  ({n} rows)")
    print(f"{len(changes)} paths change, {sum(c[2] for c in changes)} rows total")

    if not args.apply:
        print("Dry run: nothing written. Re-run with --apply to update.")
        return
    for old, new, _ in changes:
        turso_query("UPDATE page_views SET path = ? WHERE path = ?", [new, old])
    print(f"Applied: {len(changes)} UPDATEs.")


if __name__ == "__main__":
    from claude_api import load_env

    load_env()
    main()
