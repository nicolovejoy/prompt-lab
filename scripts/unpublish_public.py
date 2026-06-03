#!/usr/bin/env python3
"""Remove a project's rows from the public_* tables (local SQLite + Turso).

`public_session_summaries` / `public_weekly_rollups` are the only data the
unauthenticated /api/public_history endpoint serves. There is no read-time
allowlist (see web/api/public_history.py), so "unpublishing" a project means
deleting its rows from BOTH stores: sync_to_turso.py only upserts, never
deletes, so a local-only delete would leave the rows live on Turso (the DB the
endpoint actually reads).

Dry-run by default; pass --apply to delete. Alias-aware: the project name is
expanded to [canonical, *aliases] so e.g. `byside` also clears `offer-builder`.

    python scripts/unpublish_public.py <project>           # preview counts
    python scripts/unpublish_public.py <project> --apply   # delete both stores
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_api import load_env
from store.sqlite_store import SqliteKnowledgeStore
from store.turso_store import TursoKnowledgeStore

PUBLIC_TABLES = ("public_session_summaries", "public_weekly_rollups")


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def _remote_count(remote: TursoKnowledgeStore, table: str, names: list[str]) -> int:
    ph = _placeholders(len(names))
    res = remote._execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE project IN ({ph})", names
    )
    rows = remote._rows_to_dicts(res)
    return rows[0]["n"] if rows else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Unpublish a project from the public_* tables."
    )
    ap.add_argument("project")
    ap.add_argument(
        "--apply", action="store_true", help="actually delete (default: dry-run)"
    )
    args = ap.parse_args()

    load_env()

    local = SqliteKnowledgeStore()
    names = local.expand_project(args.project)
    ph = _placeholders(len(names))
    print(f"Project '{args.project}' resolves to: {names}")

    for table in PUBLIC_TABLES:
        n = local.conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE project IN ({ph})", names
        ).fetchone()[0]
        print(f"  local  {table}: {n} row(s)")

    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    remote = TursoKnowledgeStore(url=url, token=token) if (url and token) else None
    if remote is not None:
        for table in PUBLIC_TABLES:
            print(f"  turso  {table}: {_remote_count(remote, table, names)} row(s)")
    else:
        print("  turso: TURSO_DATABASE_URL/TURSO_AUTH_TOKEN not set — remote skipped")

    if not args.apply:
        print("\nDry run. Re-run with --apply to delete.")
        return 0

    for table in PUBLIC_TABLES:
        local.conn.execute(f"DELETE FROM {table} WHERE project IN ({ph})", names)
    local.conn.commit()
    print("\nDeleted from local SQLite.")

    if remote is not None:
        for table in PUBLIC_TABLES:
            remote._execute(f"DELETE FROM {table} WHERE project IN ({ph})", names)
        print("Deleted from Turso.")
    else:
        print("WARNING: Turso skipped (no creds) — the live site still serves these rows.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
