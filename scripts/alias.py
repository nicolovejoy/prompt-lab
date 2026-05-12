"""Manage project_aliases in the local SQLite store.

Aliases let a single project be queried under multiple names without
mutating any data rows. Reads expand the requested name into
[canonical, *aliases] and emit `WHERE project IN (...)`. Writes (e.g., the
prompt-log hook) keep using whatever name they were given; the alias layer
folds them at read time.

Usage:
  python scripts/alias.py list
  python scripts/alias.py add <alias> <canonical>
  python scripts/alias.py rm  <alias>
  python scripts/alias.py check <alias-or-canonical>

After `add` or `rm`, run `python sync_to_turso.py` to propagate to the cloud
dashboard. Until then, only the local dashboard reflects the change.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store

# Tables with a `project` column that we report on in `check`.
# (`commits` is joined via prompts/sessions and has no project column of its own.)
PROJECT_TABLES = [
    "prompts",
    "sessions",
    "daily_summaries",
    "weekly_rollups",
    "intentions",
    "project_snapshots",
    "public_session_summaries",
    "public_weekly_rollups",
    "synthesis_log",
]


def cmd_list(store) -> int:
    rows = store._conn.execute(
        "SELECT alias, canonical FROM project_aliases ORDER BY canonical, alias"
    ).fetchall()
    if not rows:
        print("(no aliases)")
        return 0
    width = max(len(r["alias"]) for r in rows)
    for r in rows:
        print(f"  {r['alias']:<{width}}  →  {r['canonical']}")
    return 0


def cmd_add(store, alias: str, canonical: str) -> int:
    if alias == canonical:
        print(f"refusing: alias and canonical are the same ({alias!r})")
        return 2

    # Reject chains: canonical must not itself be an alias.
    chain_row = store._conn.execute(
        "SELECT canonical FROM project_aliases WHERE alias = ?", (canonical,)
    ).fetchone()
    if chain_row:
        print(
            f"refusing: {canonical!r} is itself an alias for "
            f"{chain_row['canonical']!r} — alias chains are not allowed. "
            f"Use that as the canonical instead."
        )
        return 2

    # Warn if the alias is already a canonical (rows currently point at it).
    canon_row = store._conn.execute(
        "SELECT 1 FROM project_aliases WHERE canonical = ? LIMIT 1", (alias,)
    ).fetchone()
    if canon_row:
        print(
            f"refusing: {alias!r} is currently the canonical for other aliases. "
            f"Re-canonicalizing would require updating those rows first."
        )
        return 2

    store._conn.execute(
        "INSERT OR REPLACE INTO project_aliases (alias, canonical) VALUES (?, ?)",
        (alias, canonical),
    )
    store._conn.commit()
    store.invalidate_alias_cache()
    print(f"added: {alias} → {canonical}")
    print("run `python sync_to_turso.py` to propagate to the cloud dashboard.")
    return 0


def cmd_rm(store, alias: str) -> int:
    cur = store._conn.execute(
        "DELETE FROM project_aliases WHERE alias = ?", (alias,)
    )
    store._conn.commit()
    store.invalidate_alias_cache()
    if cur.rowcount == 0:
        print(f"no alias {alias!r}")
        return 1
    print(f"removed: {alias}")
    print("run `python sync_to_turso.py` to propagate to the cloud dashboard. "
          "Note: sync_to_turso currently does INSERT OR REPLACE only; "
          "you may need to delete the Turso row manually.")
    return 0


def cmd_check(store, name: str) -> int:
    names = store.expand_project(name)
    canonical = names[0]
    aliases = names[1:]
    print(f"canonical: {canonical}")
    if aliases:
        print(f"aliases:   {', '.join(aliases)}")
    else:
        print("aliases:   (none)")
    print()
    print(f"{'table':<28} {'canonical':>10}  " + "  ".join(f"{a:>10}" for a in aliases))
    for tbl in PROJECT_TABLES:
        try:
            counts = []
            for n in names:
                row = store._conn.execute(
                    f"SELECT COUNT(*) AS n FROM {tbl} WHERE project = ?", (n,)
                ).fetchone()
                counts.append(row["n"])
            print(f"{tbl:<28} " + "  ".join(f"{c:>10}" for c in counts))
        except Exception as e:
            print(f"{tbl:<28} (skipped: {e})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    store = get_store()
    try:
        if cmd == "list":
            return cmd_list(store)
        if cmd == "add" and len(argv) == 4:
            return cmd_add(store, argv[2], argv[3])
        if cmd == "rm" and len(argv) == 3:
            return cmd_rm(store, argv[2])
        if cmd == "check" and len(argv) == 3:
            return cmd_check(store, argv[2])
        print(__doc__)
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
