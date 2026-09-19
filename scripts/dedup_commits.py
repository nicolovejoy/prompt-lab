"""Remove duplicate `commits` rows and add the unique index that stops new ones.

`commits` has no unique constraint on `hash` (issue #57). /handoff's
`INSERT OR IGNORE INTO commits (...)` was meant to make a re-run a no-op, but
IGNORE only skips a row that would violate a constraint — there was never one
to violate, so a re-run just inserts the same commit again. ~395 duplicate
rows exist on the laptop DB today.

Attribution rule: when a hash has more than one row, the row with the lowest
`id` — the FIRST session that recorded the commit — is kept. Every other row
for that hash is a duplicate and gets deleted.

Dry run by default. Prints total rows, distinct hashes, duplicate rows that
would be deleted, and how many of the duplicated hashes have copies credited
to more than one distinct `session_id` (so deleting the duplicate also
changes which session gets credit for that commit).

--apply: first backs up the database with SQLite's online backup API
(`conn.backup`) to `<db>.bak-<UTC YYYYmmddTHHMMSSZ>`, verifies the backup is
readable, and prints its path. Aborts with no writes if the backup fails.
Then, in one transaction: deletes the duplicate rows and creates the unique
index `commits_hash` on `commits(hash)`. Prints rows deleted. Idempotent — a
second `--apply` run deletes 0 rows and succeeds (the index already exists
and every hash is already unique).

Run: .venv/bin/python scripts/dedup_commits.py                # dry run
     .venv/bin/python scripts/dedup_commits.py --apply
     .venv/bin/python scripts/dedup_commits.py --db path/to/other.db --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".claude" / "prompt-history.db"


def duplicate_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Rows that are NOT the min(id) for their hash — what --apply deletes."""
    return list(conn.execute("""
        SELECT id, hash, session_id FROM commits
        WHERE id NOT IN (SELECT MIN(id) FROM commits GROUP BY hash)
    """))


def cross_session_hash_count(conn: sqlite3.Connection) -> int:
    """Count of duplicated hashes where the rows sharing that hash aren't all
    credited to the same session_id — deleting the duplicate changes which
    session gets credit for the commit."""
    rows = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT hash FROM commits
            GROUP BY hash
            HAVING COUNT(*) > 1 AND COUNT(DISTINCT session_id) > 1
        )
    """).fetchone()
    return rows[0]


def backup_path(db: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return db.with_name(f"{db.name}.bak-{stamp}")


def make_backup(conn: sqlite3.Connection, dest: Path) -> None:
    """Online backup via SQLite's backup API, then verified readable — a
    backup file that can't be read back is as good as no backup."""
    backup_conn = sqlite3.connect(dest)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()
    check = sqlite3.connect(dest)
    try:
        check.execute("SELECT COUNT(*) FROM commits").fetchone()
    finally:
        check.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--apply", action="store_true",
                    help="delete duplicates and create the unique index (default is a dry run)")
    args = ap.parse_args()

    db = Path(args.db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    distinct = conn.execute("SELECT COUNT(DISTINCT hash) FROM commits").fetchone()[0]
    dups = duplicate_rows(conn)
    cross_session = cross_session_hash_count(conn)

    print(f"db:              {db}")
    print(f"total rows:      {total}")
    print(f"distinct hashes: {distinct}")
    print(f"duplicate rows:  {len(dups)}  (would be deleted)")
    print(f"cross-session:   {cross_session}  (duplicated hashes with copies credited to different session_ids)")

    if not args.apply:
        print()
        print("DRY RUN — nothing written. Re-run with --apply to delete duplicates and add the unique index.")
        conn.close()
        return 0

    print()
    dest = backup_path(db)
    try:
        make_backup(conn, dest)
    except Exception as e:  # noqa: BLE001 — any backup failure must abort, not just known ones
        print(f"BACKUP FAILED: {type(e).__name__}: {e}")
        print("Aborting — no rows deleted, no index created.")
        conn.close()
        return 1
    print(f"Backup written: {dest}")

    with conn:
        cur = conn.execute(
            "DELETE FROM commits WHERE id NOT IN (SELECT MIN(id) FROM commits GROUP BY hash)"
        )
        deleted = cur.rowcount
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS commits_hash ON commits(hash)")

    print(f"Deleted {deleted} duplicate rows. Unique index commits_hash is in place.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
