#!/usr/bin/env python3
"""Sync processed knowledge from local SQLite to Turso.

Pushes daily_summaries, weekly_rollups, intentions, review_snapshots,
and project_snapshots. Does NOT sync raw prompts or sessions (privacy).

Usage:
  python sync_to_turso.py              # sync all processed tables
  python sync_to_turso.py --days 7     # only sync last 7 days of data
  python sync_to_turso.py --dry-run    # show what would be synced

Requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env or environment.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from claude_api import load_env
from store.sqlite_store import SqliteKnowledgeStore
from store.turso_store import TursoKnowledgeStore


def sync_table(local, remote, table_name, query_fn, upsert_fn, dry_run=False):
    """Sync rows from local to remote using query/upsert functions."""
    rows = query_fn(local)
    if not rows:
        print(f"  {table_name}: 0 rows (skip)")
        return 0

    if dry_run:
        print(f"  {table_name}: {len(rows)} rows (dry run)")
        return len(rows)

    for row in rows:
        try:
            upsert_fn(remote, row)
        except Exception as e:
            print(f"  {table_name}: error on row {row.get('id', '?')}: {e}")
    print(f"  {table_name}: {len(rows)} rows synced")
    return len(rows)


def main():
    dry_run = "--dry-run" in sys.argv
    days = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--days" and i < len(sys.argv) - 1:
            days = int(sys.argv[i + 1])

    # Load environment
    load_env()

    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("Error: TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set", file=sys.stderr)
        print("  Add them to .env or set as environment variables", file=sys.stderr)
        sys.exit(1)

    since = None
    if days:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        print(f"Syncing last {days} days (since {since})")
    else:
        print("Syncing all processed data")

    if dry_run:
        print("(dry run — no writes)")

    local = SqliteKnowledgeStore()
    remote = TursoKnowledgeStore(url=url, token=token)

    # Ensure remote tables exist
    if not dry_run:
        print("Running remote migrations...")
        remote.migrate()

    total = 0

    # Daily summaries
    total += sync_table(
        local, remote, "daily_summaries",
        lambda s: s.get_daily_summaries(since=since),
        lambda r, row: r.upsert_daily_summary(
            project=row["project"], date=row["date"],
            summary=row["summary"],
            key_decisions=json.loads(row["key_decisions"]) if isinstance(row["key_decisions"], str) else (row["key_decisions"] or []),
            prompt_count=row.get("prompt_count", 0) or 0,
            session_count=row.get("session_count", 0) or 0,
            commit_count=row.get("commit_count", 0) or 0,
            model=row.get("model", "unknown"),
        ),
        dry_run,
    )

    # Weekly rollups
    total += sync_table(
        local, remote, "weekly_rollups",
        lambda s: s.get_weekly_rollups(since=since),
        lambda r, row: r.upsert_weekly_rollup(
            project=row["project"], week_start=row["week_start"],
            narrative=row["narrative"],
            highlights=json.loads(row["highlights"]) if isinstance(row["highlights"], str) else (row["highlights"] or []),
            daily_summary_ids=json.loads(row["daily_summary_ids"]) if isinstance(row["daily_summary_ids"], str) else (row["daily_summary_ids"] or []),
            prompt_count=row.get("prompt_count", 0) or 0,
            session_count=row.get("session_count", 0) or 0,
            commit_count=row.get("commit_count", 0) or 0,
            model=row.get("model", "unknown"),
        ),
        dry_run,
    )

    # Intentions (sync all active, regardless of date)
    total += sync_table(
        local, remote, "intentions",
        lambda s: s.get_intentions(status="all"),
        lambda r, row: r.upsert_intention(
            id=None,  # Always insert as new in remote
            project=row["project"],
            intention=row["intention"],
            evidence_summary_ids=json.loads(row["evidence"]) if isinstance(row["evidence"], str) else (row["evidence"] or []),
            status=row["status"],
            model=row.get("model", "unknown"),
        ),
        dry_run,
    )

    # Review snapshots
    total += sync_table(
        local, remote, "review_snapshots",
        lambda s: s.get_review_snapshots(limit=100),
        lambda r, row: r.save_review_snapshot(
            review_type=row["review_type"], date=row["date"],
            subject=row.get("subject"),
            content_html=row.get("content_html"),
            content_text=row.get("content_text"),
            content_markdown=row.get("content_markdown"),
            model=row.get("model", "unknown"),
            input_tokens=row.get("input_tokens", 0) or 0,
            output_tokens=row.get("output_tokens", 0) or 0,
        ),
        dry_run,
    )

    # Project snapshots
    total += sync_table(
        local, remote, "project_snapshots",
        lambda s: [s.get_project_snapshot(p) for p in s.get_all_project_names()
                    if s.get_project_snapshot(p) is not None],
        lambda r, row: r.save_project_snapshot(
            project=row["project"], date=row["snapshot_date"],
            data=row["data"] if isinstance(row["data"], dict) else json.loads(row["data"]),
        ),
        dry_run,
    )

    # Project aliases
    try:
        alias_rows = [
            dict(r) for r in local._conn.execute(
                "SELECT alias, canonical FROM project_aliases"
            ).fetchall()
        ]
        if alias_rows:
            if dry_run:
                print(f"  project_aliases: {len(alias_rows)} rows (dry run)")
            else:
                for row in alias_rows:
                    remote._execute(
                        "INSERT OR REPLACE INTO project_aliases (alias, canonical) VALUES (?, ?)",
                        [row["alias"], row["canonical"]],
                    )
                print(f"  project_aliases: {len(alias_rows)} rows synced")
            total += len(alias_rows)
        else:
            print("  project_aliases: 0 rows (skip)")
    except Exception as e:
        print(f"  project_aliases: {e}")

    local.close()
    remote.close()

    print(f"\nTotal: {total} rows {'would be ' if dry_run else ''}synced")


if __name__ == "__main__":
    main()
