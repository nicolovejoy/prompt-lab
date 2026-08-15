#!/usr/bin/env python3
"""Label existing rows in `prompts` with a `kind`.

    .venv/bin/python scripts/backfill_prompt_kind.py            # dry run
    .venv/bin/python scripts/backfill_prompt_kind.py --apply
    .venv/bin/python scripts/backfill_prompt_kind.py --all --apply

Dry-run by default, per the convention every mutating script here follows.
`--all` reclassifies rows that already carry a kind, which is the point of
labelling rather than filtering: when the rules in scripts/prompt_kind.py
improve, every row can be relabelled. Nothing is ever deleted, so this is
always safe to re-run.

Raw prompts are machine-local by invariant and never reach Turso, so this
talks to the local SQLite file directly — there is no cloud copy to update
and no GROUND_CONTROL_STORE to honour.

What it cannot do: recover the prompts the old `length < 20` write-time filter
discarded. Those were never stored. Counts before the cutover stay low, which
is why the change is annotated rather than silently shipped.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_kind import classify  # noqa: E402

DB = Path(os.path.expanduser("~/.claude/prompt-history.db"))


def ensure_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prompts)")}
    if "kind" not in cols:
        conn.execute("ALTER TABLE prompts ADD COLUMN kind TEXT")
        conn.commit()
        print("added column prompts.kind")


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    redo_all = "--all" in argv

    if not DB.exists():
        print(f"no database at {DB}")
        return 2

    conn = sqlite3.connect(DB)
    ensure_column(conn)

    where = "" if redo_all else " WHERE kind IS NULL"
    rows = conn.execute(
        f"SELECT id, prompt, kind FROM prompts{where}").fetchall()

    if not rows:
        print("nothing to label — every row already has a kind (use --all to redo)")
        conn.close()
        return 0

    counts: Counter[str] = Counter()
    changes: list[tuple[str, int]] = []
    moved = 0
    samples: dict[str, str] = {}

    for pid, text, current in rows:
        kind = classify(text or "")
        counts[kind] += 1
        if kind != current:
            moved += 1
        changes.append((kind, pid))
        samples.setdefault(kind, (text or "").replace("\n", " ")[:70])

    total = sum(counts.values())
    print(f"{total} row(s) considered, {moved} would change\n")
    for kind, n in counts.most_common():
        pct = 100.0 * n / total
        print(f"  {kind:<11} {n:>6}  {pct:5.1f}%   e.g. {samples[kind]!r}")

    if not apply:
        print("\ndry run — nothing written. Re-run with --apply.")
        conn.close()
        return 0

    conn.executemany("UPDATE prompts SET kind = ? WHERE id = ?", changes)
    conn.commit()
    written = conn.execute(
        "SELECT COUNT(*) FROM prompts WHERE kind IS NOT NULL").fetchone()[0]
    remaining = conn.execute(
        "SELECT COUNT(*) FROM prompts WHERE kind IS NULL").fetchone()[0]
    conn.close()
    print(f"\napplied. {written} row(s) labelled, {remaining} still NULL.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
