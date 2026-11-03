"""Tests for seed_project_workspaces.py --remap.

Run: .venv/bin/python scripts/test_seed_project_workspaces.py

Temp DB only; no network, no pytest. Exits 0 if all pass, 1 otherwise.
"""

from __future__ import annotations

import io
import re
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import seed_project_workspaces as seed  # noqa: E402
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

RECOUNTLY = "wrkspc_01B8VSus5qTLtiE8YyzRBYuA"
BYSIDE = "wrkspc_01UGcmKqG2oA3G5sF8vDdarX"
PROMPT_LAB = "wrkspc_01KXeZDUFDNaEFR3hCe7Qe3q"

failures: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"{'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        failures.append(name)


def make_db(path: Path) -> None:
    store = SqliteKnowledgeStore(path)
    store.migrate()
    rows = [(RECOUNTLY, "prompt-lab"), (BYSIDE, "__unmapped__"), (PROMPT_LAB, "prompt-lab")]
    for i, (ws, proj) in enumerate(rows):
        store.conn.execute(
            "INSERT INTO api_costs (date, workspace_id, project, description, cost_reported_usd)"
            " VALUES (?, ?, ?, ?, 1.0)",
            ("2026-10-01", ws, proj, f"d{i}"),
        )
        store.conn.execute(
            "INSERT INTO api_usage (date, workspace_id, project, model) VALUES (?, ?, ?, 'm')",
            ("2026-10-01", ws, proj),
        )
    store.conn.commit()
    store.close()


def projects(path: Path) -> dict[tuple[str, str], str]:
    conn = sqlite3.connect(path)
    out = {}
    for table in ("api_costs", "api_usage"):
        for ws, proj in conn.execute(f"SELECT workspace_id, project FROM {table}"):
            out[(table, ws)] = proj
    conn.close()
    return out


def run(path: Path, *flags: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        seed.main(["--db", str(path), *flags])
    m = re.search(r"Remapped total: (\d+) rows", buf.getvalue())
    return (int(m.group(1)) if m else -1), buf.getvalue()


with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "a.db"
    make_db(db)
    total, out = run(db, "--remap")
    got = projects(db)
    for t in ("api_costs", "api_usage"):
        check(f"{t} recountly -> raconte", got[(t, RECOUNTLY)] == "raconte")
        check(f"{t} byside -> byside", got[(t, BYSIDE)] == "byside")
        check(f"{t} correct row untouched", got[(t, PROMPT_LAB)] == "prompt-lab")
    check("printed total equals changed rows (4)", total == 4)
    check("per-table line printed",
          f"api_costs: {RECOUNTLY} prompt-lab -> raconte: 1 rows" in out)

    SYNC = "Run a full python sync_to_turso.py (no --days)"
    check("first run prints the full-sync line", SYNC in out)
    total, out2 = run(db, "--remap")
    check("second run omits the full-sync line", SYNC not in out2)
    check("second run changes 0 rows", total == 0)
    check("second run leaves data stable", projects(db) == got)

    db2 = Path(tmp) / "b.db"
    make_db(db2)
    before = projects(db2)
    run(db2)
    check("no --remap: no row changes", projects(db2) == before)

if failures:
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1)
print("\nAll passed")
