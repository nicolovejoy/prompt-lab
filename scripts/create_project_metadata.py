"""One-shot: create the `project_metadata` table on Turso (issue #23).

Turso-owned and dashboard-written (web/api/project_metadata.py) — deliberately
no local-SQLite copy and no sync leg, same as `page_views` and
`issue_categories`. The local `projects` table keeps its own status/category for
the local pipeline; the two never sync, so they cannot drift into each other.

`project` holds the CANONICAL project name (aliases are folded before writing).

Run: .venv/bin/python scripts/create_project_metadata.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from claude_api import load_env  # noqa: E402

load_env()

from turso_helper import turso_query  # noqa: E402

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS project_metadata (
        project TEXT PRIMARY KEY,
        category TEXT,
        private INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        updated_at TEXT
    )""",
]

for sql in STATEMENTS:
    turso_query(sql)

count = turso_query("SELECT COUNT(*) AS n FROM project_metadata")[0]["n"]
print(f"project_metadata ready on Turso ({count} rows)")
