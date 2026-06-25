"""Unit tests for web/api/* endpoint handlers.

Run: .venv/bin/python scripts/test_web_api.py

Loads each endpoint module fresh, monkey-patches `turso_query` and
`is_authenticated`, instantiates the handler with stubbed HTTP I/O, calls
`do_GET`, and asserts the captured SQL + response.

Tests focus on: alias expansion in the WHERE clause, auth gating,
and the no-allowlist scrubbed-data contract for public_history.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "web" / "api"))


def load_endpoint(rel_path: str, name: str):
    """Load a web/api/*.py file as a fresh module."""
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Captured:
    """Holds what the handler sent. Returned from invoke()."""

    def __init__(self):
        self.status_code: int | None = None
        self.response_headers: list[tuple[str, str]] = []
        self._body = b""

    @property
    def body(self) -> dict:
        return json.loads(self._body.decode()) if self._body else {}


def invoke(endpoint_module, path: str, headers: dict | None = None) -> Captured:
    """Instantiate the endpoint's handler class with the socket I/O stubbed,
    then call do_GET. Private methods on the handler class (like _send) still
    resolve correctly because we use the real class via __new__.
    """
    cls = endpoint_module.handler
    inst = cls.__new__(cls)  # skip BaseHTTPRequestHandler's socket init
    inst.path = path
    inst.headers = headers or {}

    captured = Captured()

    class _Writer:
        def write(self, data: bytes):
            captured._body += data

    inst.send_response = lambda code: setattr(captured, "status_code", code)
    inst.send_header = lambda k, v: captured.response_headers.append((k, v))
    inst.end_headers = lambda: None
    inst.wfile = _Writer()

    cls.do_GET(inst)
    return captured


# Import turso_helper once so we can patch its turso_query — that's the one
# resolve_project_names calls internally.
import turso_helper  # noqa: E402


_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
            return fn
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}"))
            return fn
        _results.append((name, True, ""))
        return fn
    return deco


def patch(mod, **kwargs):
    """Override module attributes; returns a restore function."""
    saved = {k: getattr(mod, k, None) for k in kwargs}
    for k, v in kwargs.items():
        setattr(mod, k, v)

    def restore():
        for k, v in saved.items():
            setattr(mod, k, v)
    return restore


def patch_turso_query(endpoint_mod, fake):
    """Patch turso_query in both turso_helper and the endpoint module.

    turso_helper's binding is what resolve_project_names uses internally;
    the endpoint's binding is what its do_GET calls directly.
    """
    r1 = patch(turso_helper, turso_query=fake)
    r2 = patch(endpoint_mod, turso_query=fake)

    def restore():
        r2()
        r1()
    return restore


# === public_history.py ===

@test("public_history: 400 when project missing")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_400")
    restore = patch_turso_query(mod, lambda *a, **kw: [])
    try:
        h = invoke(mod, "/api/public_history")
        assert h.status_code == 400, f"got {h.status_code}"
        assert h.body.get("error") == "project required"
    finally:
        restore()


@test("public_history: 200 empty when project has no public rows")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_empty")

    def fake_turso(sql, args=None):
        # No alias rows, no data rows → unknown project yields empty arrays.
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke(mod, "/api/public_history?project=random-project")
        assert h.status_code == 200, f"got {h.status_code}"
        assert h.body.get("sessions") == []
        assert h.body.get("rollups") == []
        assert h.body.get("total_sessions") == 0
    finally:
        restore()


@test("public_history: 200 when project has public rows")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_200_canon")

    def fake_turso(sql, args=None):
        if "canonical FROM project_aliases" in sql and "alias = ?" in sql:
            return []  # not an alias
        if "alias FROM project_aliases" in sql:
            return [{"alias": "offer-builder"}]
        # The actual data queries
        if "public_session_summaries" in sql:
            return [{"session_id": 1, "started_at": "2026-05-01", "public_summary": "x"}]
        if "public_weekly_rollups" in sql:
            return []
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke(mod, "/api/public_history?project=byside")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(h.body.get("sessions", [])) == 1
    finally:
        restore()


@test("public_history: 200 + alias merge when alias resolves to canonical")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_200_alias")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "canonical FROM project_aliases" in sql and "alias = ?" in sql:
            return [{"canonical": "byside"}]  # offer-builder → byside
        if "alias FROM project_aliases" in sql:
            return [{"alias": "offer-builder"}]
        if "public_session_summaries" in sql:
            return [{"session_id": 7, "started_at": "2026-04-01", "public_summary": "y"}]
        if "public_weekly_rollups" in sql:
            return [{"week_of": "2026-04-01", "public_summary": "z",
                     "session_count": 1, "commit_count": 0}]
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke(mod, "/api/public_history?project=offer-builder")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        # data SQL should query IN (canonical, alias)
        data_calls = [c for c in captured if "public_session_summaries" in c[0]]
        assert data_calls
        sql, args = data_calls[0]
        assert "project IN (?,?)" in sql, f"sql: {sql}"
        # Last arg is the limit
        names = args[:-1]
        assert set(names) == {"byside", "offer-builder"}, f"names: {names}"
    finally:
        restore()


@test("public_history: no allowlist gate — any resolved canonical returns 200")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_noallow")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "canonical FROM project_aliases" in sql and "alias = ?" in sql:
            return [{"canonical": "musicforge"}]  # frontend → musicforge
        if "alias FROM project_aliases" in sql:
            return [{"alias": "frontend"}]
        return []  # no data rows; still a 200 with empty arrays

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke(mod, "/api/public_history?project=frontend")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        data_calls = [c for c in captured if "public_session_summaries" in c[0]]
        assert data_calls, "data query should run even with no allowlist"
        _, args = data_calls[0]
        assert set(args[:-1]) == {"musicforge", "frontend"}, f"names: {args[:-1]}"
    finally:
        restore()


@test("public_history: limit clamped to MAX_SESSION_LIMIT")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_clamp")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke(mod, f"/api/public_history?project=byside&limit={10_000}")
        assert h.status_code == 200
        data_calls = [c for c in captured if "public_session_summaries" in c[0]]
        assert data_calls
        _, args = data_calls[0]
        # Last arg is the (clamped) limit
        assert args[-1] == mod.MAX_SESSION_LIMIT, f"limit not clamped: {args[-1]}"
    finally:
        restore()


# === cost_timeline.py ===

@test("cost_timeline: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/cost_timeline.py", "endpoint_cost_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, is_authenticated=lambda _: False)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_timeline?project=prompt-lab")
        assert h.status_code == 401, f"got {h.status_code}"
    finally:
        restore()


@test("cost_timeline: default response has costs + usage, no detail")
def _():
    mod = load_endpoint("web/api/cost_timeline.py", "endpoint_cost_default")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_timeline?project=prompt-lab")
        assert h.status_code == 200
        body = h.body
        assert "costs" in body and "usage" in body
        assert "detail" not in body, "detail key should be absent without ?detail=1"
        # Two SELECTs (costs + usage), no detail SELECT
        select_sqls = [s for s, _ in captured
                       if s.startswith("SELECT") and "FROM api_" in s]
        assert len(select_sqls) == 2, f"expected 2 selects, got {len(select_sqls)}"
    finally:
        restore()


@test("cost_timeline: ?detail=1 adds ungrouped detail rows")
def _():
    mod = load_endpoint("web/api/cost_timeline.py", "endpoint_cost_detail")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "GROUP BY date, model, token_type" in sql:
            return [{
                "date": "2026-05-19", "model": "claude-sonnet-4-6",
                "token_type": "output_tokens", "service_tier": "standard",
                "context_window": "0-200k", "cost_type": "tokens",
                "inference_geo": "us", "cost_usd": 1.23,
            }]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_timeline?project=prompt-lab&detail=1")
        assert h.status_code == 200
        body = h.body
        assert "detail" in body, "detail key missing"
        assert len(body["detail"]) == 1, f"got {body['detail']}"
        row = body["detail"][0]
        assert row["model"] == "claude-sonnet-4-6"
        assert row["token_type"] == "output_tokens"
        # Detail SQL must group by all the dimensions, not just (date, model)
        detail_sqls = [s for s, _ in captured
                       if "GROUP BY date, model, token_type" in s]
        assert detail_sqls, f"no detail SQL emitted, captured: {captured}"
    finally:
        restore()


# === Main ===

def main() -> int:
    if not _results:
        print("no tests ran")
        return 1
    passed = 0
    for name, ok, err in _results:
        mark = "PASS" if ok else "FAIL"
        if ok:
            print(f"  {mark}  {name}")
            passed += 1
        else:
            print(f"  {mark}  {name}")
            print(f"        → {err}")
    failed = len(_results) - passed
    print()
    print(f"{passed} passed, {failed} failed (of {len(_results)})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
