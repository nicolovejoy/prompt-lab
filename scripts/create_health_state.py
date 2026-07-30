"""One-shot: create the `health_email_state` table on Turso (issue #34).

Key-value state for the daily health email (currently just `paused_until`).
Written only by web/api/health_report.py — cloud-direct, no local-SQLite copy,
no sync leg (same class as page_views). Safe to re-run.

Run: .venv/bin/python scripts/create_health_state.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from claude_api import load_env  # noqa: E402

load_env()

from turso_helper import turso_query  # noqa: E402

turso_query(
    """CREATE TABLE IF NOT EXISTS health_email_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT
    )"""
)

rows = turso_query("SELECT key, value FROM health_email_state")
print(f"health_email_state ready on Turso ({len(rows)} rows)")
for r in rows:
    print(f"  {r['key']} = {r['value']}")
