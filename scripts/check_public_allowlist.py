#!/usr/bin/env python3
"""Audit: flag public_* rows for projects NOT on the manifest allowlist.

The unauthenticated /api/public_history endpoint serves whatever rows exist in
public_session_summaries / public_weekly_rollups (no read-time allowlist — see
web/api/public_history.py). Safety rests on write-time discipline: only the
reviewed scripts/backfill_public_*.py one-shots should ever write those tables.
This guard is the backstop — it detects drift by comparing the distinct projects
present in BOTH stores (local SQLite + Turso, which can diverge since sync only
upserts) against docs/public-allowlist.txt, the prompt-lab mirror of the
consumer's manifest. Alias-aware: a row's project is resolved to its canonical
before the check, so e.g. offer-builder is judged as byside.

Report-only by design — it never deletes. On drift, exit 1 and list offenders;
with --fix, also print (do NOT run) the unpublish commands to remove them.

    python scripts/check_public_allowlist.py          # audit, exit 1 on drift
    python scripts/check_public_allowlist.py --fix     # also print unpublish cmds

Exit codes: 0 clean, 1 drift found, 2 allowlist missing/empty.
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
ALLOWLIST_FILE = Path(__file__).resolve().parent.parent / "docs" / "public-allowlist.txt"


def load_allowlist() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        return []
    keys = []
    for line in ALLOWLIST_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def _distinct_local(store: SqliteKnowledgeStore, table: str) -> set[str]:
    rows = store.conn.execute(f"SELECT DISTINCT project FROM {table}").fetchall()
    return {r[0] for r in rows}


def _distinct_remote(remote: TursoKnowledgeStore, table: str) -> set[str]:
    res = remote._execute(f"SELECT DISTINCT project FROM {table}")
    return {r["project"] for r in remote._rows_to_dicts(res)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Flag public_* rows for projects not on the allowlist."
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="also print (do not run) the unpublish commands for any drift",
    )
    args = ap.parse_args()

    load_env()
    local = SqliteKnowledgeStore()
    local.migrate()

    allowlist = load_allowlist()
    if not allowlist:
        print(f"ERROR: allowlist missing or empty: {ALLOWLIST_FILE}", file=sys.stderr)
        return 2

    # Every project-column value legitimately allowed = each allowlist historyKey
    # expanded to [canonical, *aliases], so aliased renames of allowed projects pass.
    allowed: set[str] = set()
    for key in allowlist:
        allowed.update(local.expand_project(key))

    # Where each distinct project appears: project -> {"store/table", ...}.
    present: dict[str, set[str]] = {}
    for table in PUBLIC_TABLES:
        for p in _distinct_local(local, table):
            present.setdefault(p, set()).add(f"local/{table}")

    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    remote = TursoKnowledgeStore(url=url, token=token) if (url and token) else None
    if remote is not None:
        for table in PUBLIC_TABLES:
            for p in _distinct_remote(remote, table):
                present.setdefault(p, set()).add(f"turso/{table}")
    else:
        print(
            "WARNING: Turso creds not set — checked LOCAL only "
            "(the live site reads Turso, so this is an incomplete audit)."
        )

    offenders = sorted(p for p in present if p not in allowed)

    print(f"Allowlist ({len(allowlist)} keys): {', '.join(allowlist)}")
    print(f"Distinct projects in public tables: {len(present)}")

    if not offenders:
        print("OK: no public rows outside the allowlist.")
        return 0

    print(
        f"\nDRIFT: {len(offenders)} project(s) have public rows but are NOT "
        "on the allowlist:"
    )
    for p in offenders:
        where = ", ".join(sorted(present[p]))
        print(f"  - {p}  ({where})")

    if args.fix:
        print("\nTo remove (REVIEW FIRST — this audit never deletes):")
        seen_groups: set[frozenset[str]] = set()
        for p in offenders:
            group = frozenset(local.expand_project(p))
            if group in seen_groups:
                continue  # offender is an alias of one already printed
            seen_groups.add(group)
            print(f"  python scripts/unpublish_public.py {p} --apply")

    return 1


if __name__ == "__main__":
    sys.exit(main())
