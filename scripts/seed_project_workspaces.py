"""Seed project_workspaces with the known Anthropic workspace → project mappings.

Idempotent — re-running upserts the same rows. Run once after a fresh install
or any time a new workspace is provisioned in the Anthropic Console.

Add new mappings to MAPPINGS below; the workspace name comes from the Admin API
workspace list (GET /v1/organizations/workspaces) and is purely cosmetic in this
table. Project must match a canonical name already used elsewhere in the store.

Flags:
  --db PATH  seed this SQLite file instead of the store's default DB.
  --remap    after seeding, rewrite `project` on existing api_costs and
             api_usage rows whose workspace_id is mapped to a different
             project (rows are stamped at write time, so a corrected mapping
             does not touch history on its own). Local SQLite only. Afterwards
             run a full `python sync_to_turso.py` (no --days) so Turso picks up
             remapped rows older than the nightly 7-day window.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store
from store.sqlite_store import SqliteKnowledgeStore

MAPPINGS = [
    ("wrkspc_01KXeZDUFDNaEFR3hCe7Qe3q", "prompt-lab", "prompt-lab"),
    ("wrkspc_01VXCsaREpeooov3UNR3EMYK", "ibuild4you", "ibuild4you"),
    ("wrkspc_01SqVqpmijYCi5CixCFwUfej", "notemaxxing", "notemaxxing"),
    ("wrkspc_01YLFBLWB27KcaNTgmetB6SD", "musicForge", "musicforge"),
    ("wrkspc_017NDm4zWZQz8fZGf2sUCswn", "prntd", "prntd"),
    # Named "recountly" by the Admin API (checked 2026-11-03); recountly is an alias of raconte.
    ("wrkspc_01B8VSus5qTLtiE8YyzRBYuA", "recountly", "raconte"),
    ("wrkspc_01UGcmKqG2oA3G5sF8vDdarX", "byside", "byside"),
    ("wrkspc_01ShSn1dhfdmFzcWeHEawKGd", "elusion", "elusion"),
    # Legacy traffic from before workspace-scoped keys existed; almost all of
    # it was prompt-lab itself, so we roll it into the prompt-lab bucket.
    ("__default__", "Default", "prompt-lab"),
]


def remap(conn) -> int:
    """Restamp api_costs/api_usage rows to the mapped project; returns rows changed."""
    total = 0
    for table in ("api_costs", "api_usage"):
        for workspace_id, _name, project in MAPPINGS:
            olds = [
                r[0]
                for r in conn.execute(
                    f"SELECT DISTINCT project FROM {table} "
                    "WHERE workspace_id = ? AND project != ?",
                    (workspace_id, project),
                )
            ]
            for old in olds:
                cur = conn.execute(
                    f"UPDATE {table} SET project = ? "
                    "WHERE workspace_id = ? AND project = ?",
                    (project, workspace_id, old),
                )
                print(f"{table}: {workspace_id} {old} -> {project}: {cur.rowcount} rows")
                total += cur.rowcount
    conn.commit()
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", help="SQLite DB path (default: the store's default)")
    ap.add_argument("--remap", action="store_true",
                    help="restamp existing api_costs/api_usage rows to the mapped project")
    args = ap.parse_args(argv)

    store = SqliteKnowledgeStore(args.db) if args.db else get_store()
    store.migrate()
    for workspace_id, workspace_name, project in MAPPINGS:
        store.upsert_project_workspace(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            project=project,
        )
        print(f"  {workspace_id} → {project} ({workspace_name})")
    print(f"Seeded {len(MAPPINGS)} workspace mappings.")
    total = 0
    if args.remap:
        total = remap(store.conn)
        print(f"Remapped total: {total} rows")
        if total:
            print("Run a full python sync_to_turso.py (no --days) so Turso "
                  "picks up remapped rows older than the nightly 7-day window.")
    store.close()
    return total


if __name__ == "__main__":
    main()
