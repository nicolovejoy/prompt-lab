"""One-shot: create the `page_views` table + indexes on Turso (issue #9).

The table is written only by web/api/beacon.py (cloud-direct — there is
deliberately no local-SQLite copy and no sync leg). Safe to re-run.

Run: .venv/bin/python scripts/create_page_views.py
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
    """CREATE TABLE IF NOT EXISTS page_views (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        site TEXT NOT NULL,
        path TEXT NOT NULL,
        referrer TEXT,
        country TEXT,
        device TEXT,
        event TEXT NOT NULL DEFAULT 'pageview',
        visitor_hash TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_page_views_ts ON page_views(ts)",
    "CREATE INDEX IF NOT EXISTS idx_page_views_site_ts ON page_views(site, ts)",
]

for sql in STATEMENTS:
    turso_query(sql)

count = turso_query("SELECT COUNT(*) AS n FROM page_views")[0]["n"]
print(f"page_views ready on Turso ({count} rows)")
