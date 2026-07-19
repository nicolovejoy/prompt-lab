"""Helper for gc-write.sh update-session-summary.

Reads summary from stdin, writes via sqlite param binding to dodge any
shell-quoting issues.

Deliberately does NOT set ended_at: writing a summary and ending a session are
separate acts. Coupling them meant a mid-session /handoff closed the row, and
the positional "newest open row" resolver then re-filed every later prompt onto
an unrelated stale session. Ending is now explicit — gc-write.sh end-session.
"""
import sqlite3
import sys

db, sid = sys.argv[1], int(sys.argv[2])
summary = sys.stdin.read()
c = sqlite3.connect(db)
c.execute("UPDATE sessions SET summary=? WHERE id=?", (summary, sid))
c.commit()
c.close()
