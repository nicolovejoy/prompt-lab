"""Close session rows that were never ended.

Run: .venv/bin/python scripts/close_stale_sessions.py            # dry run
     .venv/bin/python scripts/close_stale_sessions.py --execute

Why these exist: "the current session" used to be resolved positionally
("newest open row for this project"), and nothing ever stamped ended_at unless
/handoff ran. Every abandoned session left an open row, and each open row is a
landmine — the next session on that project would resolve to it and file its
prompts there. Binding rows to the real Claude Code session id (see
workflow/hooks/log-prompt.sh) removes the landmine going forward; this closes
the ones already lying around.

ended_at is set to the session's last prompt timestamp — the honest "last time
we saw activity" — falling back to started_at for a session with no prompts.

Re-runnable: only ever touches rows where ended_at IS NULL.

Never closes a session that still looks live. A row counts as live if it is
pointed at by a ~/.claude/state/current-session-* file, or it started inside
--recent-hours, or it is bound to a real conversation (claude_session_id) and
has activity inside --recent-hours.

Recent activity alone is deliberately NOT enough to protect an *unbound* row:
the landmine rows are exactly the ones absorbing today's misattributed prompts
while having started weeks or months ago (one February row was still collecting
prompts in July). A conversation that genuinely started recently is protected by
the started_at clause regardless.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path.home() / ".claude" / "prompt-history.db"
STATE_DIR = Path.home() / ".claude" / "state"


def active_pointer_ids() -> set[int]:
    """Session ids the prompt hook currently considers live."""
    ids: set[int] = set()
    if not STATE_DIR.is_dir():
        return ids
    for f in STATE_DIR.glob("current-session-*"):
        try:
            ids.add(int(f.read_text().strip()))
        except (ValueError, OSError):
            continue
    return ids


def find_stale(conn: sqlite3.Connection, recent_hours: int) -> list[sqlite3.Row]:
    bound = "claude_session_id" in {
        r[1] for r in conn.execute("PRAGMA table_info(sessions)")
    }
    # Pre-migration DBs have no binding column; every row is then unbound.
    bound_expr = "s.claude_session_id IS NOT NULL" if bound else "0"
    cutoff = f"-{recent_hours} hours"
    return list(conn.execute(
        f"""
        SELECT s.id, s.project, s.started_at,
               (SELECT MAX(p.timestamp) FROM prompts p WHERE p.session_id = s.id)
                   AS last_prompt,
               (SELECT COUNT(*) FROM prompts p WHERE p.session_id = s.id)
                   AS n_prompts,
               {bound_expr} AS is_bound
          FROM sessions s
         WHERE s.ended_at IS NULL
           AND s.started_at < datetime('now', :cutoff)
           AND NOT ({bound_expr} AND COALESCE(
                 (SELECT MAX(p.timestamp) FROM prompts p WHERE p.session_id = s.id),
                 s.started_at
               ) >= datetime('now', :cutoff))
         ORDER BY s.started_at
        """,
        {"cutoff": cutoff},
    ))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--execute", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--recent-hours", type=int, default=6,
                    help="leave sessions with activity this recent alone")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    skip = active_pointer_ids()
    rows = find_stale(conn, args.recent_hours)
    targets = [r for r in rows if r["id"] not in skip]
    protected = [r for r in rows if r["id"] in skip]

    total_open = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"
    ).fetchone()[0]

    print(f"db:              {args.db}")
    print(f"open sessions:   {total_open}")
    print(f"stale:           {len(rows)}")
    print(f"protected:       {len(protected)} (live per ~/.claude/state pointer)")
    print(f"to close:        {len(targets)}")
    print()

    no_prompts = sum(1 for r in targets if r["n_prompts"] == 0)
    print(f"  closing to last prompt time: {len(targets) - no_prompts}")
    print(f"  closing to started_at (no prompts): {no_prompts}")
    print()

    for r in targets:
        end = r["last_prompt"] or r["started_at"]
        src = "last prompt" if r["last_prompt"] else "started_at"
        print(f"  {r['id']:>5}  {r['project']:<22} {r['started_at']} "
              f"-> {end}  ({r['n_prompts']} prompts, via {src})")

    if not args.execute:
        print()
        print("DRY RUN — nothing written. Re-run with --execute to apply.")
        return 0

    with conn:
        conn.executemany(
            "UPDATE sessions SET ended_at=? WHERE id=? AND ended_at IS NULL",
            [((r["last_prompt"] or r["started_at"]), r["id"]) for r in targets],
        )

    remaining = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"
    ).fetchone()[0]
    print()
    print(f"Closed {len(targets)}. Open sessions remaining: {remaining}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
