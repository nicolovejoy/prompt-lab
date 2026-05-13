"""Helper for gc-write.sh update-session-summary.

Reads summary from stdin, writes via sqlite param binding to dodge any
shell-quoting issues.
"""
import sqlite3
import sys

db, sid = sys.argv[1], int(sys.argv[2])
summary = sys.stdin.read()
c = sqlite3.connect(db)
c.execute(
    "UPDATE sessions SET summary=?, ended_at=datetime('now') WHERE id=?",
    (summary, sid),
)
c.commit()
c.close()
