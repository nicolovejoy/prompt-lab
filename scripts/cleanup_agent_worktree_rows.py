#!/usr/bin/env python3
"""Delete rows misattributed to agent-worktree "projects".

log-prompt.sh used to take basename(cwd) as the project, so sessions running
inside <repo>/.claude/worktrees/agent-<hash> got logged under fake projects
like agent-a3af86ee5636b49cc, which the synthesizer then summarized and synced
to Turso. The hook now resolves worktree paths to the repo; this cleans up the
rows that already leaked. Idempotent — safe to run on every machine and re-run.

Dry-run by default; pass --apply to delete.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from claude_api import load_env  # noqa: E402

load_env()

from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402
from store.turso_store import TursoKnowledgeStore  # noqa: E402

AGENT_RE = re.compile(r"^agent-[0-9a-f]{15,}$")

LOCAL_TABLES = [
    ("prompts", "project"),
    ("sessions", "project"),
    ("daily_summaries", "project"),
    ("weekly_rollups", "project"),
    ("project_snapshots", "project"),
    ("projects", "name"),
]
TURSO_TABLES = [
    ("daily_summaries", "project"),
    ("weekly_rollups", "project"),
    ("project_snapshots", "project"),
]


def fake_projects(rows):
    return sorted({p for (p,) in rows if p and AGENT_RE.match(p)})


def clean_local(apply: bool) -> None:
    store = SqliteKnowledgeStore()
    conn = store.conn
    for table, col in LOCAL_TABLES:
        rows = conn.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE 'agent-%'").fetchall()
        targets = fake_projects(rows)
        if not targets:
            continue
        for p in targets:
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (p,)).fetchone()[0]
            print(f"local {table}: {p} ({n} rows)")
            if apply:
                conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (p,))
    if apply:
        conn.commit()
    store.close()


def clean_turso(apply: bool) -> None:
    store = TursoKnowledgeStore()
    for table, col in TURSO_TABLES:
        result = store._execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE 'agent-%'")
        targets = fake_projects([(r[col],) for r in store._rows_to_dicts(result)])
        if not targets:
            continue
        for p in targets:
            result = store._execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} = ?", [p])
            n = store._rows_to_dicts(result)[0]["n"]
            print(f"turso {table}: {p} ({n} rows)")
            if apply:
                store._execute(f"DELETE FROM {table} WHERE {col} = ?", [p])
    store.close()


def main() -> None:
    apply = "--apply" in sys.argv
    clean_local(apply)
    clean_turso(apply)
    print("Deleted." if apply else "Dry run — pass --apply to delete.")


if __name__ == "__main__":
    main()
