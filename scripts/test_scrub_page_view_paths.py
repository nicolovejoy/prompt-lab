"""Tests for scripts/scrub_page_view_paths.py (Turso stubbed, synthetic paths).

Run: .venv/bin/python scripts/test_scrub_page_view_paths.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "scrub_page_view_paths.py"

failures: list[str] = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
        failures.append(label)


def load():
    spec = importlib.util.spec_from_file_location("scrub_page_view_paths", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = [
    {"path": "/", "n": 5},
    {"path": "/about", "n": 3},
    {"path": "/items/12345", "n": 4},
    {"path": "/u/11111111-2222-3333-4444-555555555555/edit", "n": 2},
]


def run(argv, rows=None, fail_on_update=None):
    mod = load()
    calls = []

    def stub(sql, args=None):
        calls.append((sql, list(args) if args else None))
        if sql.lstrip().upper().startswith("SELECT"):
            return ROWS if rows is None else rows
        n_up = sum(1 for c in calls if c[0].lstrip().upper().startswith("UPDATE"))
        if fail_on_update == n_up:
            raise RuntimeError("boom")
        return []

    mod.turso_query = stub
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mod.main(argv)
    updates = [c for c in calls if c[0].lstrip().upper().startswith("UPDATE")]
    run.calls, run.code = calls, code
    return updates, out.getvalue()


print("dry run")
updates, out = run([])
check("no UPDATE issued", updates, [])
check("every dry-run call is a SELECT",
      all(c[0].lstrip().upper().startswith("SELECT") for c in run.calls), True)
check("dry run exit 0", run.code, 0)
check("says dry run", "dry run" in out.lower(), True)
check("prints old -> new", "/items/12345 -> /items/:id" in out, True)
check("unchanged path not listed", "/about ->" in out, False)

print("--apply")
updates, out = run(["--apply"])
check("one UPDATE per changed path", len(updates), 2)
check(
    "update arguments",
    sorted(a for _, a in updates),
    sorted([
        ["/items/:id", "/items/12345"],
        ["/u/:id/edit", "/u/11111111-2222-3333-4444-555555555555/edit"],
    ]),
)
check("update sql", {s for s, _ in updates}, {"UPDATE page_views SET path = ? WHERE path = ?"})
check("per-path applied line", "applied: /items/12345 -> /items/:id (4 rows)" in out, True)
check("totals line", "Applied 2 paths, 6 rows" in out and "pre-write SELECT" in out, True)
check("apply exit 0", run.code, 0)

print("failure partway")
updates, out = run(["--apply"], fail_on_update=2)
check("nonzero exit", run.code, 1)
check("progress message", "applied 1 of 2 paths" in out and "failed at" in out, True)
check("first path recorded", "applied: /items/12345" in out, True)

print("already scrubbed")
updates, out = run(["--apply"], rows=[{"path": "/items/:id", "n": 9}, {"path": "/", "n": 1}])
check("no UPDATE", updates, [])
check("zero totals", "0 paths change" in out, True)

if failures:
    print(f"\n{len(failures)} failed")
    sys.exit(1)
print("\nall passed")
