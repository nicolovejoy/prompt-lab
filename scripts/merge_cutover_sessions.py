"""Merge the duplicate session rows left by the 2026-07-19 identity cutover.

Run: .venv/bin/python scripts/merge_cutover_sessions.py            # dry run
     .venv/bin/python scripts/merge_cutover_sessions.py --execute

Why these exist: until 2026-07-19 the prompt hook resolved "the current
session" positionally ("newest open row for this project"); it now binds rows
to the real Claude conversation id (sessions.claude_session_id, see
workflow/hooks/log-prompt.sh). Conversations already in flight at the cutover
therefore own TWO rows — the old unbound one holding the early prompts, and a
new bound one holding everything after. One-time artifact; conversations
started after the cutover bind from their first prompt.

WHAT COUNTS AS A PAIR ("abuts"). Given an unbound row E and a bound row B, all
of these must hold:
  1. same project;
  2. both started on the cutover date (--date, default 2026-07-19);
  3. B.started_at > E.started_at, and both rows have at least one prompt;
  4. no interleaving: E's LAST prompt strictly precedes B's FIRST prompt;
  5. identity proof: the earliest entry in B's conversation transcript
     (~/.claude/projects/*/<claude_session_id>.jsonl) is within
     --abut-seconds of E.started_at.

(5) is what makes this safe. The session row is created by the SessionStart
hook at conversation start, so E.started_at and the transcript's first entry
are two independent recordings of the same instant: agreeing to within seconds
proves B's conversation is the one E's row was opened for. A time-gap
heuristic alone cannot tell a genuine continuation from an unrelated later
conversation, and would be willing to fold a long-lived landmine row (one
February row was still absorbing prompts in July) into a bound row it never
belonged to. Pairs that satisfy 1-4 but not 5 are listed as UNCONFIRMED and
never acted on.

Action per pair: re-point E's prompts and commits at B, back-date B.started_at
to E's (the true conversation start), fill any NULL metadata on B from E, then
delete the emptied shell E. Prompt and commit counts are asserted conserved,
globally and per pair; a pair that fails is refused and the whole run rolls
back.

Idempotent: E is gone after a successful merge, so a second run finds nothing.

Scope guard: only the cutover date is swept. Any other --date requires
--allow-any-date.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path.home() / ".claude" / "prompt-history.db"
STATE_DIR = Path.home() / ".claude" / "state"
TRANSCRIPT_DIR = Path.home() / ".claude" / "projects"
CUTOVER_DATE = "2026-07-19"
CARRY_COLS = ("summary", "utility", "token_count", "hostname")


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


def conversation_start(conv_id: str) -> datetime | None:
    """Earliest timestamp in a conversation transcript, as naive UTC."""
    hits = sorted(TRANSCRIPT_DIR.glob(f"*/{conv_id}.jsonl"))
    if not hits:
        return None
    stamps: list[str] = []
    for path in hits:
        try:
            with open(path) as fh:
                for i, line in enumerate(fh):
                    if i > 200:  # conversation start is near the top
                        break
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(rec, dict) and rec.get("timestamp"):
                        stamps.append(rec["timestamp"])
        except OSError:
            continue
    if not stamps:
        return None
    return datetime.fromisoformat(min(stamps).replace("Z", "+00:00")).replace(tzinfo=None)


def rows_on(conn: sqlite3.Connection, date: str) -> list[sqlite3.Row]:
    return list(conn.execute(
        """
        SELECT s.id, s.project, s.started_at, s.ended_at, s.claude_session_id,
               s.summary, s.utility, s.token_count, s.hostname,
               (SELECT COUNT(*) FROM prompts p WHERE p.session_id = s.id) AS n_prompts,
               (SELECT COUNT(*) FROM commits c WHERE c.session_id = s.id) AS n_commits,
               (SELECT MIN(p.timestamp) FROM prompts p WHERE p.session_id = s.id) AS first_prompt,
               (SELECT MAX(p.timestamp) FROM prompts p WHERE p.session_id = s.id) AS last_prompt
          FROM sessions s
         WHERE date(s.started_at) = :date
         ORDER BY s.started_at
        """,
        {"date": date},
    ))


def find_pairs(
    conn: sqlite3.Connection, date: str, abut_seconds: int, max_gap_minutes: int
) -> tuple[list[dict], list[dict]]:
    """Return (confirmed pairs, unconfirmed near-misses)."""
    rows = rows_on(conn, date)
    unbound = [r for r in rows if r["claude_session_id"] is None and r["n_prompts"]]
    bound = [r for r in rows if r["claude_session_id"] is not None and r["n_prompts"]]

    confirmed: list[dict] = []
    unconfirmed: list[dict] = []
    for b in bound:
        conv_start = conversation_start(b["claude_session_id"])
        b_start = datetime.fromisoformat(b["started_at"])
        for e in unbound:
            if e["project"] != b["project"]:
                continue
            if not (b_start > datetime.fromisoformat(e["started_at"])):
                continue
            if not (e["last_prompt"] < b["first_prompt"]):  # no interleaving
                continue
            gap = (datetime.fromisoformat(b["first_prompt"])
                   - datetime.fromisoformat(e["last_prompt"]))
            if gap > timedelta(minutes=max_gap_minutes):
                continue
            skew = (None if conv_start is None
                    else (datetime.fromisoformat(e["started_at"]) - conv_start).total_seconds())
            pair = {"earlier": e, "later": b, "gap": gap, "skew": skew,
                    "conv_start": conv_start}
            if skew is not None and abs(skew) <= abut_seconds:
                confirmed.append(pair)
            else:
                unconfirmed.append(pair)

    # One shell may only ever fold into one bound row, and vice versa.
    for key in ("earlier", "later"):
        seen: dict[int, dict] = {}
        for p in confirmed:
            seen.setdefault(p[key]["id"], p)
        dupes = [p for p in confirmed if seen[p[key]["id"]] is not p]
        if dupes:
            raise SystemExit(
                f"AMBIGUOUS: more than one candidate shares the same '{key}' row "
                f"({sorted({p[key]['id'] for p in dupes})}) — refusing. Resolve by hand."
            )
    return confirmed, unconfirmed


def blocked(conn: sqlite3.Connection, pair: dict, live: set[int], skip: set[int]) -> str | None:
    e, b = pair["earlier"], pair["later"]
    if e["id"] in skip:
        return "excluded by --skip"
    # Only the shell matters: it is the row that gets emptied and deleted, so the
    # hook must not still be writing to it. A pointer at the target is harmless
    # (the merge only prepends history) and these files go stale — several still
    # name rows from the cutover evening.
    if e["id"] in live:
        return "shell is live per ~/.claude/state pointer"
    n = conn.execute(
        "SELECT COUNT(*) FROM public_session_summaries WHERE session_id IN (?, ?)",
        (e["id"], b["id"]),
    ).fetchone()[0]
    if n:
        return f"{n} public_session_summaries row(s) reference these ids"
    return None


def snapshot(db: str) -> Path:
    src = Path(db)
    dest = src.with_name(f"{src.stem}-backup-{datetime.now():%Y%m%dT%H%M%S}{src.suffix}")
    with sqlite3.connect(db) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest


def merge(conn: sqlite3.Connection, pair: dict) -> None:
    e, b = pair["earlier"], pair["later"]
    want_p = e["n_prompts"] + b["n_prompts"]
    want_c = e["n_commits"] + b["n_commits"]

    conn.execute("UPDATE prompts SET session_id=? WHERE session_id=?", (b["id"], e["id"]))
    conn.execute("UPDATE commits SET session_id=? WHERE session_id=?", (b["id"], e["id"]))
    conn.execute("UPDATE sessions SET started_at=? WHERE id=?", (e["started_at"], b["id"]))
    # A NULL ended_at on the target means the conversation never closed — keep it.
    if e["ended_at"] and b["ended_at"] and e["ended_at"] > b["ended_at"]:
        conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (e["ended_at"], b["id"]))
    for col in CARRY_COLS:
        if e[col] is not None:
            conn.execute(
                f"UPDATE sessions SET {col}=? WHERE id=? AND {col} IS NULL",
                (e[col], b["id"]),
            )

    got_p = conn.execute(
        "SELECT COUNT(*) FROM prompts WHERE session_id=?", (b["id"],)
    ).fetchone()[0]
    got_c = conn.execute(
        "SELECT COUNT(*) FROM commits WHERE session_id=?", (b["id"],)
    ).fetchone()[0]
    left = conn.execute(
        "SELECT (SELECT COUNT(*) FROM prompts WHERE session_id=?)"
        " + (SELECT COUNT(*) FROM commits WHERE session_id=?)", (e["id"], e["id"])
    ).fetchone()[0]
    if (got_p, got_c, left) != (want_p, want_c, 0):
        raise AssertionError(
            f"pair {e['id']}->{b['id']} not conserved: prompts {got_p}/{want_p}, "
            f"commits {got_c}/{want_c}, left on shell {left}"
        )
    conn.execute("DELETE FROM sessions WHERE id=?", (e["id"],))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--execute", action="store_true",
                    help="actually write (default is a dry run)")
    ap.add_argument("--date", default=CUTOVER_DATE,
                    help=f"cutover date to sweep (default {CUTOVER_DATE})")
    ap.add_argument("--allow-any-date", action="store_true",
                    help=f"permit a --date other than {CUTOVER_DATE}")
    ap.add_argument("--abut-seconds", type=int, default=300,
                    help="max skew between shell started_at and conversation start")
    ap.add_argument("--max-gap-minutes", type=int, default=180,
                    help="max quiet gap between the two halves' prompt spans")
    ap.add_argument("--skip", default="",
                    help="comma-separated shell session ids to leave alone")
    args = ap.parse_args()
    skip = {int(x) for x in args.skip.replace(",", " ").split()}

    if args.date != CUTOVER_DATE and not args.allow_any_date:
        print(f"refusing --date {args.date}: this is a one-time cutover cleanup for "
              f"{CUTOVER_DATE}. Pass --allow-any-date if you really mean it.",
              file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    live = active_pointer_ids()
    confirmed, unconfirmed = find_pairs(
        conn, args.date, args.abut_seconds, args.max_gap_minutes
    )
    refusals = [(p, why) for p in confirmed if (why := blocked(conn, p, live, skip))]
    refused_ids = {id(p) for p, _ in refusals}
    targets = [p for p in confirmed if id(p) not in refused_ids]

    before = conn.execute(
        "SELECT (SELECT COUNT(*) FROM sessions), (SELECT COUNT(*) FROM prompts),"
        " (SELECT COUNT(*) FROM commits)"
    ).fetchone()

    print(f"db:              {args.db}")
    print(f"cutover date:    {args.date}")
    print(f"sessions/prompts/commits: {before[0]} / {before[1]} / {before[2]}")
    print(f"confirmed pairs: {len(confirmed)}")
    print(f"refused:         {len(refusals)}")
    print(f"unconfirmed:     {len(unconfirmed)} (listed, never merged)")
    print(f"to merge:        {len(targets)}")
    print()

    for p in targets:
        e, b = p["earlier"], p["later"]
        print(f"  {e['id']:>5} -> {b['id']:<5} {e['project']}")
        print(f"        shell  {e['started_at']}  prompts {e['first_prompt']} .. "
              f"{e['last_prompt']}  ({e['n_prompts']}p/{e['n_commits']}c)")
        print(f"        bound  {b['started_at']}  prompts {b['first_prompt']} .. "
              f"{b['last_prompt']}  ({b['n_prompts']}p/{b['n_commits']}c)")
        print(f"        conv {b['claude_session_id']} started {p['conv_start']} "
              f"(skew {p['skew']:+.1f}s), quiet gap {p['gap']}")
        print(f"        -> {b['id']} becomes {e['n_prompts'] + b['n_prompts']}p/"
              f"{e['n_commits'] + b['n_commits']}c, started_at back-dated to "
              f"{e['started_at']}; row {e['id']} deleted")
        if b["id"] in live:
            print(f"        note: ~/.claude/state still points at target {b['id']} "
                  f"(stale pointer, not a blocker)")
        print()

    for p, why in refusals:
        print(f"  REFUSED {p['earlier']['id']} -> {p['later']['id']} "
              f"{p['earlier']['project']}: {why}")
    for p in unconfirmed:
        e, b = p["earlier"], p["later"]
        skew = "no transcript" if p["skew"] is None else f"skew {p['skew']:+.1f}s"
        print(f"  UNCONFIRMED {e['id']} -> {b['id']} {e['project']}: {skew}, "
              f"quiet gap {p['gap']} — not merged")
    if refusals or unconfirmed:
        print()

    if not args.execute:
        print("DRY RUN — nothing written. Re-run with --execute to apply.")
        return 0
    if not targets:
        print("Nothing to merge.")
        return 0

    print(f"snapshot: {snapshot(args.db)}")
    try:
        with conn:
            for p in targets:
                merge(conn, p)
            after = conn.execute(
                "SELECT (SELECT COUNT(*) FROM sessions), (SELECT COUNT(*) FROM prompts),"
                " (SELECT COUNT(*) FROM commits)"
            ).fetchone()
            if (after[1], after[2]) != (before[1], before[2]):
                raise AssertionError(
                    f"row counts changed: prompts {before[1]}->{after[1]}, "
                    f"commits {before[2]}->{after[2]}"
                )
            if after[0] != before[0] - len(targets):
                raise AssertionError(
                    f"sessions {before[0]}->{after[0]}, expected "
                    f"{before[0] - len(targets)}"
                )
    except Exception as exc:  # any failure must leave the DB untouched
        print(f"ROLLED BACK — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Merged {len(targets)} pair(s). sessions/prompts/commits: "
          f"{after[0]} / {after[1]} / {after[2]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
