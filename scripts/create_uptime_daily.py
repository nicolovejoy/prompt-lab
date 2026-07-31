"""One-shot: create the `uptime_daily` table on Turso (uptime archive, phase 1).

One row per monitor per day, written only by web/api/health_report.py on its
cron send path (cloud-direct — deliberately no local-SQLite copy and no leg in
sync_to_turso.py, same class as page_views / health_email_state /
project_metadata). That absence is what makes drift structurally impossible;
don't teach the sync about it.

Why the table exists at all: UptimeRobot is the sensor and keeps 3 months. This
keeps forever. prompt-lab still samples nothing itself.

Run: .venv/bin/python scripts/create_uptime_daily.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

# (date, monitor) is the primary key, so a second pull the same day updates the
# row instead of duplicating it — that upsert is the endpoint's UPTIME_UPSERT_SQL.
STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS uptime_daily (
        date TEXT NOT NULL,
        monitor TEXT NOT NULL,
        uptime_1d REAL,
        uptime_7d REAL,
        uptime_30d REAL,
        avg_response_ms INTEGER,
        status TEXT,
        PRIMARY KEY (date, monitor)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_uptime_daily_date ON uptime_daily(date)",
]


def main():
    # Imported here, not at module scope, so tests can read STATEMENTS without
    # loading env or opening a connection to the real database.
    from claude_api import load_env

    load_env()
    from turso_helper import turso_query

    for sql in STATEMENTS:
        turso_query(sql)

    count = turso_query("SELECT COUNT(*) AS n FROM uptime_daily")[0]["n"]
    print(f"uptime_daily ready on Turso ({count} rows)")


if __name__ == "__main__":
    main()
