"""Audit result contract against temporary SQLite and a fake remote transport."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402
import sync_to_turso  # noqa: E402

spec = importlib.util.spec_from_file_location("public_audit", ROOT / "scripts/check_public_allowlist.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
failures = []


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)
        print(detail)


def run_case(*, local_keys=(), remote_keys=(), credentials="full", fail_remote=False,
             allowlist=True, fix=False, fail_local=False):
    with tempfile.TemporaryDirectory(prefix="public-audit-") as tmp:
        db = Path(tmp) / "history.db"
        local = SqliteKnowledgeStore(db)
        local.migrate()
        local.conn.executemany(
            "INSERT INTO public_weekly_rollups(project,week_of) VALUES(?, '2026-09-07')",
            [(key,) for key in local_keys],
        )
        local.conn.execute("INSERT INTO project_aliases(alias,canonical) VALUES('old-public','public')")
        local.conn.commit()
        manifest = Path(tmp) / "allowlist.txt"
        if allowlist:
            manifest.write_text("# reviewed keys\npublic\n")

        class Remote:
            def __init__(self, **kwargs):
                self.calls = 0

            def _execute(self, sql):
                if fail_remote:
                    raise RuntimeError("fixture DNS failure")
                assert sql.startswith("SELECT DISTINCT project FROM public_")
                return [{"project": key} for key in remote_keys]

            def _rows_to_dicts(self, result):
                return result

        values = {}
        if credentials in {"full", "partial"}:
            values["TURSO_DATABASE_URL"] = "https://fake.invalid"
        if credentials == "full":
            values["TURSO_AUTH_TOKEN"] = "fake-token"
        out = io.StringIO()
        err = io.StringIO()

        def local_factory():
            if fail_local:
                raise sqlite3.OperationalError("fixture locked")
            return local

        with patch.dict(os.environ, values, clear=True), \
                patch.object(audit, "load_env", lambda: None), \
                patch.object(audit, "ALLOWLIST_FILE", manifest), \
                patch.object(audit, "SqliteKnowledgeStore", local_factory), \
                patch.object(audit, "TursoKnowledgeStore", Remote), \
                patch.object(sys, "argv", ["audit"] + (["--fix"] if fix else [])), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = audit.main()
        local.close()
        conn = sqlite3.connect(db)
        remaining = conn.execute("SELECT COUNT(*) FROM public_weekly_rollups").fetchone()[0]
        conn.close()
        check("audit never removes public rows", remaining == len(local_keys))
        return rc, out.getvalue() + err.getvalue()


for args, expected, label in [
    ({"local_keys": ["public"], "remote_keys": ["old-public"]}, 0, "complete alias-aware clean audit"),
    ({"local_keys": ["private"], "remote_keys": ["public"], "fix": True}, 10, "confirmed local drift"),
    ({"remote_keys": ["private"]}, 10, "confirmed remote drift"),
    ({"credentials": "missing"}, 3, "missing credentials are incomplete"),
    ({"credentials": "partial"}, 3, "partial credentials are incomplete"),
    ({"fail_remote": True}, 4, "DNS failure is operational error"),
    ({"fail_local": True}, 4, "local DB failure is operational error"),
    ({"allowlist": False}, 2, "missing allowlist is configuration error"),
]:
    rc, output = run_case(**args)
    check(label, rc == expected, output)
    if expected != 0:
        check(f"{label} never claims clean", "OK:" not in output, output)
    if args.get("fix"):
        check("fix remains a printed suggestion", "unpublish_public.py private --apply" in output)

# The post-sync consumer must use the same exit-code contract as readup.
for rc, expected in ((0, "OK (no drift)"), (10, "DRIFT"), (1, "could not complete"),
                     (3, "could not complete"), (4, "could not complete")):
    output = io.StringIO()
    result = SimpleNamespace(returncode=rc, stdout="fixture result", stderr="fixture diagnostic")
    with patch.object(sync_to_turso.subprocess, "run", return_value=result), \
            contextlib.redirect_stdout(output):
        sync_to_turso.check_public_allowlist_drift()
    check(f"post-sync audit classifies exit {rc}", expected in output.getvalue())

if failures:
    sys.exit(f"{len(failures)} failures: {failures}")
print("All public audit contract tests passed.")
