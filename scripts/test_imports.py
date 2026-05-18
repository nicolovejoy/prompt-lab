"""Compile-check every .py file in the repo and import-check the ones we expect to be importable.

Run: .venv/bin/python scripts/test_imports.py

Two phases:
  1. py_compile every .py — catches syntax errors anywhere.
  2. Import the canonical entry points — catches broken imports, typos, missing names.

Exits 0 if everything passes, 1 otherwise.
"""

from __future__ import annotations

import importlib
import importlib.util
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "web"))  # web/api/* import sibling helpers
sys.path.insert(0, str(ROOT / "web" / "api"))

SKIP_DIRS = {".venv", "__pycache__", ".git", "reports", "node_modules", "build"}


def iter_py_files() -> list[Path]:
    files = []
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def compile_check(files: list[Path]) -> list[tuple[Path, str]]:
    """Return [(path, error)] for files with syntax errors."""
    failures = []
    for p in files:
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            failures.append((p, str(e)))
    return failures


# Modules to import-check. These are the canonical entry points; if they import
# cleanly, everything they transitively use must also import cleanly.
IMPORT_TARGETS = [
    "store",
    "store.base",
    "store.sqlite_store",
    "store.turso_store",
    "claude_api",
    "alias",  # scripts/alias.py via sys.path
    "auth_helper",
    "turso_helper",
]

# Files we should be able to load as module-from-file (not in a package).
# Each entry is the path relative to ROOT.
FILE_IMPORT_TARGETS = [
    "synthesizer.py",
    "sync_to_turso.py",
    "send-review.py",
    "generate-report.py",
    "backfill_project_urls.py",
    "todos.py",
    "dashboard/server.py",
    "mobile/serve.py",
    "web/api/intentions.py",
    "web/api/rollups.py",
    "web/api/summaries.py",
    "web/api/public_history.py",
    "web/api/overview.py",
    "web/api/project.py",
    "web/api/projects.py",
    "web/api/info.py",
    "web/api/login.py",
    "web/api/ask.py",
    "web/api/reviews.py",
]


def import_module_check(name: str) -> tuple[bool, str | None]:
    try:
        importlib.import_module(name)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def import_file_check(rel_path: str) -> tuple[bool, str | None]:
    path = ROOT / rel_path
    if not path.exists():
        return True, None  # OK to skip files that don't exist
    spec = importlib.util.spec_from_file_location(
        f"_import_check_{path.stem}_{hash(rel_path)}", path
    )
    if spec is None or spec.loader is None:
        return False, "could not load module spec"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    files = iter_py_files()
    print(f"Scanned {len(files)} .py files under {ROOT.name}/")
    print()

    # Phase 1: syntax
    syntax_failures = compile_check(files)
    print(f"Phase 1 — syntax (py_compile): {len(files) - len(syntax_failures)} pass, "
          f"{len(syntax_failures)} fail")
    for p, err in syntax_failures:
        print(f"  FAIL {p.relative_to(ROOT)}")
        for line in err.splitlines()[:3]:
            print(f"        {line}")

    # Phase 2: imports — packaged modules
    module_failures = []
    for name in IMPORT_TARGETS:
        ok, err = import_module_check(name)
        if not ok:
            module_failures.append((name, err))
    print(f"Phase 2a — packaged modules: {len(IMPORT_TARGETS) - len(module_failures)} pass, "
          f"{len(module_failures)} fail")
    for name, err in module_failures:
        print(f"  FAIL {name}")
        print(f"        {err}")

    # Phase 2b: imports — top-level scripts loaded as files
    file_failures = []
    for rel in FILE_IMPORT_TARGETS:
        ok, err = import_file_check(rel)
        if not ok:
            file_failures.append((rel, err))
    print(f"Phase 2b — top-level scripts: "
          f"{len(FILE_IMPORT_TARGETS) - len(file_failures)} pass, "
          f"{len(file_failures)} fail")
    for rel, err in file_failures:
        print(f"  FAIL {rel}")
        print(f"        {err}")

    # Phase 3: instantiate concrete stores — catches abstract-method drift
    # (a method added to KnowledgeStore but not implemented on a subclass would
    # import cleanly and only fail at instantiation, silently breaking /handoff).
    instantiation_failures = []
    try:
        from store.sqlite_store import SqliteKnowledgeStore
        SqliteKnowledgeStore()
    except Exception as e:  # noqa: BLE001
        instantiation_failures.append(("SqliteKnowledgeStore", f"{type(e).__name__}: {e}"))
    try:
        from store.turso_store import TursoKnowledgeStore
        # Skip if env not configured — instantiation needs TURSO_DATABASE_URL.
        import os
        if os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"):
            TursoKnowledgeStore()
        else:
            # Still catches abstract-method drift via class construction itself.
            TursoKnowledgeStore.__abstractmethods__  # type: ignore[attr-defined]
            if TursoKnowledgeStore.__abstractmethods__:
                raise TypeError(
                    "Can't instantiate abstract class TursoKnowledgeStore "
                    f"without an implementation for abstract method "
                    f"{next(iter(TursoKnowledgeStore.__abstractmethods__))!r}"
                )
    except Exception as e:  # noqa: BLE001
        instantiation_failures.append(("TursoKnowledgeStore", f"{type(e).__name__}: {e}"))
    print(f"Phase 3 — store instantiation: "
          f"{2 - len(instantiation_failures)} pass, {len(instantiation_failures)} fail")
    for name, err in instantiation_failures:
        print(f"  FAIL {name}")
        print(f"        {err}")

    total_failures = (
        len(syntax_failures) + len(module_failures)
        + len(file_failures) + len(instantiation_failures)
    )
    print()
    if total_failures == 0:
        print("All imports clean.")
        return 0
    print(f"{total_failures} total failures.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
