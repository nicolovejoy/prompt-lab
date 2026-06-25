#!/usr/bin/env python3
"""Sync processed knowledge from local SQLite to Turso.

Pushes daily_summaries, weekly_rollups, review_snapshots,
project_snapshots, and the public_* tables consumed by external sites
(e.g. pianohouseproject.org). Does NOT sync raw prompts or sessions
(privacy).

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

from claude_api import load_env
from store.sqlite_store import SqliteKnowledgeStore
from store.turso_store import TursoKnowledgeStore


def sync_table(local, remote, table_name, query_fn, upsert_fn, dry_run=False, chunk=100):
    """Sync rows from local to remote, batching writes via _execute_many.

    Buffers each upsert_fn's _execute call into (sql, args) tuples, then flushes
    in chunks via remote._execute_many. ~50–100x fewer HTTP round-trips than
    one-row-per-request.
    """
    rows = query_fn(local)
    if not rows:
        print(f"  {table_name}: 0 rows (skip)")
        return 0

    if dry_run:
        print(f"  {table_name}: {len(rows)} rows (dry run)")
        return len(rows)

    buffer = []
    orig_execute = remote._execute

    def buffered_execute(sql, args=None):
        buffer.append((sql, args or []))

    remote._execute = buffered_execute
    try:
        for row in rows:
            try:
                upsert_fn(remote, row)
            except Exception as e:
                print(f"  {table_name}: error on row {row.get('id', '?')}: {e}")
    finally:
        remote._execute = orig_execute

    n = len(buffer)
    for i in range(0, n, chunk):
        remote._execute_many(buffer[i:i + chunk])
        done = min(i + chunk, n)
        if n > chunk:
            print(f"  {table_name}: {done}/{n} synced")
    print(f"  {table_name}: {len(rows)} rows synced")
    return len(rows)


def main():
    sys.stdout.reconfigure(line_buffering=True)
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

    # Public session summaries (consumed by external sites; safe-by-construction)
    total += sync_table(
        local, remote, "public_session_summaries",
        lambda s: s.get_public_session_summaries(since=since),
        lambda r, row: r.upsert_public_session_summary(
            project=row["project"], session_id=row["session_id"],
            started_at=row["started_at"],
            public_summary=row.get("public_summary"),
        ),
        dry_run,
    )

    # Public weekly rollups
    total += sync_table(
        local, remote, "public_weekly_rollups",
        lambda s: s.get_public_weekly_rollups(since=since),
        lambda r, row: r.upsert_public_weekly_rollup(
            project=row["project"], week_of=row["week_of"],
            public_summary=row.get("public_summary"),
            session_count=row.get("session_count", 0) or 0,
            commit_count=row.get("commit_count", 0) or 0,
        ),
        dry_run,
    )

    # Project workspaces (small metadata; sync all)
    total += sync_table(
        local, remote, "project_workspaces",
        lambda s: s.get_project_workspaces(),
        lambda r, row: r.upsert_project_workspace(
            workspace_id=row["workspace_id"],
            workspace_name=row["workspace_name"],
            project=row["project"],
        ),
        dry_run,
    )

    # API usage (per-model tokens)
    total += sync_table(
        local, remote, "api_usage",
        lambda s: s.get_api_usage(since=since),
        lambda r, row: r.upsert_api_usage(
            date=row["date"], workspace_id=row["workspace_id"],
            project=row["project"], model=row["model"],
            input_tokens=row.get("input_tokens", 0) or 0,
            cached_input_tokens=row.get("cached_input_tokens", 0) or 0,
            cache_creation_tokens=row.get("cache_creation_tokens", 0) or 0,
            output_tokens=row.get("output_tokens", 0) or 0,
            cost_computed_usd=row.get("cost_computed_usd", 0.0) or 0.0,
        ),
        dry_run,
    )

    # API costs (per-workspace×description USD; grain matches Admin API
    # response when grouped by description)
    total += sync_table(
        local, remote, "api_costs",
        lambda s: s.get_api_costs(since=since),
        lambda r, row: r.upsert_api_cost(
            date=row["date"], workspace_id=row["workspace_id"],
            project=row["project"], description=row["description"],
            model=row.get("model"), cost_type=row.get("cost_type"),
            token_type=row.get("token_type"),
            service_tier=row.get("service_tier"),
            context_window=row.get("context_window"),
            inference_geo=row.get("inference_geo"),
            cost_reported_usd=row.get("cost_reported_usd", 0.0) or 0.0,
        ),
        dry_run,
    )

    # Claude Code Analytics (per-user-per-day-per-model)
    total += sync_table(
        local, remote, "claude_code_usage",
        lambda s: s.get_claude_code_usage(since=since),
        lambda r, row: r.upsert_claude_code_usage(
            date=row["date"], actor_kind=row["actor_kind"],
            actor_id=row["actor_id"],
            customer_type=row.get("customer_type"),
            terminal_type=row.get("terminal_type"),
            organization_id=row.get("organization_id"),
            sessions=row.get("sessions", 0) or 0,
            lines_added=row.get("lines_added", 0) or 0,
            lines_removed=row.get("lines_removed", 0) or 0,
            commits=row.get("commits", 0) or 0,
            prs=row.get("prs", 0) or 0,
            edit_accepted=row.get("edit_accepted", 0) or 0,
            edit_rejected=row.get("edit_rejected", 0) or 0,
            multi_edit_accepted=row.get("multi_edit_accepted", 0) or 0,
            multi_edit_rejected=row.get("multi_edit_rejected", 0) or 0,
            write_accepted=row.get("write_accepted", 0) or 0,
            write_rejected=row.get("write_rejected", 0) or 0,
            notebook_edit_accepted=row.get("notebook_edit_accepted", 0) or 0,
            notebook_edit_rejected=row.get("notebook_edit_rejected", 0) or 0,
            model=row["model"],
            input_tokens=row.get("input_tokens", 0) or 0,
            output_tokens=row.get("output_tokens", 0) or 0,
            cache_read_tokens=row.get("cache_read_tokens", 0) or 0,
            cache_creation_tokens=row.get("cache_creation_tokens", 0) or 0,
            estimated_cost_cents=row.get("estimated_cost_cents", 0.0) or 0.0,
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
