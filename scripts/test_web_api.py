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
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "web" / "api"))

from day_helper import lab_today  # noqa: E402  (needs the web/ path above)


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


def invoke_post(endpoint_module, path: str, body, headers: dict | None = None) -> Captured:
    """Same as invoke() but calls do_POST with a stubbed request body.

    `body` may be a dict (encoded to JSON) or raw bytes, so tests can send
    malformed payloads too. Headers are a plain dict, so — unlike the real
    case-insensitive email.message.Message that BaseHTTPRequestHandler hands a
    live handler — lookups here are case-SENSITIVE. Endpoints in this repo read
    lowercase header names; keep it that way or a handler will silently see no
    body under test while working fine in production.
    """
    import io

    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    cls = endpoint_module.handler
    inst = cls.__new__(cls)
    inst.path = path
    inst.headers = {**(headers or {}), "content-length": str(len(raw))}
    inst.rfile = io.BytesIO(raw)

    captured = Captured()

    class _Writer:
        def write(self, data: bytes):
            captured._body += data

    inst.send_response = lambda code: setattr(captured, "status_code", code)
    inst.send_header = lambda k, v: captured.response_headers.append((k, v))
    inst.end_headers = lambda: None
    inst.wfile = _Writer()

    cls.do_POST(inst)
    return captured


# Import turso_helper once so we can patch its turso_query — that's the one
# resolve_project_names calls internally.
import turso_helper  # noqa: E402

# Needed early: several endpoint fixtures below (cost_overview, activity_timeline,
# overview, day) patch resolve_access directly now that those endpoints route
# auth through access_helper instead of auth_helper.is_authenticated.
import access_helper  # noqa: E402


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


def _projection_turso(captured, *, public_counts, prose_weeks, private_weeks):
    """Fake turso for the counts-projection tests.

    prose_weeks: list of (week_of, session_count, commit_count) published rows.
    private_weeks: list of (week_start, session_count, commit_count) private rows.
    """
    def fake(sql, args=None):
        captured.append((sql, args or []))
        if "canonical FROM project_aliases" in sql and "alias = ?" in sql:
            return []  # not an alias
        if "alias FROM project_aliases" in sql:
            return []  # no aliases
        if "public_session_summaries" in sql:
            return []
        if "public_weekly_rollups" in sql:
            return [{"week_of": w, "public_summary": f"prose-{w}",
                     "session_count": s, "commit_count": c}
                    for (w, s, c) in prose_weeks]
        if "public_counts FROM project_metadata" in sql:
            return [{"public_counts": 1 if public_counts else 0}]
        if "week_start" in sql and "FROM weekly_rollups" in sql:
            return [{"week_start": w, "session_count": s, "commit_count": c}
                    for (w, s, c) in private_weeks]
        return []
    return fake


@test("public_history: opted-in project overlays counts-only weeks, prose wins")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_proj")
    captured = []
    fake = _projection_turso(
        captured, public_counts=True,
        prose_weeks=[("2026-07-13", 9, 9)],
        private_weeks=[("2026-07-13", 1, 1), ("2026-07-06", 0, 4),
                       ("2026-06-29", 1, 1)])
    restore = patch_turso_query(mod, fake)
    try:
        h = invoke(mod, "/api/public_history?project=prompt-lab")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        rollups = h.body["rollups"]
        weeks = [r["week_of"] for r in rollups]
        # 3 distinct weeks, sorted newest first.
        assert weeks == ["2026-07-13", "2026-07-06", "2026-06-29"], weeks
        # Published week keeps its prose AND its published counts (9,9),
        # NOT the private (1,1) values.
        top = rollups[0]
        assert top["public_summary"] == "prose-2026-07-13", top
        assert top["session_count"] == 9 and top["commit_count"] == 9, top
        # Projected weeks are counts-only (null prose).
        assert rollups[1]["public_summary"] is None, rollups[1]
        assert rollups[1]["session_count"] == 0 and rollups[1]["commit_count"] == 4
        assert rollups[2]["public_summary"] is None, rollups[2]
    finally:
        restore()


@test("public_history: NOT opted-in project never queries private weekly_rollups")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_noopt")
    captured = []
    fake = _projection_turso(
        captured, public_counts=False,
        prose_weeks=[("2026-07-13", 2, 2)],
        private_weeks=[("2026-07-06", 5, 5)])
    restore = patch_turso_query(mod, fake)
    try:
        h = invoke(mod, "/api/public_history?project=prompt-lab")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        # Only the published week appears; no projection.
        assert [r["week_of"] for r in h.body["rollups"]] == ["2026-07-13"]
        private_calls = [c for c in captured
                         if "week_start" in c[0] and "FROM weekly_rollups" in c[0]]
        assert not private_calls, f"private table queried when not opted in: {private_calls}"
    finally:
        restore()


@test("public_history: projection query selects numeric columns only (no prose)")
def _():
    mod = load_endpoint("web/api/public_history.py", "endpoint_publichist_safe")
    captured = []
    fake = _projection_turso(
        captured, public_counts=True, prose_weeks=[],
        private_weeks=[("2026-07-06", 1, 1)])
    restore = patch_turso_query(mod, fake)
    try:
        h = invoke(mod, "/api/public_history?project=prompt-lab")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        private_calls = [c for c in captured
                         if "week_start" in c[0] and "FROM weekly_rollups" in c[0]]
        assert private_calls, "projection query never ran"
        sql = private_calls[0][0]
        # Structural prose-safety: the private query must NEVER touch prose cols.
        assert "narrative" not in sql, f"prose column leaked into query: {sql}"
        assert "highlights" not in sql, f"prose column leaked into query: {sql}"
        assert "session_count" in sql and "commit_count" in sql, sql
    finally:
        restore()


# === cost_timeline.py ===

@test("cost_timeline: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/cost_timeline.py", "endpoint_cost_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, resolve_access=lambda h: None)

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
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access("admin", "a@b.c", None, None))

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
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access("admin", "a@b.c", None, None))

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


# === cost_overview.py ===

@test("cost_overview: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/cost_overview.py", "endpoint_costov_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, resolve_access=lambda h: None)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_overview")
        assert h.status_code == 401, f"got {h.status_code}"
    finally:
        restore()


@test("cost_overview: folds raw project names into canonical and re-sums")
def _():
    mod = load_endpoint("web/api/cost_overview.py", "endpoint_costov_fold")

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return [{"alias": "offer-builder", "canonical": "byside"}]
        if "FROM api_costs" in sql:
            # Same date+model under canonical + alias → should collapse to one row.
            return [
                {"date": "2026-06-01", "project": "byside",
                 "model": "claude-sonnet-4-6", "cost_usd": 1.0},
                {"date": "2026-06-01", "project": "offer-builder",
                 "model": "claude-sonnet-4-6", "cost_usd": 0.5},
                {"date": "2026-06-01", "project": "prompt-lab",
                 "model": "claude-opus-4-8", "cost_usd": 2.0},
            ]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_overview?since=2026-05-01")
        assert h.status_code == 200, f"got {h.status_code}"
        rows = h.body["rows"]
        byside = [r for r in rows if r["project"] == "byside"]
        assert len(byside) == 1, f"expected aliases folded into one byside row, got {byside}"
        assert abs(byside[0]["cost_usd"] - 1.5) < 1e-9, f"got {byside[0]}"
        assert not any(r["project"] == "offer-builder" for r in rows), "alias name leaked"
        assert any(r["project"] == "prompt-lab" for r in rows)
    finally:
        restore()


@test("cost_overview: passes since/until as date bounds")
def _():
    mod = load_endpoint("web/api/cost_overview.py", "endpoint_costov_bounds")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/cost_overview?since=2026-05-01&until=2026-06-01")
        assert h.status_code == 200
        cost_calls = [(s, a) for s, a in captured if "FROM api_costs" in s]
        assert cost_calls, "no api_costs query emitted"
        sql, args = cost_calls[0]
        assert "date >= ?" in sql and "date <= ?" in sql, f"sql: {sql}"
        assert "2026-05-01" in args and "2026-06-01" in args, f"args: {args}"
    finally:
        restore()


# === activity_timeline.py ===

@test("activity_timeline: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, resolve_access=lambda h: None)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/activity_timeline")
        assert h.status_code == 401, f"got {h.status_code}"
        assert h.body.get("error") == "unauthorized", f"got {h.body}"
    finally:
        restore()


@test("activity_timeline: folds raw project names into canonical and re-sums")
def _():
    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_fold")

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return [{"alias": "offer-builder", "canonical": "byside"}]
        if "FROM daily_summaries" in sql:
            # Same date under canonical + alias → should collapse to one row.
            return [
                {"date": "2026-06-01", "project": "byside",
                 "sessions": 1, "prompts": 10, "commits": 2},
                {"date": "2026-06-01", "project": "offer-builder",
                 "sessions": 2, "prompts": 5, "commits": 1},
                {"date": "2026-06-01", "project": "prompt-lab",
                 "sessions": 3, "prompts": 40, "commits": 7},
            ]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/activity_timeline?days=30")
        assert h.status_code == 200, f"got {h.status_code}"
        rows = h.body["rows"]
        byside = [r for r in rows if r["project"] == "byside"]
        assert len(byside) == 1, f"expected aliases folded into one byside row, got {byside}"
        assert byside[0]["sessions"] == 3, f"got {byside[0]}"
        assert byside[0]["prompts"] == 15, f"got {byside[0]}"
        assert byside[0]["commits"] == 3, f"got {byside[0]}"
        assert not any(r["project"] == "offer-builder" for r in rows), "alias name leaked"
        assert any(r["project"] == "prompt-lab" for r in rows)
        # Sorted by (date, project).
        assert rows == sorted(rows, key=lambda r: (r["date"], r["project"])), f"unsorted: {rows}"
    finally:
        restore()


@test("activity_timeline: all three metrics are ints, NULL columns become 0")
def _():
    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_metrics")

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return []
        if "FROM daily_summaries" in sql:
            return [
                {"date": "2026-06-02", "project": "musicforge",
                 "sessions": None, "prompts": 4, "commits": None},
                {"date": "2026-06-01", "project": "prntd",
                 "sessions": 1, "prompts": None, "commits": 0},
            ]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/activity_timeline")
        assert h.status_code == 200, f"got {h.status_code}"
        rows = h.body["rows"]
        assert len(rows) == 2, f"got {rows}"
        for r in rows:
            for metric in ("sessions", "prompts", "commits"):
                assert metric in r, f"{metric} missing from {r}"
                assert isinstance(r[metric], int), f"{metric} not int in {r}"
                assert r[metric] is not None
        mf = [r for r in rows if r["project"] == "musicforge"][0]
        assert (mf["sessions"], mf["prompts"], mf["commits"]) == (0, 4, 0), f"got {mf}"
        pr = [r for r in rows if r["project"] == "prntd"][0]
        assert (pr["sessions"], pr["prompts"], pr["commits"]) == (1, 0, 0), f"got {pr}"
        # Sorted by date ascending.
        assert [r["date"] for r in rows] == ["2026-06-01", "2026-06-02"], f"got {rows}"
        assert ("Cache-Control", "no-store") in h.response_headers, f"got {h.response_headers}"
    finally:
        restore()


@test("activity_timeline: coerces Turso's string-encoded SUM() values to ints")
def _():
    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_strints")

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return []
        if "FROM daily_summaries" in sql:
            # Turso's HTTP API returns integer column values as JSON strings.
            return [{"date": "2026-06-01", "project": "prompt-lab",
                     "sessions": "3", "prompts": "42", "commits": "7"}]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/activity_timeline")
        assert h.status_code == 200, f"got {h.status_code}"
        r = h.body["rows"][0]
        assert (r["sessions"], r["prompts"], r["commits"]) == (3, 42, 7), f"got {r}"
        for metric in ("sessions", "prompts", "commits"):
            assert isinstance(r[metric], int), f"{metric} left as {type(r[metric])}: {r}"
    finally:
        restore()


@test("activity_timeline: ?days= bounds the window")
def _():
    import datetime as _dt

    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_days")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/activity_timeline?days=90")
        assert h.status_code == 200, f"got {h.status_code}"
        calls = [(s, a) for s, a in captured if "FROM daily_summaries" in s]
        assert calls, "no daily_summaries query emitted"
        sql, args = calls[0]
        assert "date >= ?" in sql, f"sql: {sql}"
        # Lab day, not UTC (#48) — deriving the expectation in UTC made this
        # test pass by day and fail after 5pm Pacific, which is exactly the
        # bug it is meant to guard.
        today = lab_today()
        expected = (today - _dt.timedelta(days=89)).isoformat()
        assert args and args[0] == expected, f"expected {expected}, args: {args}"
        assert h.body.get("days") == 90, f"got {h.body.get('days')}"

        # Default window is 30 days.
        captured.clear()
        h2 = invoke(mod, "/api/activity_timeline")
        assert h2.status_code == 200
        _, args2 = [(s, a) for s, a in captured if "FROM daily_summaries" in s][0]
        assert args2[0] == (today - _dt.timedelta(days=29)).isoformat(), f"args: {args2}"
        assert h2.body.get("days") == 30
    finally:
        restore()


@test("activity_timeline: garbage/absurd ?days= falls back or clamps, never 500s")
def _():
    mod = load_endpoint("web/api/activity_timeline.py", "endpoint_acttl_baddays")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))

    def restore():
        restore_a()
        restore_q()
    try:
        for bad in ("abc", "", "1e9", "-5", "0", "nan"):
            captured.clear()
            h = invoke(mod, f"/api/activity_timeline?days={bad}")
            assert h.status_code == 200, f"days={bad!r} got {h.status_code}"
            assert h.body["rows"] == [], f"days={bad!r} got {h.body}"
            days = h.body.get("days")
            assert isinstance(days, int) and 1 <= days <= 3650, f"days={bad!r} → {days}"
        # Absurdly large clamps to the 3650-day ceiling rather than erroring.
        captured.clear()
        h = invoke(mod, "/api/activity_timeline?days=999999")
        assert h.status_code == 200, f"got {h.status_code}"
        assert h.body.get("days") == 3650, f"got {h.body.get('days')}"
    finally:
        restore()


# === todos.py ===

@test("todos: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/todos.py", "endpoint_todos_unauth")
    restore_a = patch(mod, is_authenticated=lambda _: False)
    try:
        h = invoke(mod, "/api/todos")
        assert h.status_code == 401, f"got {h.status_code}"
    finally:
        restore_a()


@test("todos: configured=false when GITHUB_TOKEN unset")
def _():
    import os
    mod = load_endpoint("web/api/todos.py", "endpoint_todos_unconfigured")
    restore_a = patch(mod, is_authenticated=lambda _: True)
    saved = os.environ.pop("GITHUB_TOKEN", None)
    try:
        h = invoke(mod, "/api/todos")
        assert h.status_code == 200, f"got {h.status_code}"
        assert h.body.get("configured") is False
        assert h.body.get("total") == 0
    finally:
        if saved is not None:
            os.environ["GITHUB_TOKEN"] = saved
        restore_a()


@test("todos: groups issues by repo, folds aliases, excludes PRs")
def _():
    import os
    mod = load_endpoint("web/api/todos.py", "endpoint_todos_group")
    restore_a = patch(mod, is_authenticated=lambda _: True)
    restore_q = patch_turso_query(
        mod, lambda *a, **kw: [{"alias": "offer-builder", "canonical": "byside"}])

    fake_items = [
        {"title": "Fix A", "number": 1, "html_url": "u1", "labels": [{"name": "bug"}],
         "repository_url": "https://api.github.com/repos/nicolovejoy/offer-builder",
         "comments": 0, "updated_at": "2026-06-20T00:00:00Z"},
        {"title": "Fix B", "number": 2, "html_url": "u2", "labels": [],
         "repository_url": "https://api.github.com/repos/nicolovejoy/prntd",
         "comments": 1, "updated_at": "2026-06-21T00:00:00Z"},
        {"title": "A PR", "number": 3, "html_url": "u3", "labels": [],
         "repository_url": "https://api.github.com/repos/nicolovejoy/prntd",
         "pull_request": {"url": "x"}, "updated_at": "2026-06-22T00:00:00Z"},
    ]
    restore_fetch = patch(mod, _fetch_open_issues=lambda token, user: fake_items)
    saved = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = "ghp_test"
    try:
        h = invoke(mod, "/api/todos")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        projs = h.body["projects"]
        assert "byside" in projs, f"alias not folded: {list(projs)}"
        assert "offer-builder" not in projs
        assert h.body["total"] == 2, f"PR not excluded? total={h.body['total']}"
    finally:
        if saved is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = saved
        restore_fetch()
        restore_q()
        restore_a()


# === todos.py categorize (by-type) ===

_CAT_ITEMS = [
    {"title": "Fix crash", "number": 1, "html_url": "u1", "labels": [{"name": "bug"}],
     "repository_url": "https://api.github.com/repos/nicolovejoy/musicforge",
     "updated_at": "2026-07-01T00:00:00Z"},
    {"title": "Add export", "number": 2, "html_url": "u2", "labels": [],
     "repository_url": "https://api.github.com/repos/nicolovejoy/prntd",
     "updated_at": "2026-07-02T00:00:00Z"},
]


@test("todos categorize: reader gets cached categories, no classify")
def _():
    import os
    mod = load_endpoint("web/api/todos.py", "endpoint_todos_cat_reader")
    restore_auth = patch(mod, is_authenticated=lambda _: True,
                         get_role=lambda _: "reader")
    inserts = []

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return []
        if "SELECT repo, number, title, category FROM issue_categories" in sql:
            # musicforge#1 cached; prntd#2 absent
            return [{"repo": "musicforge", "number": 1,
                     "title": "Fix crash", "category": "bug"}]
        if "INSERT INTO issue_categories" in sql:
            inserts.append(args)
            return []
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_fetch = patch(mod, _fetch_open_issues=lambda t, u: _CAT_ITEMS)
    saved = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = "ghp_test"
    try:
        h = invoke(mod, "/api/todos?categorize=1")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        b = h.body
        assert b.get("categorized") is True
        assert b["classified_now"] == 0, "reader must not classify"
        assert not inserts, "reader must not write cache"
        mf = b["projects"]["musicforge"][0]
        pr = b["projects"]["prntd"][0]
        assert mf["category"] == "bug", f"cache miss: {mf}"
        assert pr["category"] == "uncategorized", f"uncached should be uncategorized: {pr}"
        assert b["pending"] == 1
    finally:
        if saved is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = saved
        restore_fetch()
        restore_q()
        restore_auth()


@test("todos categorize: admin classifies uncached via classify_batch")
def _():
    import os
    mod = load_endpoint("web/api/todos.py", "endpoint_todos_cat_admin")
    restore_auth = patch(mod, is_authenticated=lambda _: True,
                         get_role=lambda _: "admin")
    inserts = []

    def fake_turso(sql, args=None):
        if "FROM project_aliases" in sql:
            return []
        if "SELECT repo, number, title, category FROM issue_categories" in sql:
            return [{"repo": "musicforge", "number": 1,
                     "title": "Fix crash", "category": "bug"}]
        if "INSERT INTO issue_categories" in sql:
            inserts.append(args)
            return []
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_fetch = patch(mod, _fetch_open_issues=lambda t, u: _CAT_ITEMS)
    restore_cls = patch(mod, classify_batch=lambda issues: {"prntd#2": "feature"})
    saved = os.environ.get("GITHUB_TOKEN")
    saved_key = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["GITHUB_TOKEN"] = "ghp_test"
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    try:
        h = invoke(mod, "/api/todos?categorize=1")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        b = h.body
        assert b["classified_now"] == 1, f"admin should classify the 1 uncached: {b}"
        assert b["pending"] == 0
        pr = b["projects"]["prntd"][0]
        assert pr["category"] == "feature", f"not classified: {pr}"
        assert inserts and inserts[0][0] == "prntd" and inserts[0][3] == "feature", f"cache not written: {inserts}"
    finally:
        if saved is None:
            os.environ.pop("GITHUB_TOKEN", None)
        else:
            os.environ["GITHUB_TOKEN"] = saved
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key
        restore_cls()
        restore_fetch()
        restore_q()
        restore_auth()


# === beacon.py ===

GOOD_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
           "AppleWebKit/537.36 Chrome/126.0 Safari/537.36")
GOOD_HEADERS = {
    "user-agent": GOOD_UA,
    "origin": "https://www.ibuild4you.com",
    "x-forwarded-for": "203.0.113.9, 10.0.0.1",
    "x-vercel-ip-country": "US",
}


@test("beacon: valid pageview builds a clean row")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_ok")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    body = json.dumps({"path": "/pricing?token=secret#frag",
                       "ref": "https://www.google.com/search?q=x"}).encode()
    row = mod.parse_event(GOOD_HEADERS, body)
    assert row, "valid hit was dropped"
    assert row["site"] == "ibuild4you.com", f"www not stripped: {row['site']}"
    assert row["path"] == "/pricing", f"query/frag not stripped: {row['path']}"
    assert row["referrer"] == "google.com", f"referrer not host-only: {row['referrer']}"
    assert row["country"] == "US"
    assert row["device"] == "desktop"
    assert row["event"] == "pageview"
    assert len(row["visitor_hash"]) == 16
    assert "203.0.113.9" not in json.dumps(row), "raw IP leaked into row"


@test("beacon: self-referral stored as null referrer")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_selfref")
    body = json.dumps({"path": "/a", "ref": "https://ibuild4you.com/b"}).encode()
    row = mod.parse_event(GOOD_HEADERS, body)
    assert row and row["referrer"] is None, f"got {row}"


# === beacon: automation labelling (issue #52) ===

@test("beacon #52: a normal browser hit is NOT flagged")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_agent_human")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    row = mod.parse_event(GOOD_HEADERS, json.dumps({"path": "/"}).encode())
    assert row, "valid hit was dropped"
    assert row["agent"] == 0, f"human traffic flagged as automation: {row}"
    # An explicitly-false webdriver flag must not trip the label either.
    row2 = mod.parse_event(
        GOOD_HEADERS, json.dumps({"path": "/", "wd": False}).encode())
    assert row2["agent"] == 0, f"wd:false flagged: {row2}"
    row3 = mod.parse_event(
        GOOD_HEADERS, json.dumps({"path": "/", "wd": 0}).encode())
    assert row3["agent"] == 0, f"wd:0 flagged: {row3}"


@test("beacon #52: navigator.webdriver is stored as a label, not dropped")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_agent_wd")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    for payload in ({"path": "/", "wd": 1}, {"path": "/", "wd": True},
                    {"path": "/", "wd": "true"}, {"path": "/", "agent": 1}):
        row = mod.parse_event(GOOD_HEADERS, json.dumps(payload).encode())
        # Labelled, NOT dropped — the whole design of #52. A discarded row
        # makes automation volume invisible; a labelled one is recomputable.
        assert row is not None, f"automation hit was dropped, not labelled: {payload}"
        assert row["agent"] == 1, f"automation not flagged: {payload} -> {row}"


@test("beacon #52: X-Test-Agent header flags header-capable callers")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_agent_header")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    h = {**GOOD_HEADERS, mod.AGENT_HEADER: "1"}
    row = mod.parse_event(h, json.dumps({"path": "/"}).encode())
    assert row and row["agent"] == 1, f"header not honored: {row}"
    # Falsey spellings must not flag.
    for value in ("", "0", "false", "off"):
        h2 = {**GOOD_HEADERS, mod.AGENT_HEADER: value}
        row2 = mod.parse_event(h2, json.dumps({"path": "/"}).encode())
        assert row2["agent"] == 0, f"{value!r} flagged as automation: {row2}"


@test("beacon #52: the agent flag reaches the INSERT")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_agent_insert")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        invoke_post(mod, "/api/beacon",
                    json.dumps({"path": "/x", "wd": 1}).encode(), GOOD_HEADERS)
        inserts = [c for c in captured if "INSERT INTO page_views" in c[0]]
        assert len(inserts) == 1, f"expected 1 insert, got {captured}"
        sql, args = inserts[0]
        assert "agent" in sql, f"agent column not in INSERT: {sql}"
        assert args[-1] == 1, f"agent flag not last arg / not 1: {args}"

        captured.clear()
        invoke_post(mod, "/api/beacon",
                    json.dumps({"path": "/x"}).encode(), GOOD_HEADERS)
        args2 = [c for c in captured if "INSERT INTO page_views" in c[0]][0][1]
        assert args2[-1] == 0, f"human row not agent=0: {args2}"
    finally:
        restore()


@test("beacon #52: a missing agent column keeps humans, drops automation, says so")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_agent_migration")
    calls = []

    def unmigrated(sql, args=None):
        calls.append((sql, args or []))
        if "agent" in sql:
            raise RuntimeError("SQLITE_ERROR: table page_views has no column "
                               "named agent")
        return []

    restore = patch_turso_query(mod, unmigrated)
    try:
        base = {"ts": "2026-08-17T00:00:00Z", "site": "x.com", "path": "/",
                "referrer": None, "country": "US", "device": "desktop",
                "event": "pageview", "visitor_hash": "abc"}
        # Human row survives the window on the legacy column shape.
        mod.insert_row({**base, "agent": 0})
        legacy = [c for c in calls if "INSERT INTO page_views" in c[0]
                  and "agent" not in c[0]]
        assert len(legacy) == 1, f"human row lost during migration gap: {calls}"
        assert len(legacy[0][1]) == 8, f"legacy shape wrong: {legacy[0][1]}"

        # An automation row must NEVER land unlabelled — dropping it is the
        # point of #52. Otherwise the gap silently reintroduces the pollution.
        calls.clear()
        mod.insert_row({**base, "agent": 1})
        legacy2 = [c for c in calls if "INSERT INTO page_views" in c[0]
                   and "agent" not in c[0]]
        assert not legacy2, f"automation row written unlabelled: {calls}"
    finally:
        restore()


@test("beacon: drops bot user-agents and missing UA")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_bots")
    body = json.dumps({"path": "/"}).encode()
    for ua in ["Googlebot/2.1", "python-requests/2.31", "curl/8.4",
               "HeadlessChrome/126", ""]:
        h = {**GOOD_HEADERS, "user-agent": ua}
        assert mod.parse_event(h, body) is None, f"UA not dropped: {ua!r}"


@test("beacon: drops missing, localhost, and malformed origins")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_origins")
    body = json.dumps({"path": "/"}).encode()
    for origin in ["", "http://localhost:3000", "http://127.0.0.1:8080",
                   "https://dev.local", "not a url"]:
        h = {**GOOD_HEADERS, "origin": origin}
        h.pop("referer", None)
        assert mod.parse_event(h, body) is None, f"origin not dropped: {origin!r}"


@test("beacon: drops unknown event types and bad payloads")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_events")
    # `login` used to be the not-allowed example here; it joined ALLOWED_EVENTS
    # in issue #10, so the drop case is now an event that is still unknown.
    bad = [json.dumps({"path": "/", "event": "signup"}).encode(),
           json.dumps({"path": "/", "event": "click"}).encode(),
           json.dumps({"path": "no-slash"}).encode(),
           json.dumps(["not", "a", "dict"]).encode(),
           b"not json at all"]
    for body in bad:
        assert mod.parse_event(GOOD_HEADERS, body) is None, f"not dropped: {body!r}"


@test("beacon: login event is accepted and inserted (issue #10)")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_login_event")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    body = json.dumps({"path": "/login/admin", "event": "login"}).encode()
    row = mod.parse_event(GOOD_HEADERS, body)
    assert row, "login event was dropped"
    assert row["event"] == "login", f"event not preserved: {row}"
    assert row["path"] == "/login/admin", f"path not preserved: {row}"

    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke_post(mod, "/api/beacon", body, GOOD_HEADERS)
        assert h.status_code == 204, f"got {h.status_code}"
        inserts = [c for c in captured if "INSERT INTO page_views" in c[0]]
        assert len(inserts) == 1, f"expected 1 insert, got {captured}"
        assert "login" in inserts[0][1], f"event not in args: {inserts[0][1]}"
        assert "/login/admin" in inserts[0][1], f"path not in args: {inserts[0][1]}"
    finally:
        restore()


@test("beacon: visitor hash varies by IP, never exposes it")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_hash")
    os.environ.setdefault("BEACON_SALT", "test-salt")
    a = mod._visitor_hash("203.0.113.9", GOOD_UA)
    b = mod._visitor_hash("203.0.113.10", GOOD_UA)
    a2 = mod._visitor_hash("203.0.113.9", GOOD_UA)
    assert a != b, "different IPs should hash differently"
    assert a == a2, "same-day same-input hash should be stable"
    assert "203" not in a


@test("beacon: BEACON_SALT is the only salt of record, no AUTH_SECRET fallback")
def _():
    import hashlib
    import os
    import time
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_salt")
    saved = {k: os.environ.get(k) for k in ("BEACON_SALT", "AUTH_SECRET")}
    try:
        os.environ["BEACON_SALT"] = "beacon-salt-v1"
        os.environ["AUTH_SECRET"] = "auth-secret-A"
        ip, ua = "203.0.113.9", GOOD_UA
        got = mod._visitor_hash(ip, ua)
        # Byte-identical to an independent sha256 over BEACON_SALT (not AUTH_SECRET).
        day = time.strftime("%Y-%m-%d", time.gmtime())
        want = hashlib.sha256(
            f"beacon-salt-v1|{day}|{ip}|{ua}".encode()).hexdigest()[:16]
        assert got == want, f"salt not BEACON_SALT-derived: {got} != {want}"
        # Continuity: rotating AUTH_SECRET must NOT change the hash while
        # BEACON_SALT is set.
        os.environ["AUTH_SECRET"] = "auth-secret-B"
        assert mod._visitor_hash(ip, ua) == got, "AUTH_SECRET rotation moved the hash"
        # §2.3: BEACON_SALT unset must fail closed (None), never silently
        # fall back to AUTH_SECRET or any other secret.
        del os.environ["BEACON_SALT"]
        assert mod._visitor_hash(ip, ua) is None, (
            "BEACON_SALT-unset must return None, not fall back to AUTH_SECRET")
        # parse_event must drop the hit (still opaque) rather than crash or
        # insert a hash salted with something else.
        body = json.dumps({"path": "/"}).encode()
        assert mod.parse_event(GOOD_HEADERS, body) is None, (
            "parse_event must drop when BEACON_SALT is unset")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@test("beacon: do_POST inserts row and returns 204; turso failure still 204")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_post")
    captured_sql = []

    def fake_turso(sql, args=None):
        captured_sql.append((sql, args))
        return []

    restore = patch_turso_query(mod, fake_turso)
    body = json.dumps({"path": "/x"}).encode()
    try:
        h = invoke_post(mod, "/api/beacon", body, GOOD_HEADERS)
        assert h.status_code == 204, f"got {h.status_code}"
        inserts = [c for c in captured_sql if "INSERT INTO page_views" in c[0]]
        assert len(inserts) == 1, f"expected 1 insert, got {captured_sql}"
        # 8 original columns + `agent` (issue #52).
        assert len(inserts[0][1]) == 9

        def boom(sql, args=None):
            raise RuntimeError("turso down")
        patch_turso_query(mod, boom)
        h2 = invoke_post(mod, "/api/beacon", body, GOOD_HEADERS)
        assert h2.status_code == 204, f"error leaked: {h2.status_code}"
    finally:
        restore()


@test("beacon: dropped hit inserts nothing but still 204")
def _():
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_post_drop")
    captured_sql = []

    def fake_turso(sql, args=None):
        captured_sql.append(sql)
        return []

    restore = patch_turso_query(mod, fake_turso)
    try:
        h = invoke_post(mod, "/api/beacon", json.dumps({"path": "/"}).encode(),
                        {**GOOD_HEADERS, "user-agent": "Googlebot"})
        assert h.status_code == 204
        assert not captured_sql, f"bot hit reached the DB: {captured_sql}"
    finally:
        restore()


# === visitor_overview.py ===

@test("visitor_overview: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, is_authenticated=lambda _: False)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/visitor_overview")
        assert h.status_code == 401, f"got {h.status_code}"
    finally:
        restore()


@test("visitor_overview: 200 shape, since bound, int coercion")
def _():
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_shape")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "GROUP BY date, site" in sql:
            return [{"date": "2026-07-01", "site": "prntd.org",
                     "views": "12", "uniques": "3"}]
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)

    def restore():
        restore_a()
        restore_q()
    try:
        h = invoke(mod, "/api/visitor_overview?since=2026-06-05")
        assert h.status_code == 200, f"got {h.status_code}"
        body = h.body
        for key in ("daily", "paths", "referrers", "countries"):
            assert key in body, f"missing {key}"
        assert body["daily"][0]["views"] == 12, f"views not int: {body['daily']}"
        assert body["daily"][0]["uniques"] == 3
        assert all("2026-06-05" in a for _, a in captured), "since bound missing"
        # The four page-view queries must all pin event = 'pageview'. The login
        # queries added in issue #10 deliberately filter event = 'login'
        # instead, so scope the assertion to the non-login SQL.
        pv = [s for s, _ in captured if "'login'" not in s]
        assert len(pv) == 4, f"expected 4 pageview queries, got {len(pv)}"
        assert all("pageview" in s for s in pv), "event filter missing"
    finally:
        restore()


# === visitor_overview: login events (issue #10) ===

def _visov_logins(login_day_rows, login_path_rows, path="/api/visitor_overview"):
    """Invoke visitor_overview with the two login queries stubbed.
    Returns (captured_sql_list, response_body)."""
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_logins")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "'login'" not in sql:
            return []
        return login_path_rows if "GROUP BY path" in sql else login_day_rows

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)
    try:
        h = invoke(mod, path)
    finally:
        restore_a()
        restore_q()
    return captured, h


@test("visitor_overview: logins block — int counts, roles from paths, total")
def _():
    captured, h = _visov_logins(
        [{"date": "2026-07-28", "count": "2"}, {"date": "2026-07-29", "count": "5"}],
        [{"path": "/login/admin", "count": "5"}, {"path": "/login/reader", "count": "2"}],
    )
    assert h.status_code == 200, f"got {h.status_code}"
    logins = h.body.get("logins")
    assert logins is not None, f"no logins block: {sorted(h.body)}"
    assert logins["by_day"] == [{"date": "2026-07-28", "count": 2},
                                {"date": "2026-07-29", "count": 5}], logins["by_day"]
    assert logins["by_role"] == [{"role": "admin", "count": 5},
                                 {"role": "reader", "count": 2}], logins["by_role"]
    assert logins["total"] == 7, f"total not summed as int: {logins['total']!r}"
    for row in logins["by_day"] + logins["by_role"]:
        assert isinstance(row["count"], int), f"count not int: {row}"
    assert isinstance(logins["total"], int), "total not int"


@test("visitor_overview: malformed login path → role 'unknown', never null")
def _():
    _, h = _visov_logins(
        [{"date": "2026-07-29", "count": "3"}],
        [{"path": "/login", "count": "1"}, {"path": "/", "count": "1"},
         {"path": None, "count": "1"}],
    )
    assert h.status_code == 200, f"got {h.status_code}"
    roles = h.body["logins"]["by_role"]
    assert roles == [{"role": "unknown", "count": 3}], roles


@test("visitor_overview: empty logins block is present with int zero total")
def _():
    _, h = _visov_logins([], [])
    logins = h.body["logins"]
    assert logins == {"by_day": [], "by_role": [], "total": 0}, logins


@test("visitor_overview: login rows can't reach daily/paths (pageview filter stays)")
def _():
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_nomix")
    captured = []

    def fake_turso(sql, args=None):
        captured.append(sql)
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)
    try:
        h = invoke(mod, "/api/visitor_overview")
        assert h.status_code == 200, f"got {h.status_code}"
        pv = [s for s in captured if "'login'" not in s]
        assert len(pv) == 4, f"expected 4 pageview queries, got {pv}"
        for s in pv:
            assert "event = 'pageview'" in s, f"pageview filter dropped: {s}"
        lg = [s for s in captured if "'login'" in s]
        assert len(lg) == 2, f"expected 2 login queries, got {lg}"
        for s in lg:
            assert "event = 'login'" in s, f"login query not event-scoped: {s}"
            assert "pageview" not in s, f"login query mixes pageviews: {s}"
    finally:
        restore_a()
        restore_q()


@test("visitor_overview #52: every query excludes agent-flagged rows")
def _():
    mod = load_endpoint("web/api/visitor_overview.py", "endpoint_visov_agent")
    captured = []

    def fake_turso(sql, args=None):
        captured.append(sql)
        return []

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: True)
    try:
        h = invoke(mod, "/api/visitor_overview")
        assert h.status_code == 200, f"got {h.status_code}"
        assert len(captured) == 6, f"expected 6 queries, got {captured}"
        for sql in captured:
            assert "agent = 0" in sql, (
                f"automation traffic not excluded from a visitor read: {sql}")
    finally:
        restore_a()
        restore_q()


@test("day #52: the visitors block excludes agent-flagged rows")
def _():
    import re
    src = open("web/api/day.py").read()
    m = re.search(r"SELECT site, COUNT\(\*\) AS views FROM page_views.*?\"\s*\)",
                  src, re.S)
    assert m, "page_views query not found in day.py — did it move?"
    q = m.group(0)
    assert "agent = 0" in q, f"day page counts automation as visitors: {q}"


@test("visitor_overview: login queries honor since/until like the rest")
def _():
    captured, h = _visov_logins(
        [], [], path="/api/visitor_overview?since=2026-06-05&until=2026-07-29")
    assert h.status_code == 200, f"got {h.status_code}"
    lg = [(s, a) for s, a in captured if "'login'" in s]
    assert len(lg) == 2, f"expected 2 login queries, got {lg}"
    for s, a in lg:
        assert a == ["2026-06-05", "2026-07-29"], f"bounds not passed: {a}"
        assert s.count("substr(ts, 1, 10)") >= 2, f"bounds not in SQL: {s}"


# === project_metadata.py (issue #23) ===

def _meta_mod(name: str, fake_turso, role="admin"):
    """Load project_metadata.py with turso + auth patched. Returns (mod, restore)."""
    mod = load_endpoint("web/api/project_metadata.py", name)
    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod,
                      is_authenticated=lambda _: role is not None,
                      get_role=lambda _: role)

    def restore():
        restore_a()
        restore_q()
    return mod, restore


@test("project_metadata: GET 401 when not authenticated")
def _():
    mod, restore = _meta_mod("endpoint_meta_unauth", lambda *a, **kw: [], role=None)
    try:
        h = invoke(mod, "/api/project_metadata")
        assert h.status_code == 401, f"got {h.status_code}"
    finally:
        restore()


@test("project_metadata: GET returns projects keyed by name, private as bool")
def _():
    rows = [{"project": "byside", "category": "Collabs", "private": "1",
             "status": "active", "public_counts": "1",
             "updated_at": "2026-07-14T00:00:00Z"}]
    mod, restore = _meta_mod("endpoint_meta_get", lambda *a, **kw: rows, role="reader")
    try:
        h = invoke(mod, "/api/project_metadata")
        assert h.status_code == 200, f"got {h.status_code}"
        m = h.body["projects"]["byside"]
        assert m["private"] is True, f"private not coerced to bool: {m}"
        assert m["public_counts"] is True, f"public_counts not coerced to bool: {m}"
        assert m["category"] == "Collabs" and m["status"] == "active"
    finally:
        restore()


@test("project_metadata: POST sets public_counts as a boolean, rejects non-bool")
def _():
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "project_aliases" in sql:
            return []
        if sql.startswith("SELECT project"):
            return [{"project": "split-recording", "category": None, "private": 0,
                     "status": "active", "public_counts": 1, "updated_at": "now"}]
        return []

    mod, restore = _meta_mod("endpoint_meta_pubcounts", fake_turso)
    try:
        h = invoke_post(mod, "/api/project_metadata",
                        {"project": "split-recording", "public_counts": True})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["metadata"]["public_counts"] is True, h.body
        sql = [(s, a) for s, a in captured
               if s.startswith("INSERT INTO project_metadata")][0][0]
        assert "public_counts=excluded.public_counts" in sql, sql
        # A public_counts-only POST must not clobber siblings.
        assert "status=excluded.status" not in sql, sql

        h = invoke_post(mod, "/api/project_metadata",
                        {"project": "split-recording", "public_counts": "yes"})
        assert h.status_code == 400, f"non-bool accepted: {h.status_code}"
    finally:
        restore()


@test("project_metadata: POST 403 for reader, 401 for anonymous")
def _():
    mod, restore = _meta_mod("endpoint_meta_reader", lambda *a, **kw: [], role="reader")
    try:
        h = invoke_post(mod, "/api/project_metadata", {"project": "x", "status": "dormant"})
        assert h.status_code == 403, f"reader got {h.status_code}, expected 403"
    finally:
        restore()

    mod, restore = _meta_mod("endpoint_meta_anon", lambda *a, **kw: [], role=None)
    try:
        h = invoke_post(mod, "/api/project_metadata", {"project": "x", "status": "dormant"})
        assert h.status_code == 401, f"anon got {h.status_code}, expected 401"
    finally:
        restore()


@test("project_metadata: POST folds an alias to its canonical project")
def _():
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "SELECT canonical FROM project_aliases" in sql:
            return [{"canonical": "byside"}]
        if "SELECT alias FROM project_aliases" in sql:
            return [{"alias": "offer-builder"}]
        if sql.startswith("SELECT project"):
            return [{"project": "byside", "category": None, "private": 0,
                     "status": "dormant", "updated_at": "now"}]
        return []

    mod, restore = _meta_mod("endpoint_meta_alias", fake_turso)
    try:
        h = invoke_post(mod, "/api/project_metadata",
                        {"project": "offer-builder", "status": "dormant"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["project"] == "byside", f"alias not folded: {h.body}"
        upserts = [(s, a) for s, a in captured if s.startswith("INSERT INTO project_metadata")]
        assert upserts, "no upsert emitted"
        assert upserts[0][1][0] == "byside", f"wrote alias, not canonical: {upserts[0][1]}"
    finally:
        restore()


@test("project_metadata: POST partial update touches only the sent field")
def _():
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if "project_aliases" in sql:
            return []
        if sql.startswith("SELECT project"):
            return [{"project": "musicforge", "category": "Music", "private": 0,
                     "status": "active", "updated_at": "now"}]
        return []

    mod, restore = _meta_mod("endpoint_meta_partial", fake_turso)
    try:
        h = invoke_post(mod, "/api/project_metadata",
                        {"project": "musicforge", "category": "Music"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        sql, args = [(s, a) for s, a in captured
                     if s.startswith("INSERT INTO project_metadata")][0]
        # A category-only POST must not reset status/private on an existing row.
        assert "status=excluded.status" not in sql, f"status clobbered: {sql}"
        assert "private=excluded.private" not in sql, f"private clobbered: {sql}"
        assert "category=excluded.category" in sql, f"category not updated: {sql}"
    finally:
        restore()


@test("project_metadata: POST rejects bad category, status, private, and empty body")
def _():
    mod, restore = _meta_mod("endpoint_meta_validate", lambda *a, **kw: [])
    try:
        cases = [
            ({"project": "p", "category": "Nonsense"}, "bad category"),
            ({"project": "p", "status": "archived"}, "bad status"),
            ({"project": "p", "private": "yes"}, "private as string"),
            ({"project": "p"}, "no fields"),
            ({"status": "active"}, "no project"),
        ]
        for body, label in cases:
            h = invoke_post(mod, "/api/project_metadata", body)
            assert h.status_code == 400, f"{label}: got {h.status_code}, expected 400"

        h = invoke_post(mod, "/api/project_metadata", b"{not json")
        assert h.status_code == 400, f"malformed json: got {h.status_code}"
    finally:
        restore()


@test("project_metadata: POST accepts an explicit null category (clears it)")
def _():
    def fake_turso(sql, args=None):
        if "project_aliases" in sql:
            return []
        if sql.startswith("SELECT project"):
            return [{"project": "p", "category": None, "private": 0,
                     "status": "active", "updated_at": "now"}]
        return []

    mod, restore = _meta_mod("endpoint_meta_null_cat", fake_turso)
    try:
        h = invoke_post(mod, "/api/project_metadata", {"project": "p", "category": None})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["metadata"]["category"] is None
    finally:
        restore()


@test("overview: project_metadata rides along, and a missing table isn't fatal")
def _():
    def fake_turso(sql, args=None):
        if "FROM project_metadata" in sql:
            raise RuntimeError("no such table: project_metadata")
        return []

    mod = load_endpoint("web/api/overview.py", "endpoint_overview_meta")
    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))
    try:
        h = invoke(mod, "/api/overview")
        # The table not existing yet must degrade to {}, never 503 the page.
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["project_metadata"] == {}, f"got {h.body['project_metadata']}"
    finally:
        restore_a()
        restore_q()


@test("overview: project_metadata folds aliases onto the canonical name")
def _():
    def fake_turso(sql, args=None):
        if "SELECT alias, canonical FROM project_aliases" in sql:
            return [{"alias": "offer-builder", "canonical": "byside"}]
        if "FROM project_metadata" in sql:
            return [{"project": "offer-builder", "category": "Collabs",
                     "private": 1, "status": "dormant"}]
        return []

    mod = load_endpoint("web/api/overview.py", "endpoint_overview_meta_alias")
    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))
    try:
        h = invoke(mod, "/api/overview")
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        meta = h.body["project_metadata"]
        assert "byside" in meta, f"alias not folded: {meta}"
        assert "offer-builder" not in meta, f"alias leaked: {meta}"
        assert meta["byside"]["private"] is True
    finally:
        restore_a()
        restore_q()


# === auth_helper / login / callback (Phase 2 OAuth) ===

import auth_helper  # noqa: E402


def _ah_sign(payload: dict, secret: str) -> str:
    """Mint a token the same way auth_helper.make_token does:
    urlsafe_b64(json).hexhmac, joined by a dot. Used to hand-build legacy /
    malformed / expired tokens (and states) the public make_* helpers won't.
    """
    import base64
    import hashlib
    import hmac

    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def _save_env(*keys):
    """Return (restore_fn) that resets the named env vars to their current values."""
    import os

    saved = {k: os.environ.get(k) for k in keys}

    def restore():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return restore


def _cookie_token(captured):
    """Pull the gc_session token out of a captured Set-Cookie header, or None."""
    prefix = auth_helper.COOKIE_NAME + "="
    for k, v in captured.response_headers:
        if k == "Set-Cookie" and v.startswith(prefix):
            return v.split(";", 1)[0][len(prefix):]
    return None


def _location(captured):
    for k, v in captured.response_headers:
        if k == "Location":
            return v
    return None


def _fake_id_token(claims: dict) -> str:
    """Unsigned JWT: header.payload.sig, each segment base64url WITHOUT padding
    (strip '='). Pins that the callback pads before urlsafe_b64decode."""
    import base64

    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none', 'typ': 'JWT'})}.{seg(claims)}.sig"


# --- auth_helper: make_token / verify_token ---

def _mint(role="admin", email="nico@example.com", secret="test-secret", exp_delta=3600):
    """Hand-sign a NEW-shape {exp, role, email} token (bypasses make_token so the
    verify_token assertions run even before make_token grows an `email` param)."""
    import time

    return _ah_sign(
        {"exp": int(time.time()) + exp_delta, "role": role, "email": email}, secret)


@test("auth_helper: verify_token returns the full payload dict, not the role string")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        payload = auth_helper.verify_token(_mint("admin", "nico@example.com"))
        assert isinstance(payload, dict), (
            f"verify_token must return the payload dict, got {payload!r}")
        assert payload["role"] == "admin", payload
        assert payload["email"] == "nico@example.com", payload
        assert "exp" in payload, payload
    finally:
        restore()


@test("auth_helper: make_token(role, email=) round-trips through verify_token")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        # make_token MUST accept an email arg; a TypeError here IS the failure.
        tok = auth_helper.make_token("admin", email="nico@example.com")
        payload = auth_helper.verify_token(tok)
        assert isinstance(payload, dict) and payload["email"] == "nico@example.com", payload
    finally:
        restore()


@test("auth_helper: password token (email=None) still verifies (key-presence)")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        # email KEY present, value null — the password/preview break-glass shape.
        tok = _ah_sign(
            {"exp": int(time.time()) + 3600, "role": "admin", "email": None},
            "test-secret")
        payload = auth_helper.verify_token(tok)
        assert isinstance(payload, dict), f"email=None token rejected: {payload!r}"
        assert payload["role"] == "admin", payload
        assert "email" in payload, f"email key must be present even when null: {payload}"
        assert payload["email"] is None, payload
    finally:
        restore()


@test("auth_helper: legacy {exp,role} token (no email key) → None")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        legacy = _ah_sign({"exp": int(time.time()) + 3600, "role": "admin"}, "test-secret")
        assert auth_helper.verify_token(legacy) is None, (
            "legacy no-email cookie must be rejected (decision 3)")
    finally:
        restore()


@test("auth_helper: token missing role key → None (fail-open removed)")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        no_role = _ah_sign(
            {"exp": int(time.time()) + 3600, "email": "nico@example.com"}, "test-secret")
        assert auth_helper.verify_token(no_role) is None, (
            "missing role must not default to admin")
    finally:
        restore()


@test("auth_helper: tampered signature → None")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        tok = _mint("admin", "nico@example.com")
        bad = tok[:-1] + ("a" if tok[-1] != "a" else "b")
        assert auth_helper.verify_token(bad) is None, "tampered sig accepted"
    finally:
        restore()


@test("auth_helper: expired token → None")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        expired = _ah_sign(
            {"exp": int(time.time()) - 10, "role": "admin", "email": "nico@example.com"},
            "test-secret")
        assert auth_helper.verify_token(expired) is None, "expired token accepted"
    finally:
        restore()


@test("auth_helper: get_identity returns the payload dict (email + role)")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        headers = {"cookie": f"{auth_helper.COOKIE_NAME}={_mint('admin', 'nico@example.com')}"}
        ident = auth_helper.get_identity(headers)
        assert isinstance(ident, dict), f"get_identity must return a dict, got {ident!r}"
        assert ident["role"] == "admin" and ident["email"] == "nico@example.com", ident
    finally:
        restore()


@test("auth_helper: get_role returns the role string")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        tok = _ah_sign(
            {"exp": int(time.time()) + 3600, "role": "reader", "email": None},
            "test-secret")
        headers = {"cookie": f"{auth_helper.COOKIE_NAME}={tok}"}
        assert auth_helper.get_role(headers) == "reader", auth_helper.get_role(headers)
    finally:
        restore()


@test("auth_helper: set_cookie_header / clear_cookie_header use SameSite=Lax not Strict")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        # These two run against current code (no new signature needed) → red on Strict now.
        clear_hdr = auth_helper.clear_cookie_header()
        assert "SameSite=Lax" in clear_hdr, f"clear_cookie not Lax: {clear_hdr}"
        assert "SameSite=Strict" not in clear_hdr, f"clear_cookie still Strict: {clear_hdr}"
        set_hdr = auth_helper.set_cookie_header("admin")
        assert "SameSite=Lax" in set_hdr, f"set_cookie not Lax: {set_hdr}"
        assert "SameSite=Strict" not in set_hdr, f"set_cookie still Strict: {set_hdr}"
        # And it must thread email through (TypeError here = must-accept-email).
        with_email = auth_helper.set_cookie_header("admin", email="nico@example.com")
        assert "SameSite=Lax" in with_email, with_email
        tok = with_email.split(";", 1)[0][len(auth_helper.COOKIE_NAME) + 1:]
        assert auth_helper.verify_token(tok)["email"] == "nico@example.com", (
            "email not threaded into the cookie token")
    finally:
        restore()


# --- auth_helper: state (CSRF) ---

@test("auth_helper: make_state/verify_state round-trips")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        state = auth_helper.make_state()
        assert state, "make_state returned nothing"
        assert auth_helper.verify_state(state), "fresh state failed to verify"
    finally:
        restore()


@test("auth_helper: verify_state rejects a tampered state")
def _():
    import os
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        state = auth_helper.make_state()
        bad = state[:-1] + ("a" if state[-1] != "a" else "b")
        assert not auth_helper.verify_state(bad), "tampered state accepted"
    finally:
        restore()


@test("auth_helper: verify_state rejects an expired state")
def _():
    import os
    import time
    restore = _save_env("AUTH_SECRET")
    os.environ["AUTH_SECRET"] = "test-secret"
    try:
        expired = _ah_sign(
            {"exp": int(time.time()) - 10, "nonce": "deadbeef"}, "test-secret")
        assert not auth_helper.verify_state(expired), "expired state accepted"
    finally:
        restore()


# --- login.py ---

@test("login GET ?provider=google: 302 to Google authorize URL")
def _():
    import os
    from urllib.parse import quote
    mod = load_endpoint("web/api/login.py", "endpoint_login_google")
    restore = _save_env("AUTH_SECRET", "GOOGLE_CLIENT_ID", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
    os.environ.pop("VERCEL_ENV", None)
    try:
        h = invoke(mod, "/api/login?provider=google")
        assert h.status_code == 302, f"got {h.status_code}"
        loc = _location(h)
        assert loc, "no Location header"
        assert "accounts.google.com" in loc, loc
        assert "test-client-id" in loc, loc
        assert quote("https://prompt-labs.org/api/callback", safe="") in loc, loc
        assert "response_type=code" in loc, loc
        assert "openid" in loc and "email" in loc, loc
        # The state param must be a real signed state, not a literal placeholder.
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(loc).query)
        assert qs.get("state"), f"no state param: {loc}"
        assert auth_helper.verify_state(qs["state"][0]), "emitted state does not verify"
    finally:
        restore()


@test("login GET bare unauthenticated: 401 with password_login=true, google_login=false (non-prod)")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_bare_nonprod")
    restore = _save_env("AUTH_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ.pop("VERCEL_ENV", None)
    try:
        h = invoke(mod, "/api/login")
        assert h.status_code == 401, f"got {h.status_code}"
        assert h.body.get("authenticated") is False, h.body
        assert h.body.get("password_login") is True, (
            f"password_login must be true off-production: {h.body}")
        assert h.body.get("google_login") is False, (
            # issue #30: the OAuth redirect is pinned to prod, so previews
            # must not offer a Google button that silently logs you into prod.
            f"google_login must be false off-production: {h.body}")
    finally:
        restore()


@test("login GET bare unauthenticated: password_login=false, google_login=true in production")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_bare_prod")
    restore = _save_env("AUTH_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ["VERCEL_ENV"] = "production"
    try:
        h = invoke(mod, "/api/login")
        assert h.status_code == 401, f"got {h.status_code}"
        assert h.body.get("password_login") is False, (
            f"password_login must be false in production: {h.body}")
        assert h.body.get("google_login") is True, (
            f"google_login must be true in production: {h.body}")
    finally:
        restore()


@test("login GET bare authenticated: 200 with role + email")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_bare_auth")
    restore = _save_env("AUTH_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ.pop("VERCEL_ENV", None)
    try:
        tok = _mint("admin", "nico@example.com")
        h = invoke(mod, "/api/login",
                   headers={"cookie": f"{auth_helper.COOKIE_NAME}={tok}"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body.get("authenticated") is True, h.body
        assert h.body.get("role") == "admin", h.body
        assert h.body.get("email") == "nico@example.com", h.body
    finally:
        restore()


def _post_login(mod, body):
    """POST to login with a CAPITALIZED Content-Length header.

    login.py reads `self.headers.get("Content-Length")` (capitalized), but
    invoke_post only injects a lowercase `content-length`. On the plain-dict
    test headers that lookup is case-sensitive, so without this the handler
    sees an empty body and every password login spuriously 401s. Supplying the
    capitalized header (merged before invoke_post's lowercase one) is what lets
    the real password path be exercised.
    """
    clen = str(len(json.dumps(body).encode()))
    return invoke_post(mod, "/api/login", body, headers={"Content-Length": clen})


@test("login POST password: 403 in production")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_post_prod")
    restore = _save_env("AUTH_SECRET", "AUTH_READ_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ.pop("AUTH_READ_SECRET", None)
    os.environ["VERCEL_ENV"] = "production"
    try:
        # Correct password + production must STILL be refused (gating, not auth).
        h = _post_login(mod, {"password": "test-secret"})
        assert h.status_code == 403, (
            f"password login must be disabled in production, got {h.status_code}")
    finally:
        restore()


@test("login POST password: correct password → 200 + cookie (non-prod)")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_post_ok")
    restore = _save_env("AUTH_SECRET", "AUTH_READ_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ.pop("AUTH_READ_SECRET", None)
    os.environ.pop("VERCEL_ENV", None)
    try:
        h = _post_login(mod, {"password": "test-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert _cookie_token(h), "no Set-Cookie on successful login"
    finally:
        restore()


@test("login POST password: wrong password → 401 (non-prod, real body)")
def _():
    import os
    mod = load_endpoint("web/api/login.py", "endpoint_login_post_wrong")
    restore = _save_env("AUTH_SECRET", "AUTH_READ_SECRET", "VERCEL_ENV")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ.pop("AUTH_READ_SECRET", None)
    os.environ.pop("VERCEL_ENV", None)
    try:
        # A non-empty, WRONG password (not an empty body) must 401.
        h = _post_login(mod, {"password": "definitely-not-the-secret"})
        assert h.status_code == 401, f"got {h.status_code}"
        assert _cookie_token(h) is None, "wrong password minted a cookie"
    finally:
        restore()


# --- callback.py (does not exist until implemented — load will error → red) ---

def _callback_env():
    """Set OAuth env for callback tests; returns restore()."""
    import os
    restore = _save_env(
        "AUTH_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "ADMIN_EMAILS",
        "BEACON_SALT", "TURSO_DATABASE_URL", "GARM_GATING")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
    os.environ["ADMIN_EMAILS"] = "nlovejoy@me.com"
    # A successful callback now fires a best-effort login beacon row (#10).
    # Salt it so the row is built, and blank the DB URL so any test that
    # doesn't patch turso_query can never reach a real database.
    os.environ["BEACON_SALT"] = "test-salt"
    os.environ["TURSO_DATABASE_URL"] = ""
    # Default the kill switch OFF (READER_EMAILS path) so every callback test
    # written before Garm consumption still exercises the behaviour it pins.
    # Tests that want the live-Garm branch patch GARM_ENABLED directly, which
    # overrides this regardless of env.
    os.environ["GARM_GATING"] = "off"
    return restore


@test("callback: valid state + verified admin id_token → 302 + admin cookie")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_valid")
        calls = []

        def fake_exchange(code):
            calls.append(code)
            return {"id_token": _fake_id_token({
                "email": "nlovejoy@me.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=authcode&state={state}")
            assert h.status_code == 302, f"got {h.status_code}"
            assert _location(h) == "/", f"redirect target: {_location(h)}"
            assert calls == ["authcode"], f"exchange not called with code: {calls}"
            tok = _cookie_token(h)
            assert tok, "no session cookie minted"
            payload = auth_helper.verify_token(tok)
            assert payload and payload["role"] == "admin", payload
            assert payload["email"] == "nlovejoy@me.com", payload
        finally:
            r()
    finally:
        restore()


@test("callback: unknown email → readable 403")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_unknown")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "stranger@gmail.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 403, f"got {h.status_code}"
            blob = h._body.decode().lower()
            assert blob.strip(), "403 body must not be blank"
            assert ("stranger@gmail.com" in blob or "authoriz" in blob
                    or "forbidden" in blob or "not allowed" in blob), (
                f"403 body should be readable/explanatory, got: {blob!r}")
            assert _cookie_token(h) is None, "unknown email got a session cookie"
        finally:
            r()
    finally:
        restore()


@test("callback: email_verified false → 403")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_unverified")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "nlovejoy@me.com", "email_verified": False,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 403, f"got {h.status_code}"
            assert _cookie_token(h) is None, "unverified email got a cookie"
        finally:
            r()
    finally:
        restore()


@test("callback: wrong aud → 403")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_wrongaud")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "nlovejoy@me.com", "email_verified": True,
                "aud": "wrong-client"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 403, f"got {h.status_code}"
            assert _cookie_token(h) is None, "wrong-aud token got a cookie"
        finally:
            r()
    finally:
        restore()


@test("callback: bad state → 400 and exchange is never called")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_badstate")
        calls = []

        def fake_exchange(code):
            calls.append(code)
            return {"id_token": _fake_id_token({
                "email": "nlovejoy@me.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            h = invoke(mod, "/api/callback?code=c&state=forged.deadbeef")
            assert h.status_code == 400, f"got {h.status_code}"
            assert not calls, "code was exchanged despite bad state"
        finally:
            r()
    finally:
        restore()


@test("callback: ?error=access_denied with no code → 4xx, no crash")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_error")
        calls = []
        r = patch(mod, _exchange_code=lambda code: calls.append(code))
        try:
            h = invoke(mod, "/api/callback?error=access_denied")
            assert 400 <= (h.status_code or 0) <= 403, f"got {h.status_code}"
            assert not calls, "exchange attempted on an error redirect"
        finally:
            r()
    finally:
        restore()


@test("callback: token exchange with no id_token → readable error, no crash/cookie")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_noidtoken")
        # Google error responses omit id_token (e.g. {"error": "invalid_grant"}).
        r = patch(mod, _exchange_code=lambda code: {"error": "invalid_grant"})
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert 400 <= (h.status_code or 0) < 600 and h.status_code != 302, (
                f"missing id_token should be a readable error, got {h.status_code}")
            assert h.status_code >= 400, f"got {h.status_code}"
            assert _cookie_token(h) is None, "minted a cookie without an id_token"
        finally:
            r()
    finally:
        restore()


@test("callback: ADMIN_EMAILS match is case-insensitive")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_case")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "NLovejoy@ME.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 302, f"case-sensitive compare rejected admin: {h.status_code}"
            assert _cookie_token(h), "no cookie for case-variant admin email"
        finally:
            r()
    finally:
        restore()


@test("callback: READER_EMAILS email → 302 + reader cookie")
def _():
    import os
    restore = _callback_env()
    saved_r = os.environ.get("READER_EMAILS")
    os.environ["READER_EMAILS"] = "ELovejoy5@gmail.com, other@x.test"
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_reader")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "elovejoy5@gmail.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 302, f"got {h.status_code}"
            token = _cookie_token(h)
            assert token, "no cookie for reader email"
            payload = auth_helper.verify_token(token)
            assert payload and payload["role"] == "reader", f"got {payload}"
            assert payload["email"] == "elovejoy5@gmail.com"
        finally:
            r()
    finally:
        if saved_r is None:
            os.environ.pop("READER_EMAILS", None)
        else:
            os.environ["READER_EMAILS"] = saved_r
        restore()


@test("callback: admin email wins even if also listed in READER_EMAILS")
def _():
    import os
    restore = _callback_env()
    saved_r = os.environ.get("READER_EMAILS")
    os.environ["READER_EMAILS"] = "nlovejoy@me.com"
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_adminwins")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "nlovejoy@me.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 302, f"got {h.status_code}"
            payload = auth_helper.verify_token(_cookie_token(h))
            assert payload and payload["role"] == "admin", f"got {payload}"
        finally:
            r()
    finally:
        if saved_r is None:
            os.environ.pop("READER_EMAILS", None)
        else:
            os.environ["READER_EMAILS"] = saved_r
        restore()


@test("callback: email in neither list still 403 when READER_EMAILS set")
def _():
    import os
    restore = _callback_env()
    saved_r = os.environ.get("READER_EMAILS")
    os.environ["READER_EMAILS"] = "elovejoy5@gmail.com"
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_neither")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": "stranger@gmail.com", "email_verified": True,
                "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 403, f"got {h.status_code}"
            assert _cookie_token(h) is None, "stranger got a cookie"
        finally:
            r()
    finally:
        if saved_r is None:
            os.environ.pop("READER_EMAILS", None)
        else:
            os.environ["READER_EMAILS"] = saved_r
        restore()


@test("callback: HTML in ?error= param is escaped (reflected XSS)")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_xss_error")
        r = patch(mod, _exchange_code=lambda code: {})
        try:
            h = invoke(mod, "/api/callback?error=%3Cscript%3Ealert(1)%3C/script%3E")
            body = h._body.decode()
            assert "<script>" not in body, f"unescaped error param reflected: {body}"
            assert "&lt;script&gt;" in body or "script" not in body, (
                f"error param neither escaped nor omitted: {body}")
        finally:
            r()
    finally:
        restore()


@test("callback: HTML in unauthorized email is escaped (reflected XSS)")
def _():
    restore = _callback_env()
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_xss_email")

        def fake_exchange(code):
            return {"id_token": _fake_id_token({
                "email": '<img src=x onerror=alert(1)>@evil.test',
                "email_verified": True, "aud": "test-client-id"})}

        r = patch(mod, _exchange_code=fake_exchange)
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            body = h._body.decode()
            assert h.status_code == 403, f"got {h.status_code}"
            assert "<img" not in body, f"unescaped email reflected: {body}"
        finally:
            r()
    finally:
        restore()


# === callback: readers resolve through Garm (Task 3) ===

def _id_token(email):
    """A verified, correct-aud id_token for `email` — the common case every
    garm-consumer callback test needs."""
    return _fake_id_token({
        "email": email, "email_verified": True, "aud": "test-client-id"})


def _state():
    return auth_helper.make_state()


@test("callback: non-admin with Garm grants → 302 + reader cookie carrying projects")
def _():
    restore = _callback_env()
    os.environ.pop("READER_EMAILS", None)
    cb = load_endpoint("web/api/callback.py", "cb_garm1")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: {"prntd"}, GARM_ENABLED=lambda: True)
    try:
        cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
        assert cap.status_code == 302, cap.status_code
        tok = [v for k, v in cap.response_headers if k == "Set-Cookie"][0].split(";")[0].split("=", 1)[1]
        p = auth_helper.verify_token(tok)  # AUTH_SECRET must still be the test value here
        assert p["role"] == "reader" and p["projects"] == ["prntd"], p
    finally:
        r(); restore()


@test("callback: non-admin with NO grants → 403 even if in READER_EMAILS (gating on)")
def _():
    restore = _callback_env()
    os.environ["READER_EMAILS"] = "pierre@example.com"
    cb = load_endpoint("web/api/callback.py", "cb_garm2")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: set(), GARM_ENABLED=lambda: True)
    try:
        cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally:
        r(); restore()
    assert cap.status_code == 403, cap.status_code


@test("callback: Garm unreachable → 403 with a 'try again' message, never a cookie")
def _():
    restore = _callback_env()
    cb = load_endpoint("web/api/callback.py", "cb_garm3")
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: None, GARM_ENABLED=lambda: True)
    try:
        cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally:
        r(); restore()
    assert cap.status_code == 503 and not [k for k, _ in cap.response_headers if k == "Set-Cookie"]


@test("callback: GARM_GATING=off → READER_EMAILS path, unfiltered reader cookie, Garm not called")
def _():
    restore = _callback_env()
    os.environ["READER_EMAILS"] = "pierre@example.com"
    cb = load_endpoint("web/api/callback.py", "cb_garm4")
    called = []
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("pierre@example.com")},
              fetch_grants=lambda e: called.append(e), GARM_ENABLED=lambda: False)
    try:
        cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally:
        r(); restore()
    assert cap.status_code == 302 and called == []


@test("callback: admin path unchanged — Garm never called even when gating on")
def _():
    restore = _callback_env()
    cb = load_endpoint("web/api/callback.py", "cb_garm5")
    called = []
    r = patch(cb, _exchange_code=lambda c: {"id_token": _id_token("nlovejoy@me.com")},
              fetch_grants=lambda e: called.append(e), GARM_ENABLED=lambda: True)
    try:
        cap = invoke(cb, "/api/callback?state=%s&code=c" % _state())
    finally:
        r(); restore()
    assert cap.status_code == 302 and called == []


# === callback login events (issue #10) ===

def _cb_login(email, role_env=None, name="endpoint_cb_login", turso=None,
              headers=None):
    """Run a callback sign-in with turso_query captured. Returns
    (captured_calls, response, cookie_payload) — the cookie is decoded before
    the env restore drops AUTH_SECRET. `role_env` sets READER_EMAILS."""
    import os
    restore = _callback_env()
    saved_r = os.environ.get("READER_EMAILS")
    if role_env is not None:
        os.environ["READER_EMAILS"] = role_env
    calls = []

    def fake_turso(sql, args=None):
        calls.append((sql, args or []))
        return []

    try:
        mod = load_endpoint("web/api/callback.py", name)
        rq = patch(turso_helper, turso_query=turso or fake_turso)
        r = patch(mod, _exchange_code=lambda code: {"id_token": _fake_id_token({
            "email": email, "email_verified": True, "aud": "test-client-id"})})
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}",
                       headers=headers)
            token = _cookie_token(h)
            payload = auth_helper.verify_token(token) if token else None
        finally:
            r()
            rq()
    finally:
        if saved_r is None:
            os.environ.pop("READER_EMAILS", None)
        else:
            os.environ["READER_EMAILS"] = saved_r
        restore()
    return calls, h, payload


def _page_view_inserts(calls):
    return [c for c in calls if "INSERT INTO page_views" in c[0]]


@test("callback login event: admin sign-in writes exactly one /login/admin row")
def _():
    calls, h, payload = _cb_login("nlovejoy@me.com", name="endpoint_cb_login_admin")
    assert h.status_code == 302, f"got {h.status_code}"
    assert payload and payload["role"] == "admin", f"no admin cookie: {payload}"
    inserts = _page_view_inserts(calls)
    assert len(inserts) == 1, f"expected exactly 1 login row, got {calls}"
    args = inserts[0][1]
    assert "login" in args, f"event not 'login': {args}"
    assert "/login/admin" in args, f"path not /login/admin: {args}"


@test("callback login event: reader sign-in writes /login/reader")
def _():
    calls, h, payload = _cb_login("elovejoy5@gmail.com",
                                  role_env="elovejoy5@gmail.com",
                                  name="endpoint_cb_login_reader")
    assert h.status_code == 302, f"got {h.status_code}"
    assert payload and payload["role"] == "reader", payload
    inserts = _page_view_inserts(calls)
    assert len(inserts) == 1, f"expected exactly 1 login row, got {calls}"
    assert "/login/reader" in inserts[0][1], f"path not /login/reader: {inserts[0][1]}"


@test("callback login event: no email — or any fragment of it — in the row")
def _():
    email = "nlovejoy@me.com"
    calls, h, _payload = _cb_login(email, name="endpoint_cb_login_noemail")
    inserts = _page_view_inserts(calls)
    assert len(inserts) == 1, f"expected exactly 1 login row, got {calls}"
    sql, args = inserts[0]
    # Every column value, checked individually — nothing derived from the
    # identity may appear anywhere in the row.
    for value in args:
        blob = str(value).lower()
        for needle in (email, email.split("@")[0], email.split("@")[1],
                       "nlovejoy", "lovejoy", "me.com"):
            assert needle not in blob, (
                f"identity fragment {needle!r} leaked into column value "
                f"{value!r} (row: {args})")
    assert email.lower() not in sql.lower(), f"email in SQL text: {sql}"
    # And the whole serialized row, as a belt-and-braces check.
    assert "lovejoy" not in json.dumps(args).lower(), f"email leaked: {args}"


@test("callback login event: sign-in still succeeds when the row insert raises")
def _():
    def boom(sql, args=None):
        raise RuntimeError("turso down")

    ok_calls, ok, _ok_payload = _cb_login(
        "nlovejoy@me.com", name="endpoint_cb_login_ok_ref")
    bad_calls, bad, bad_payload = _cb_login(
        "nlovejoy@me.com", name="endpoint_cb_login_boom", turso=boom)
    assert bad.status_code == ok.status_code == 302, (
        f"insert failure changed status: {bad.status_code} vs {ok.status_code}")
    assert _location(bad) == _location(ok) == "/", f"redirect changed: {_location(bad)}"
    bad_cookie = [v for k, v in bad.response_headers if k == "Set-Cookie"]
    ok_cookie = [v for k, v in ok.response_headers if k == "Set-Cookie"]
    assert len(bad_cookie) == len(ok_cookie) == 1, (
        f"cookie count changed: {bad_cookie} vs {ok_cookie}")
    assert bad_payload and bad_payload["role"] == "admin", bad_payload
    assert not _page_view_inserts(bad_calls), "boom should have recorded nothing"
    assert _page_view_inserts(ok_calls), "reference run wrote no row"


@test("callback login event: BEACON_SALT unset → no row, sign-in still succeeds")
def _():
    import os
    restore = _callback_env()
    os.environ.pop("BEACON_SALT", None)
    calls = []
    try:
        mod = load_endpoint("web/api/callback.py", "endpoint_cb_login_nosalt")
        rq = patch(turso_helper,
                   turso_query=lambda sql, args=None: calls.append((sql, args)) or [])
        r = patch(mod, _exchange_code=lambda code: {"id_token": _fake_id_token({
            "email": "nlovejoy@me.com", "email_verified": True,
            "aud": "test-client-id"})})
        try:
            state = auth_helper.make_state()
            h = invoke(mod, f"/api/callback?code=c&state={state}")
            assert h.status_code == 302, f"got {h.status_code}"
            payload = auth_helper.verify_token(_cookie_token(h))
            assert payload and payload["role"] == "admin", payload
            assert not _page_view_inserts(calls), (
                f"row written without BEACON_SALT: {calls}")
        finally:
            r()
            rq()
    finally:
        restore()


@test("callback login event: a rejected sign-in records nothing")
def _():
    calls, h, payload = _cb_login("stranger@gmail.com",
                                  name="endpoint_cb_login_rejected")
    assert payload is None, f"rejected sign-in got a cookie: {payload}"
    assert h.status_code == 403, f"got {h.status_code}"
    assert not _page_view_inserts(calls), f"403 wrote a login row: {calls}"


# === health_report (issue #34) ===

def _health_env():
    """Set the env the health endpoint needs; returns a restore fn."""
    saved = {k: os.environ.get(k) for k in
             ("AUTH_SECRET", "CRON_SECRET", "RESEND_API_KEY", "HEALTH_TO_EMAIL",
              "UPTIMEROBOT_API_KEY")}
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ["CRON_SECRET"] = "cron-secret"
    os.environ["RESEND_API_KEY"] = "re_test"
    os.environ["HEALTH_TO_EMAIL"] = "nico@test.invalid"
    os.environ["UPTIMEROBOT_API_KEY"] = "ur-test"

    def restore():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


def _health_mod(up=True, hb="fresh", ur="ok"):
    """Load health_report with targets, joke, send, and the UptimeRobot pull
    stubbed. Returns (mod, sent) where sent collects (subject, html, text)
    tuples. Every poll appends to `mod._polls`, so a test can pin that an
    unauthorized caller never made us do the target-polling work; every uptime
    archive write appends to `mod._uptime_writes`.

    `hb` drives the heartbeat (artifact-freshness) stub: fresh / stale /
    never (table empty) / error (Turso unreadable). `ur` drives the uptime
    pull: ok / error (UptimeRobot unreachable).

    The turso stub dispatches on the SQL because the endpoint issues three
    different kinds of query against the same helper — the pause lookup, the
    freshness lookups, and the uptime upsert — and they must not be conflated:
    the pause check fails OPEN, freshness must not, and the uptime write must
    be separately observable."""
    mod = load_endpoint("web/api/health_report.py", "health_report_test")
    sent = []
    mod._polls = []
    mod._uptime_writes = []
    # Ordered log of what each query was, so a test can pin that the archive's
    # own freshness is read BEFORE the archive is written.
    mod._sql_kinds = []

    def fake_check(name, url, deep=False):
        mod._polls.append(name)
        return {"name": name, "ok": up, "status": 200 if up else 503,
                "note": "db ok" if deep else "", "ms": 42}

    today = lab_today().isoformat()  # #48: the archive files under the lab day

    def fake_turso(sql, args=None):
        # Match the write on INSERT, not on the table name: the "uptime archive"
        # heartbeat SELECTs from uptime_daily too, and conflating the two would
        # make the freshness read look like a write and return no rows.
        if "INSERT INTO uptime_daily" in sql:
            mod._sql_kinds.append("uptime-write")
            mod._uptime_writes.append(args)
            return []
        if "health_email_state" in sql:
            return []  # not paused
        mod._sql_kinds.append(
            "uptime-freshness" if "uptime_daily" in sql else "freshness")
        if hb == "error":
            raise RuntimeError("turso unreachable")
        if hb == "never":
            return []
        return [{"d": "2020-01-01" if hb == "stale" else today}]

    def fake_fetch(api_key):
        if ur == "error":
            raise RuntimeError("uptimerobot unreachable")
        return [
            {"friendly_name": "garm-monitor", "status": 2,
             "custom_uptime_ratio": "100.000-100.000-99.980",
             "response_times": [{"datetime": 1, "value": 280},
                                {"datetime": 2, "value": 282}]},
            {"friendly_name": "prompt-labs", "status": 9,
             "custom_uptime_ratio": "50.000-90.000-99.000",
             "response_times": []},
        ]

    mod._check_target = fake_check
    mod._joke = lambda: "a test joke"
    mod._send_email = lambda subject, html, text: sent.append((subject, html, text))
    mod._fetch_uptime_monitors = fake_fetch
    mod.turso_query = fake_turso
    return mod, sent


@test("health_report: no auth → 401, nothing sent")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report")
        assert h.status_code == 401, f"got {h.status_code}: {h.body}"
        assert not sent
    finally:
        restore()


@test("health_report: cron bearer → polls targets, sends, reports")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(up=True)
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body == {"sent": True, "down": [], "stale": [],
                          "uptime_rows": 2}, h.body
        assert len(sent) == 1
        subject, html, text = sent[0]
        n = len(mod.TARGETS)  # derived, not pinned — TARGETS grows
        assert f"{n}/{n} up" in subject, subject
        assert "a test joke" in text and "a test joke" in html
        assert "action=pause&token=" in text, "pause link missing"
        assert "Tune the daily health email" in text, "tune-up prompt missing"
    finally:
        restore()


@test("health_report: a down target is named in subject and body")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(up=False)
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["down"] == [n for n, _, _ in mod.TARGETS], h.body
        assert "DOWN" in sent[0][0], sent[0][0]
    finally:
        restore()


@test("health_report: paused state skips the send")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        far = "2099-01-01T00:00:00Z"
        mod.turso_query = lambda sql, args=None: [{"value": far}]
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body == {"skipped": "paused", "paused_until": far,
                          "uptime_rows": 2}, h.body
        assert not sent
    finally:
        restore()


@test("health_report: pause check fails OPEN — turso down, email still sends")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()

        def boom(sql, args=None):
            raise RuntimeError("turso unreachable")
        mod.turso_query = boom
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(sent) == 1
    finally:
        restore()


@test("health_report: ?dry=1 polls without sending")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report?dry=1",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["would_send"] is True, h.body
        assert ([t["name"] for t in h.body["targets"]]
                == [n for n, _, _ in mod.TARGETS]), h.body["targets"]
        assert not sent
    finally:
        restore()


def _health_cookie(role, email="someone@test.invalid"):
    """A real signed session cookie header for `role`. Call AFTER _health_env()
    so AUTH_SECRET matches what the endpoint's get_role() will verify against."""
    tok = auth_helper.make_token(role, email=email)
    return {"cookie": f"{auth_helper.COOKIE_NAME}={tok}"}


@test("health_report: reader cookie + ?dry=1 → 200 targets, nothing sent")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report?dry=1", _health_cookie("reader"))
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert ([t["name"] for t in h.body["targets"]]
                == [n for n, _, _ in mod.TARGETS]), h.body["targets"]
        assert "paused_until" in h.body and "would_send" in h.body, h.body
        assert not sent, "reader dry run sent an email"
    finally:
        restore()


@test("health_report: reader cookie without dry → 403 (not 401), nothing sent")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report", _health_cookie("reader"))
        assert h.status_code == 403, (
            f"authenticated reader got {h.status_code}, expected 403 — a 401 "
            "would say 'not logged in' when the truth is 'may not trigger a send'")
        assert h.body.get("error"), f"no error body: {h.body}"
        assert not sent, "reader triggered a send"
    finally:
        restore()


@test("health_report: admin cookie without dry still sends (send path intact)")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report", _health_cookie("admin"))
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body == {"sent": True, "down": [], "stale": [],
                          "uptime_rows": 2}, h.body
        assert len(sent) == 1, f"admin send path broken: {sent}"
    finally:
        restore()


# === heartbeats / artifact freshness (issue #45) ===

@test("heartbeats: all fresh → one summary line, subject stays ✅")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="fresh")
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert h.body["stale"] == [], h.body
        subject, html_body, text = sent[0]
        assert subject.startswith("✅"), subject
        n = len(mod.HEARTBEATS)
        assert f"all {n} artifacts fresh" in text, text
        # Healthy state must stay one line, or the email stops being glanceable.
        assert "expected within" not in text, text
    finally:
        restore()


@test("heartbeats: a stale artifact escalates the subject and is named")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="stale")
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(h.body["stale"]) == len(mod.HEARTBEATS), h.body
        subject, html_body, text = sent[0]
        assert subject.startswith("🟡"), subject
        assert "stale" in subject, subject
        # Named, with the age and the threshold it broke.
        assert "review email" in text, text
        assert "expected within" in text, text
        assert "review email" in html_body, html_body
    finally:
        restore()


@test("heartbeats: an unreadable Turso reports UNCHECKED, never fresh")
def _():
    """The bug this whole feature exists to kill is absence reading as fine.
    The pause check above fails open on purpose; freshness must not."""
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="error")
        h = invoke(mod, "/api/health_report?dry=1",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        hbs = h.body["heartbeats"]
        assert len(hbs) == len(mod.HEARTBEATS), hbs
        assert all(x["ok"] is None for x in hbs), hbs
        assert all("could not check" in x["note"] for x in hbs), hbs
        # Crucially: not reported as fresh, and not miscounted as stale either.
        assert h.body.get("stale") is None, h.body
    finally:
        restore()


@test("heartbeats: an unreadable Turso still lets the email send")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="error")
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(sent) == 1, "a failed freshness check killed the email"
        assert "unchecked" in sent[0][0], sent[0][0]
    finally:
        restore()


@test("heartbeats: an empty table is stale ('never produced'), not fresh")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="never")
        h = invoke(mod, "/api/health_report?dry=1",
                   {"authorization": "Bearer cron-secret"})
        hbs = h.body["heartbeats"]
        assert all(x["ok"] is False for x in hbs), hbs
        assert all("never produced" in x["note"] for x in hbs), hbs
        assert all(x["last"] is None for x in hbs), hbs
    finally:
        restore()


@test("heartbeats: ?dry=1 exposes the block for the #/health page")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(hb="fresh")
        h = invoke(mod, "/api/health_report?dry=1",
                   {"authorization": "Bearer cron-secret"})
        hbs = h.body["heartbeats"]
        assert [x["name"] for x in hbs] == [n for n, _, _ in mod.HEARTBEATS], hbs
        for x in hbs:
            assert x["ok"] is True, x
            assert x["age_days"] == 0, x
            assert set(x) >= {"name", "ok", "last", "age_days", "max_age_days", "note"}, x
        assert not sent
    finally:
        restore()


@test("heartbeats: thresholds are days and exceed each job's real period")
def _():
    """A threshold at or below the job's own cadence alarms on a healthy run.
    Nightly jobs must tolerate one miss (#45's bar is catching night two)."""
    mod, _ = _health_mod()
    by_name = {n: d for n, _, d in mod.HEARTBEATS}
    for nightly in ("review email", "synthesizer"):
        assert by_name[nightly] == 2, f"{nightly}: {by_name[nightly]}"
    # Anthropic reports a day late, so yesterday is the healthy newest row.
    assert by_name["cost pull + sync"] >= 3, by_name
    # 1st & 16th → gaps of ~16 days.
    assert by_name["bi-monthly report"] >= 17, by_name
    assert by_name["weekly rollups"] >= 8, by_name
    # Written by a daily cron, so it tolerates one miss like the other nightlies.
    assert by_name["uptime archive"] == 2, by_name


@test("heartbeats: the uptime archive declares its own freshness")
def _():
    """Added 2026-08-02: the archive wrote on Aug 1, not Aug 2, and nothing
    said so for two days because it was the one artifact with no check."""
    mod, _ = _health_mod()
    sqls = {n: s for n, s, _ in mod.HEARTBEATS}
    assert "uptime archive" in sqls, list(sqls)
    assert "uptime_daily" in sqls["uptime archive"], sqls["uptime archive"]


@test("heartbeats: the archive's freshness is read before the archive is written")
def _():
    """The same request writes uptime_daily and grades it. If the write ran
    first it would refresh the row it is about to grade and report fresh
    forever — an alarm that can never fire is worse than none."""
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert mod._uptime_writes, "archive never written on the send path"
        kinds = mod._sql_kinds
        assert "uptime-freshness" in kinds, kinds
        assert kinds.index("uptime-freshness") < kinds.index("uptime-write"), kinds
    finally:
        restore()


@test("health_report: no auth + ?dry=1 → 401 and targets never polled")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report?dry=1")
        assert h.status_code == 401, f"got {h.status_code}: {h.body}"
        assert not sent
        assert mod._polls == [], f"polled targets before rejecting: {mod._polls}"
    finally:
        restore()


@test("health_report: bad cookie + ?dry=1 → 401 and targets never polled")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report?dry=1",
                   {"cookie": f"{auth_helper.COOKIE_NAME}=garbage.sig"})
        assert h.status_code == 401, f"got {h.status_code}: {h.body}"
        assert not sent
        assert mod._polls == [], f"polled targets before rejecting: {mod._polls}"
    finally:
        restore()


@test("health_report: valid pause token writes paused_until ≈ 7 days out")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        writes = []
        mod.turso_query = lambda sql, args=None: writes.append((sql, args))
        token = mod._make_pause_token()
        h = invoke(mod, f"/api/health_report?action=pause&token={token}")
        assert h.status_code == 200, f"got {h.status_code}"
        assert len(writes) == 1 and "health_email_state" in writes[0][0]
        until = writes[0][1][0]
        expected = time.time() + 7 * 86400
        import calendar
        got = calendar.timegm(time.strptime(until, "%Y-%m-%dT%H:%M:%SZ"))
        assert abs(got - expected) < 3600, f"paused_until off: {until}"
        assert not sent
    finally:
        restore()


@test("health_report: bad pause token → 403, no state write")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        writes = []
        mod.turso_query = lambda sql, args=None: writes.append((sql, args))
        h = invoke(mod, "/api/health_report?action=pause&token=garbage.sig")
        assert h.status_code == 403, f"got {h.status_code}"
        assert not writes and not sent
    finally:
        restore()


@test("health_report: joke falls back to canned when anthropic unavailable")
def _():
    restore = _health_env()
    try:
        mod, _sent = _health_mod()
        saved = sys.modules.get("anthropic")
        sys.modules["anthropic"] = None  # forces ImportError inside _joke
        try:
            mod2 = load_endpoint("web/api/health_report.py", "health_report_joke_test")
            joke = mod2._joke()
            assert joke in mod2.CANNED_JOKES, f"not canned: {joke}"
        finally:
            if saved is None:
                sys.modules.pop("anthropic", None)
            else:
                sys.modules["anthropic"] = saved
    finally:
        restore()


# === health (public liveness, docs/health-convention.md) ===

@test("health: shallow → 200 {ok: true}, no auth required")
def _():
    mod = load_endpoint("web/api/health.py", "health_test")
    mod.turso_query = lambda sql, args=None: (_ for _ in ()).throw(
        AssertionError("shallow check must not touch Turso"))
    h = invoke(mod, "/api/health")
    assert h.status_code == 200, f"got {h.status_code}: {h.body}"
    assert h.body == {"ok": True}, h.body


@test("health: deep ?db=1 with Turso up → 200 {ok: true, db: true}")
def _():
    mod = load_endpoint("web/api/health.py", "health_test")
    mod.turso_query = lambda sql, args=None: [{"1": 1}]
    h = invoke(mod, "/api/health?db=1")
    assert h.status_code == 200, f"got {h.status_code}: {h.body}"
    assert h.body == {"ok": True, "db": True}, h.body


@test("health: deep ?db=1 with Turso down → 503 {ok: false, db: false}")
def _():
    mod = load_endpoint("web/api/health.py", "health_test")

    def boom(sql, args=None):
        raise OSError("turso unreachable")

    mod.turso_query = boom
    h = invoke(mod, "/api/health?db=1")
    assert h.status_code == 503, f"got {h.status_code}: {h.body}"
    assert h.body == {"ok": False, "db": False}, h.body


@test("health_report: prompt-labs target is the public /api/health, deep")
def _():
    # Regression pin: the first health email reported prompt-labs.org DOWN
    # because TARGETS polled auth-gated /api/info and got a 401.
    mod = load_endpoint("web/api/health_report.py", "health_report_targets_test")
    by_name = {name: (url, deep) for name, url, deep in mod.TARGETS}
    url, deep = by_name["prompt-labs.org"]
    assert url == "https://prompt-labs.org/api/health?db=1", url
    assert deep is True
    assert "/api/info" not in url


@test("health_report: every TARGETS url is also an UptimeRobot HTTP monitor")
def _():
    # TARGETS (daily trend email) and HTTP_MONITORS (5-minute paging) are two
    # declarations of the same intent and drifted for a month — 2 vs 8 — until
    # phase 5. The layers differ, the URL set should not: a target polled daily
    # but never paged is a gap, and a URL typo'd in one file alone is invisible
    # otherwise. HTTP_MONITORS may legitimately hold MORE (something worth
    # paging on but not worth a daily line), so this is a subset check.
    mod = load_endpoint("web/api/health_report.py", "health_report_drift_test")
    ur = load_endpoint("scripts/uptimerobot.py", "uptimerobot_drift_test")
    monitored = {url for _, url in ur.HTTP_MONITORS}
    missing = [(n, u) for n, u, _ in mod.TARGETS if u not in monitored]
    assert not missing, (
        f"TARGETS urls absent from HTTP_MONITORS: {missing} — add them to "
        f"scripts/uptimerobot.py (and run `uptimerobot.py sync --apply`)")


@test("health_report: deep flag matches the url's ?db=1")
def _():
    # The convention is mechanical on purpose: ?db=1 asks the app to touch its
    # dependencies, so there is a body worth parsing. A deep flag that drifts
    # off its URL means either a wasted parse or silently discarded detail.
    mod = load_endpoint("web/api/health_report.py", "health_report_deepflag_test")
    for name, url, deep in mod.TARGETS:
        if "db=1" in url:
            assert deep is True, f"{name}: ?db=1 url but deep={deep}"


@test("health_report: deep parser summarizes a checks[] body, naming failures")
def _():
    # ibuild4you, byside and pianohouse return checks[] rather than a db bool;
    # before phase 5 the parser knew only db/howl and rendered them note-less.
    mod = load_endpoint("web/api/health_report.py", "health_report_checks_test")

    class FakeResp:
        status = 200

        def __init__(self, payload):
            self._b = json.dumps(payload).encode()

        def read(self, n=None):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def poll(payload):
        mod.urllib.request.urlopen = lambda req, timeout=None: FakeResp(payload)
        return mod._check_target("t", "https://x/api/health?db=1", deep=True)

    r = poll({"ok": True, "checks": [{"name": "db", "ok": True},
                                     {"name": "cache", "ok": True}]})
    assert r["ok"] is True
    assert r["note"] == "2/2 checks ok", r["note"]

    r = poll({"ok": False, "checks": [{"name": "db", "ok": True},
                                      {"name": "sanity", "ok": False}]})
    assert r["note"] == "1/2 checks ok — sanity DOWN", r["note"]

    # The db-bool shape must keep working unchanged.
    r = poll({"ok": True, "db": True})
    assert r["note"] == "db ok", r["note"]


@test("health_report: _check_targets returns results in TARGETS order")
def _():
    # The poll fans out across threads; the email and the #/health page both
    # read positionally, so order must survive.
    mod = load_endpoint("web/api/health_report.py", "health_report_order_test")
    mod._check_target = lambda name, url, deep=False: {
        "name": name, "ok": True, "status": 200, "note": "", "ms": 1}
    got = [r["name"] for r in mod._check_targets()]
    assert got == [n for n, _, _ in mod.TARGETS], got


# === day.py — the #/day/<date> detail page ===


def _day_mod(rows, authed=True, boom=False):
    mod = load_endpoint("web/api/day.py", "endpoint_day")
    seen = []

    def fake_turso(sql, args=None):
        seen.append((sql, args or []))
        if boom:
            raise OSError("turso unreachable")
        if "project_aliases" in sql:
            return [{"alias": "pianohouse", "canonical": "selected-projects"}]
        # Dispatch on the SQL, same reason the health stub does: this endpoint
        # reads four tables through one turso_query, and feeding summary rows to
        # the page_views read would silently pass while proving nothing.
        if "daily_summaries" in sql:
            return rows
        return []
    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: (access_helper.Access('admin', 'a@b.c', None, None) if authed else None))

    def restore():
        restore_a()
        restore_q()
    return mod, seen, restore


@test("day: 401 when not authenticated, before any query runs")
def _():
    mod, seen, restore = _day_mod([], authed=False)
    try:
        h = invoke(mod, "/api/day?date=2026-08-02")
        assert h.status_code == 401, h.status_code
        assert not seen, "queried on behalf of an anonymous caller"
    finally:
        restore()


@test("day: a malformed date is a 400, not an empty day")
def _():
    # A typo'd URL must say what's wrong. Silently returning an empty day would
    # read as "nothing happened then", which is a different and wrong claim.
    for bad in ["", "2026-8-2", "august 2", "2026-08-02'; DROP TABLE x--"]:
        mod, seen, restore = _day_mod([])
        try:
            h = invoke(mod, "/api/day?date=" + bad.replace(" ", "%20"))
            assert h.status_code == 400, f"{bad!r} → {h.status_code}"
            assert not seen, f"{bad!r} reached the database"
        finally:
            restore()


@test("day: a quiet day is 200 with zeros, never a 404")
def _():
    mod, _, restore = _day_mod([])
    try:
        h = invoke(mod, "/api/day?date=2026-03-01")
        assert h.status_code == 200, h.status_code
        assert h.body["totals"] == {"prompts": 0, "sessions": 0, "commits": 0}, h.body
        assert h.body["projects"] == [], h.body
        assert h.body["provisional"] is False, "a past date is not provisional"
    finally:
        restore()


@test("day: folds aliases, re-sums counts, and coerces Turso's strings")
def _():
    # Turso returns COALESCE/SUM results as strings; without int() the totals
    # concatenate instead of adding. Same trap as the chart math.
    rows = [
        {"project": "pianohouse", "summary": "short", "key_decisions": None,
         "prompts": "3", "sessions": "1", "commits": "0"},
        {"project": "selected-projects", "summary": "a much longer telling",
         "key_decisions": '["shipped the axis"]',
         "prompts": "4", "sessions": "1", "commits": "2"},
        {"project": "garm", "summary": "", "key_decisions": None,
         "prompts": 1, "sessions": 0, "commits": 0},
    ]
    mod, _, restore = _day_mod(rows)
    try:
        h = invoke(mod, "/api/day?date=2026-08-02")
        assert h.status_code == 200, h.status_code
        by = {p["project"]: p for p in h.body["projects"]}
        assert set(by) == {"selected-projects", "garm"}, list(by)
        sp = by["selected-projects"]
        assert sp["prompts"] == 7 and sp["sessions"] == 2 and sp["commits"] == 2, sp
        # The longer prose wins outright — gluing two tellings of the same day
        # together reads as a contradiction.
        assert sp["summary"] == "a much longer telling", sp["summary"]
        assert sp["key_decisions"] == ["shipped the axis"], sp["key_decisions"]
        assert h.body["totals"] == {"prompts": 8, "sessions": 2, "commits": 2}, h.body["totals"]
        # Busiest first, so the page opens on what the day was actually about.
        assert [p["project"] for p in h.body["projects"]] == ["selected-projects", "garm"]
    finally:
        restore()


@test("day: selects no prose column Turso doesn't already hold")
def _():
    # Structural echo of the private_history guarantee: Turso has no prompts /
    # sessions / commits tables at all, so this can only ever read counts and
    # already-written summary prose. Pin the table it reads.
    mod, seen, restore = _day_mod([])
    try:
        invoke(mod, "/api/day?date=2026-08-02")
        day_sql = [s for s, _ in seen if "daily_summaries" in s]
        assert day_sql, "no daily_summaries query emitted"
        for s, _ in seen:
            for banned in ("FROM prompts", "FROM sessions", "FROM commits"):
                assert banned not in s, f"{banned} in {s}"
    finally:
        restore()


@test("day: today is flagged provisional — an unsummarized day isn't a quiet one")
def _():
    # Counts come from daily_summaries, written at /handoff time, so a live
    # session is missing from them. Rendering that as a final number is this
    # repo's recurring failure shape: partial output presented as complete.
    from day_helper import lab_today as _lt
    mod, _, restore = _day_mod([])
    try:
        h = invoke(mod, "/api/day?date=" + _lt().isoformat())
        assert h.body["provisional"] is True, h.body
    finally:
        restore()


@test("day: one unreadable side table degrades to a missing section, not a 503")
def _():
    # The summaries read 503s (a day page with no day in it is not a page); the
    # spend/visitors/uptime reads must not, or a cost-table blip takes the page
    # down with it.
    mod = load_endpoint("web/api/day.py", "endpoint_day_soft")

    def fake_turso(sql, args=None):
        if "api_costs" in sql:
            raise OSError("turso unreachable")
        if "project_aliases" in sql:
            return []
        if "daily_summaries" in sql:
            return [{"project": "garm", "summary": "", "key_decisions": None,
                     "prompts": 2, "sessions": 1, "commits": 0}]
        return []
    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, resolve_access=lambda h: access_helper.Access('admin', 'a@b.c', None, None))
    try:
        h = invoke(mod, "/api/day?date=2026-08-02")
        assert h.status_code == 200, f"{h.status_code}: {h.body}"
        assert h.body["spend"] is None, "a failed read must be null, not 0"
        assert h.body["totals"]["prompts"] == 2, h.body
        assert h.body["visitors"] == {"views": 0, "by_site": []}, h.body["visitors"]
    finally:
        restore_a()
        restore_q()


@test("day: an unreadable Turso is a 503, not an empty day")
def _():
    mod, _, restore = _day_mod([], boom=True)
    try:
        h = invoke(mod, "/api/day?date=2026-08-02")
        assert h.status_code == 503, h.status_code
        assert "error" in h.body, h.body
    finally:
        restore()


# === clocks: UTC at rest, Pacific on display (#48) ===
#
# These are drift guards, not behaviour tests. Every instance of #48 was a date
# that LOOKED right — a plain YYYY-MM-DD string with nothing saying which clock
# produced it — and each one only misbehaved for the seven hours a day when UTC
# and Pacific disagree. A test that computes its own expectation is no help
# (four in this file did exactly that and passed by day, failed by night), so
# these read the source instead.


@test("clocks: the lab day is Pacific, and rolls at Pacific midnight")
def _():
    from datetime import datetime as _dtc
    from datetime import timezone as _tzc

    import day_helper
    # 00:30 UTC on Aug 3 is still Aug 2 in the lab — the exact window that put a
    # phantom tomorrow column on the activity chart. Also proves the zone
    # actually resolved: a missing tzdb would silently degrade this to UTC.
    aug3_utc = _dtc(2026, 8, 3, 0, 30, tzinfo=_tzc.utc)
    assert aug3_utc.astimezone(day_helper.LAB_TZ).date().isoformat() == "2026-08-02"
    # And a summer afternoon is unambiguous in both.
    noon_utc = _dtc(2026, 8, 2, 19, 0, tzinfo=_tzc.utc)
    assert noon_utc.astimezone(day_helper.LAB_TZ).date().isoformat() == "2026-08-02"
    # lab_window is inclusive of today, so N reaches back N-1.
    assert day_helper.lab_window(1) == day_helper.lab_today().isoformat()


@test("clocks: no frontend date bucket is built from toISOString()")
def _():
    # `new Date(…).toISOString().slice(0, 10)` is UTC. It reads as "today" and
    # is not, which is how every axis in this dashboard ended up a day ahead
    # after 5pm Pacific. labDay()/labDayOf() exist so this never comes back.
    src = (ROOT / "web" / "index.html").read_text()
    offenders = [ln.strip() for ln in src.splitlines()
                 if "toISOString()" in ln and ".slice(0," in ln
                 and not ln.strip().startswith("//")]
    assert not offenders, (
        "toISOString() used to form a date/stamp — use labDay()/labDayOf()/"
        f"labStamp() instead: {offenders}")


@test("clocks: no web/api endpoint derives a calendar day from UTC")
def _():
    # UTC stays correct for *instants* (generated_at, build time, token expiry).
    # It is calendar DAYS that must come from day_helper — so the pattern banned
    # here is specifically `.date()` off a now(), not now() itself.
    import re as _re
    bad = []
    for path in sorted((ROOT / "web" / "api").glob("*.py")):
        for i, ln in enumerate(path.read_text().splitlines(), 1):
            if ln.lstrip().startswith("#"):
                continue
            if _re.search(r"datetime\.now\([^)]*\)\.date\(\)", ln) or \
               _re.search(r"datetime\.now\(\)\.strftime", ln):
                bad.append(f"{path.name}:{i}: {ln.strip()}")
    assert not bad, ("calendar day derived from a raw now() — import from "
                     f"day_helper instead: {bad}")


@test("clocks: raw UTC timestamps are bucketed with 'localtime', day columns are not")
def _():
    # sqlite_store mixes two column families that look identical: UTC instants
    # (prompts.timestamp, sessions.started_at, commits.timestamp) and calendar
    # days (daily_summaries.date). date() on the first without 'localtime'
    # files an evening's work under tomorrow; 'localtime' on the second would
    # shift a date that was never UTC to begin with.
    import re as _re
    src = (ROOT / "store" / "sqlite_store.py").read_text()
    naked = _re.findall(r"date\((\w+\.)?(timestamp|started_at)\)", src)
    assert not naked, f"timestamp bucketed in UTC (add 'localtime'): {naked}"
    assert "date(ds.date, 'weekday 0', '-6 days')" in src, (
        "daily_summaries.date is already a calendar day — it must NOT gain "
        "'localtime', and the week bucket must stay 'weekday 0','-6 days' "
        "(the containing week's Monday); this pins both")


@test("clocks: a Monday's week_start is itself — 'weekday 1','-7 days' must not return")
def _():
    # SQLite's 'weekday N' means next-or-SAME day, so 'weekday 1','-7 days'
    # mapped a Monday to the PREVIOUS Monday and filed every Monday under the
    # prior week (found 2026-08-05). 'weekday 0','-6 days' — next-or-same
    # Sunday, minus 6 — is Monday-of-week for all seven weekdays. Run it for
    # real: Mon 2026-08-03 through Sun 2026-08-09 must all bucket to 08-03.
    import sqlite3 as _sq
    con = _sq.connect(":memory:")
    for i in range(7):
        d = f"2026-08-{3 + i:02d}"
        got = con.execute(
            "SELECT date(?, 'weekday 0', '-6 days')", (d,)).fetchone()[0]
        assert got == "2026-08-03", f"{d} bucketed to {got}"
    # And the buggy expression must not creep back into any of its four homes.
    # Comment lines are exempt — they are exactly where the trap is explained.
    homes = [ROOT / "store" / "sqlite_store.py",
             ROOT / "store" / "turso_store.py",
             ROOT / "web" / "api" / "private_history.py",
             ROOT / "workflow" / "bin" / "gc-read.sh"]
    stale = [p.name for p in homes
             if any("'weekday 1'" in ln for ln in p.read_text().splitlines()
                    if not ln.lstrip().startswith(("#", "--")))]
    assert not stale, f"'weekday 1' week bucketing is back in: {stale}"
    # gc-read's completed-weeks filter shares the trap: date('now','weekday 1')
    # is NEXT Monday except on Mondays, which admitted the in-progress week.
    sh = (ROOT / "workflow" / "bin" / "gc-read.sh").read_text()
    assert "date < date('now', 'weekday 0', '-6 days')" in sh, (
        "completed-weeks filter must cut at the CURRENT week's Monday")


# === uptime archive (Phase 1, docs/plan-2026-08-01-uptime-dashboard.md) ===

def _uptime_ddl():
    return load_endpoint("scripts/create_uptime_daily.py", "create_uptime_daily_test")


@test("uptime_daily: DDL re-runs clean and declares the planned columns")
def _():
    import sqlite3
    ddl = _uptime_ddl()
    con = sqlite3.connect(":memory:")
    for _ in range(2):  # idempotent: the script is expected to be re-run
        for sql in ddl.STATEMENTS:
            con.execute(sql)
    info = list(con.execute("PRAGMA table_info(uptime_daily)"))
    assert [r[1] for r in info] == [
        "date", "monitor", "uptime_1d", "uptime_7d", "uptime_30d",
        "avg_response_ms", "status"], info
    assert [r[1] for r in info if r[5]] == ["date", "monitor"], f"PK is not (date, monitor): {info}"


@test("uptime_daily: a second same-day pull UPDATEs the row, never duplicates")
def _():
    import sqlite3
    ddl = _uptime_ddl()
    mod = load_endpoint("web/api/health_report.py", "health_report_upsert_test")
    con = sqlite3.connect(":memory:")
    for sql in ddl.STATEMENTS:
        con.execute(sql)
    con.execute(mod.UPTIME_UPSERT_SQL,
                ["2026-08-01", "garm", 100.0, 100.0, 100.0, 281, "UP"])
    con.execute(mod.UPTIME_UPSERT_SQL,
                ["2026-08-01", "garm", 99.5, 99.9, 99.99, 310, "SEEMS_DOWN"])
    rows = list(con.execute(
        "SELECT date, monitor, uptime_1d, avg_response_ms, status FROM uptime_daily"))
    assert len(rows) == 1, f"same-day re-run duplicated: {rows}"
    assert rows[0] == ("2026-08-01", "garm", 99.5, 310, "SEEMS_DOWN"), rows[0]


@test("uptime pull: custom_uptime_ratio is a STRING and must be split + floated")
def _():
    # The trap this test exists for: UptimeRobot returns "100.000-99.980-99.990"
    # for custom_uptime_ratios=1-7-30. Same class as Turso handing back
    # aggregates as strings — untouched, every downstream number is text.
    mod = load_endpoint("web/api/health_report.py", "health_report_ratio_test")
    row = mod._uptime_row({"friendly_name": "garm", "status": 2,
                           "custom_uptime_ratio": "100.000-99.980-99.990"},
                          "2026-08-01")
    assert row["uptime_1d"] == 100.0 and isinstance(row["uptime_1d"], float), row
    assert row["uptime_7d"] == 99.98, row
    assert row["uptime_30d"] == 99.99, row
    assert row["status"] == "UP", row


@test("uptime pull: a missing or garbage ratio reads None, never crashes")
def _():
    mod = load_endpoint("web/api/health_report.py", "health_report_ratio_bad_test")
    for raw in (None, "", "n/a", "100.000-"):
        row = mod._uptime_row({"friendly_name": "x", "custom_uptime_ratio": raw},
                              "2026-08-01")
        assert row["uptime_7d"] is None and row["uptime_30d"] is None, (raw, row)
    assert mod._uptime_row({"friendly_name": "x"}, "2026-08-01")["status"] == "UNKNOWN"


@test("uptime pull: response times collapse to one daily average int")
def _():
    # Decision 1 in the plan: keep the daily average, not the raw 5-minute
    # series (~2,600 rows per monitor per day).
    mod = load_endpoint("web/api/health_report.py", "health_report_avg_test")
    row = mod._uptime_row({"friendly_name": "garm", "status": 2,
                           "response_times": [{"datetime": 1, "value": 280},
                                              {"datetime": 2, "value": 283}]},
                          "2026-08-01")
    assert row["avg_response_ms"] == 282 and isinstance(row["avg_response_ms"], int), row
    empty = mod._uptime_row({"friendly_name": "garm", "response_times": []},
                            "2026-08-01")
    assert empty["avg_response_ms"] is None, empty


@test("uptime pull: cron send writes exactly one row per monitor, dated today")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        writes = mod._uptime_writes
        assert len(writes) == 2, f"expected one row per monitor: {writes}"
        today = lab_today().isoformat()
        assert [w[0] for w in writes] == [today, today], writes
        assert [w[1] for w in writes] == ["garm-monitor", "prompt-labs"], writes
        assert h.body["uptime_rows"] == 2, h.body
    finally:
        restore()


@test("uptime pull: ?dry=1 writes NOTHING — a reader must not trigger a write")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report?dry=1", _health_cookie("reader"))
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert mod._uptime_writes == [], (
            "dry run archived uptime — ?dry=1 is open to any authenticated role, "
            f"so that is a privilege leak: {mod._uptime_writes}")
        assert not sent
    finally:
        restore()


@test("uptime pull: an UptimeRobot outage still sends the email")
def _():
    restore = _health_env()
    try:
        mod, sent = _health_mod(ur="error")
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(sent) == 1, "a failed uptime pull killed the email"
        assert h.body["uptime_rows"] == 0, h.body
        assert mod._uptime_writes == [], mod._uptime_writes
    finally:
        restore()


@test("uptime pull: no UPTIMEROBOT_API_KEY → skipped quietly, email unaffected")
def _():
    # The key is in mini's .env.local but not yet in Vercel; until it is, the
    # cron must behave exactly as before rather than erroring nightly.
    restore = _health_env()
    try:
        os.environ.pop("UPTIMEROBOT_API_KEY", None)
        mod, sent = _health_mod()
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert len(sent) == 1
        assert h.body["uptime_rows"] == 0, h.body
        assert mod._uptime_writes == [], mod._uptime_writes
    finally:
        restore()


@test("uptime pull: the row count reaches the email body, loud when zero")
def _():
    # The Aug 2 gap: uptime_rows lived only in the JSON response, which nothing
    # reads, so a totally failed pull looked identical to a good one in the
    # inbox. The count must land in the body — and 0 must be unmissable.
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        invoke(mod, "/api/health_report", {"authorization": "Bearer cron-secret"})
        _, html, text = sent[0]
        assert "2 monitors archived" in text, text
        assert "2 monitors archived" in html, html

        mod, sent = _health_mod(ur="error")
        invoke(mod, "/api/health_report", {"authorization": "Bearer cron-secret"})
        _, html, text = sent[0]
        assert "uptime archive: 0 rows written" in text, text
        assert "uptime archive: 0 rows written" in html, html
    finally:
        restore()


@test("uptime pull: the archive still fills while emails are paused")
def _():
    # Pausing the EMAIL for a week must not punch a week-long hole in the
    # archive — the two are independent artifacts.
    restore = _health_env()
    try:
        mod, sent = _health_mod()
        base = mod.turso_query

        def paused_turso(sql, args=None):
            if "health_email_state" in sql:
                return [{"value": "2099-01-01T00:00:00Z"}]
            return base(sql, args)
        mod.turso_query = paused_turso
        h = invoke(mod, "/api/health_report",
                   {"authorization": "Bearer cron-secret"})
        assert h.body["skipped"] == "paused", h.body
        assert not sent
        assert len(mod._uptime_writes) == 2, mod._uptime_writes
    finally:
        restore()


# === uptime_overview.py (read side; contract fixed in the plan) ===

def _uptime_ov(rows, path="/api/uptime_overview", authed=True):
    """Invoke uptime_overview with the archive query stubbed.
    Returns (captured_sql_list, response)."""
    mod = load_endpoint("web/api/uptime_overview.py", "endpoint_uptime_ov")
    captured = []

    def fake_turso(sql, args=None):
        captured.append((sql, args or []))
        if callable(rows):
            return rows(sql, args)
        return rows

    restore_q = patch_turso_query(mod, fake_turso)
    restore_a = patch(mod, is_authenticated=lambda _: authed)
    try:
        h = invoke(mod, path)
    finally:
        restore_a()
        restore_q()
    return captured, h


@test("uptime_overview: anonymous → 401, archive never read")
def _():
    captured, h = _uptime_ov([], authed=False)
    assert h.status_code == 401, f"got {h.status_code}: {h.body}"
    assert captured == [], f"queried before rejecting: {captured}"


@test("uptime_overview: returns the contract Phase 2 builds against")
def _():
    captured, h = _uptime_ov([
        {"date": "2026-08-01", "monitor": "garm", "uptime_1d": 100.0,
         "uptime_7d": 100.0, "uptime_30d": 99.98, "avg_response_ms": 281,
         "status": "UP"},
        {"date": "2026-08-02", "monitor": "garm", "uptime_1d": 99.5,
         "uptime_7d": 99.9, "uptime_30d": 99.97, "avg_response_ms": 300,
         "status": "UP"},
        {"date": "2026-08-02", "monitor": "prntd", "uptime_1d": 100.0,
         "uptime_7d": 100.0, "uptime_30d": 100.0, "avg_response_ms": 120,
         "status": "UP"},
    ])
    assert h.status_code == 200, f"got {h.status_code}: {h.body}"
    body = h.body
    assert set(body) >= {"days", "monitors", "generated_at"}, sorted(body)
    assert body["days"] == 30, body["days"]
    assert body["generated_at"].endswith("Z"), body["generated_at"]
    names = [m["name"] for m in body["monitors"]]
    assert names == ["garm", "prntd"], names
    garm = body["monitors"][0]
    assert set(garm) >= {"name", "uptime_30d", "uptime_7d", "uptime_1d",
                         "avg_response_ms", "status", "series"}, sorted(garm)
    # Headline figures come from the newest row, not the first one seen.
    assert garm["uptime_1d"] == 99.5 and garm["uptime_30d"] == 99.97, garm
    assert garm["avg_response_ms"] == 300 and garm["status"] == "UP", garm
    assert garm["series"] == [
        {"date": "2026-08-01", "uptime": 100.0, "ms": 281},
        {"date": "2026-08-02", "uptime": 99.5, "ms": 300}], garm["series"]
    assert "date >= ?" in captured[0][0], captured[0][0]


@test("uptime_overview: an empty archive is a valid 200, not an error")
def _():
    # The archive starts at zero rows and fills one day at a time; there is no
    # backfill (v2 exposes rolling ratios only, so history would be invented).
    _, h = _uptime_ov([])
    assert h.status_code == 200, f"got {h.status_code}: {h.body}"
    assert h.body["monitors"] == [], h.body
    assert h.body["days"] == 30, h.body


@test("uptime_overview: Turso's string-encoded numbers are coerced")
def _():
    # Recurring gotcha: Turso hands back numeric columns as JSON strings.
    _, h = _uptime_ov([
        {"date": "2026-08-01", "monitor": "garm", "uptime_1d": "100.000",
         "uptime_7d": "99.980", "uptime_30d": "99.990",
         "avg_response_ms": "281", "status": "UP"},
    ])
    m = h.body["monitors"][0]
    assert isinstance(m["uptime_1d"], float) and m["uptime_1d"] == 100.0, m
    assert isinstance(m["avg_response_ms"], int) and m["avg_response_ms"] == 281, m
    assert m["series"][0] == {"date": "2026-08-01", "uptime": 100.0, "ms": 281}, m


@test("uptime_overview: nulls survive as null, not 0")
def _():
    # A monitor with no response-time samples has an unknown latency; 0ms would
    # be a lie the chart would happily draw.
    _, h = _uptime_ov([
        {"date": "2026-08-01", "monitor": "garm", "uptime_1d": None,
         "uptime_7d": None, "uptime_30d": None, "avg_response_ms": None,
         "status": "PAUSED"},
    ])
    m = h.body["monitors"][0]
    assert m["avg_response_ms"] is None and m["uptime_30d"] is None, m
    assert m["series"][0]["ms"] is None, m["series"]


@test("uptime_overview: days windows the query and is clamped, never 400s")
def _():
    captured, h = _uptime_ov([], path="/api/uptime_overview?days=90")
    assert h.body["days"] == 90, h.body
    since = captured[0][1][0]
    expected = (lab_today() - timedelta(days=89)).isoformat()
    assert since == expected, f"{since} != {expected}"
    _, h2 = _uptime_ov([], path="/api/uptime_overview?days=banana")
    assert h2.body["days"] == 30, h2.body


@test("uptime_overview: an unreadable archive says so — never a silent empty")
def _():
    # #45's whole point: absence must not read as 'nothing to report'.
    def boom(sql, args=None):
        raise RuntimeError("turso unreachable")
    _, h = _uptime_ov(boom)
    assert h.status_code == 200, f"got {h.status_code}: {h.body}"
    assert h.body["monitors"] == [], h.body
    assert h.body.get("unavailable") is True, h.body


# === private_history.py ===

PRIVHIST_KEY = "test-service-key"


def _privhist(fake_turso, name, key=PRIVHIST_KEY):
    """Load private_history with a stubbed Turso and the service key set."""
    mod = load_endpoint("web/api/private_history.py", name)
    restore_turso = patch_turso_query(mod, fake_turso)
    saved = os.environ.get("SERVICE_HISTORY_KEY")
    if key is None:
        os.environ.pop("SERVICE_HISTORY_KEY", None)
    else:
        os.environ["SERVICE_HISTORY_KEY"] = key

    def restore():
        restore_turso()
        if saved is None:
            os.environ.pop("SERVICE_HISTORY_KEY", None)
        else:
            os.environ["SERVICE_HISTORY_KEY"] = saved
    return mod, restore


def _privhist_rows(sql, args=None):
    """Turso stub: aggregates come back as STRINGS, as the real one does."""
    if "project_aliases" in sql:
        return []
    if "FROM daily_summaries" in sql and "GROUP BY" in sql:
        return [
            {"week_of": "2026-07-20", "session_count": "3",
             "commit_count": "0", "prompt_count": "40"},
            {"week_of": "2026-07-27", "session_count": "9",
             "commit_count": "21", "prompt_count": "140"},
        ]
    if "FROM daily_summaries" in sql:
        return [{"first_at": "2025-03-11", "last_at": "2026-08-01",
                 "sessions": "412", "commits": "1180", "prompts": "9001"}]
    if "FROM weekly_rollups" in sql:
        return [{"week_start": "2026-07-27", "session_count": "9",
                 "commit_count": "21"}]
    return []


@test("private_history: 401 without a bearer key")
def _():
    mod, restore = _privhist(_privhist_rows, "endpoint_privhist_401")
    try:
        h = invoke(mod, "/api/private_history?project=musicforge")
        assert h.status_code == 401, f"got {h.status_code}: {h.body}"
        assert h.body.get("error") == "unauthorized"
    finally:
        restore()


@test("private_history: 401 with the wrong bearer key")
def _():
    mod, restore = _privhist(_privhist_rows, "endpoint_privhist_401b")
    try:
        h = invoke(mod, "/api/private_history?project=musicforge",
                   headers={"authorization": "Bearer nope"})
        assert h.status_code == 401, f"got {h.status_code}: {h.body}"
    finally:
        restore()


@test("private_history: 503 when no service key is configured (never fails open)")
def _():
    mod, restore = _privhist(_privhist_rows, "endpoint_privhist_503", key=None)
    try:
        h = invoke(mod, "/api/private_history?project=musicforge",
                   headers={"authorization": "Bearer anything"})
        assert h.status_code == 503, f"got {h.status_code}: {h.body}"
        assert "activity" not in h.body, h.body
    finally:
        restore()


@test("private_history: 400 when project missing")
def _():
    mod, restore = _privhist(_privhist_rows, "endpoint_privhist_400")
    try:
        h = invoke(mod, "/api/private_history",
                   headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        assert h.status_code == 400, f"got {h.status_code}: {h.body}"
    finally:
        restore()


@test("private_history: 200 full envelope with the key")
def _():
    mod, restore = _privhist(_privhist_rows, "endpoint_privhist_200")
    try:
        h = invoke(mod, "/api/private_history?project=musicforge",
                   headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        b = h.body
        assert b["project"] == "musicforge", b
        assert b["first_activity_at"] == "2025-03-11", b
        assert b["last_activity_at"] == "2026-08-01", b
        # Turso's string aggregates must arrive as real ints.
        assert b["total_sessions"] == 412 and isinstance(b["total_sessions"], int), b
        assert b["total_commits"] == 1180 and isinstance(b["total_commits"], int), b
        # activity is oldest → newest, ints throughout.
        assert [r["week_of"] for r in b["activity"]] == \
            ["2026-07-20", "2026-07-27"], b["activity"]
        assert b["activity"][1] == {
            "week_of": "2026-07-27", "session_count": 9,
            "commit_count": 21, "prompt_count": 140}, b["activity"]
        # Tier 1: rollups carry counts only, sessions is empty.
        assert b["rollups"] == [{"week_of": "2026-07-27", "public_summary": None,
                                "session_count": 9, "commit_count": 21}], b
        assert b["sessions"] == [], b
    finally:
        restore()


@test("private_history: unknown project → empty 200 envelope")
def _():
    def empty(sql, args=None):
        return []
    mod, restore = _privhist(empty, "endpoint_privhist_unknown")
    try:
        h = invoke(mod, "/api/private_history?project=nope",
                   headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        b = h.body
        assert b["activity"] == [] and b["rollups"] == [] and b["sessions"] == [], b
        assert b["first_activity_at"] is None and b["last_activity_at"] is None, b
        assert b["total_sessions"] == 0 and b["total_commits"] == 0, b
    finally:
        restore()


@test("private_history: NULL/absent counts render as 0, never null")
def _():
    def nulls(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "FROM daily_summaries" in sql and "GROUP BY" in sql:
            return [{"week_of": "2026-07-27", "session_count": None,
                     "commit_count": None, "prompt_count": None}]
        if "FROM daily_summaries" in sql:
            return [{"first_at": None, "last_at": None, "sessions": None,
                     "commits": None, "prompts": None}]
        if "FROM weekly_rollups" in sql:
            return [{"week_start": "2026-07-27", "session_count": None,
                     "commit_count": None}]
        return []
    mod, restore = _privhist(nulls, "endpoint_privhist_zeros")
    try:
        h = invoke(mod, "/api/private_history?project=musicforge",
                   headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        b = h.body
        assert b["total_sessions"] == 0 and b["total_commits"] == 0, b
        assert b["activity"][0] == {"week_of": "2026-07-27", "session_count": 0,
                                    "commit_count": 0, "prompt_count": 0}, b
        assert b["rollups"][0]["session_count"] == 0, b
        assert b["rollups"][0]["commit_count"] == 0, b
    finally:
        restore()


@test("private_history: alias folding expands the WHERE clause")
def _():
    seen = []

    def aliased(sql, args=None):
        if "canonical FROM project_aliases" in sql and "alias = ?" in sql:
            return [{"canonical": "selected-projects"}]
        if "alias FROM project_aliases" in sql:
            return [{"alias": "pianohouse"}]
        seen.append((sql, list(args or [])))
        return _privhist_rows(sql, args)

    mod, restore = _privhist(aliased, "endpoint_privhist_alias")
    try:
        h = invoke(mod, "/api/private_history?project=pianohouse",
                   headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        assert h.status_code == 200, f"got {h.status_code}: {h.body}"
        assert seen, "no data queries ran"
        for sql, args in seen:
            assert "IN (?,?)" in sql, sql
            assert args[:2] == ["selected-projects", "pianohouse"], args
        # The echoed key stays what the consumer asked for.
        assert h.body["project"] == "pianohouse", h.body
    finally:
        restore()


@test("private_history: queries select no prose columns (Tier 1 structural guarantee)")
def _():
    seen = []

    def spy(sql, args=None):
        seen.append(sql)
        return _privhist_rows(sql, args)

    mod, restore = _privhist(spy, "endpoint_privhist_noprose")
    try:
        invoke(mod, "/api/private_history?project=musicforge",
               headers={"authorization": f"Bearer {PRIVHIST_KEY}"})
        for sql in seen:
            low = sql.lower()
            for banned in ("narrative", "highlights", "summary", "key_decisions"):
                assert banned not in low, f"{banned} in {sql}"
    finally:
        restore()


# === garm consumer ===
import garm_helper  # noqa: E402


def _fake_urlopen(status=200, body=None, raise_exc=None):
    import io

    class _Resp(io.BytesIO):
        def __init__(self, b, st):
            super().__init__(b)
            self.status = st

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        fake.calls.append((req, timeout))
        if raise_exc:
            raise raise_exc
        return _Resp(json.dumps(body or {}).encode(), status)
    fake.calls = []
    return fake


@test("garm: fetch_grants → bare slugs from the prompt-lab: namespace + wildcard; foreign grants dropped")
def _():
    os.environ["GARM_URL"] = "https://garm.test"
    os.environ["GARM_KEY"] = "garm_x"
    fake = _fake_urlopen(body={"grants": [{"project": "prompt-lab:prntd", "role": "viewer"},
                                          {"project": "prntd", "role": "owner"},   # another app's grant — ignored
                                          {"project": "*", "role": "viewer"}]})
    r = patch(garm_helper, urlopen=fake)
    try:
        got = garm_helper.fetch_grants("pierre@example.com")
    finally:
        r()
    assert got == {"prntd", "*"}, got
    req, timeout = fake.calls[0]
    assert timeout == 2.0, timeout
    assert req.get_header("Authorization") == "Bearer garm_x"
    assert req.get_header("X-garm-contract") == "1"
    assert "email=pierre%40example.com" in req.full_url, req.full_url


@test("garm: fetch_grants → empty set when no grants (not None)")
def _():
    r = patch(garm_helper, urlopen=_fake_urlopen(body={"grants": []}))
    try:
        assert garm_helper.fetch_grants("x@y.z") == set()
    finally:
        r()


@test("garm: fetch_grants → None on exception / non-200 / bad json (fail closed)")
def _():
    for fake in (_fake_urlopen(raise_exc=OSError("down")),
                 _fake_urlopen(status=401, body={}),
                 _fake_urlopen(body={"nope": 1})):
        r = patch(garm_helper, urlopen=fake)
        try:
            assert garm_helper.fetch_grants("x@y.z") is None
        finally:
            r()


@test("garm: GARM_ENABLED honours GARM_GATING=off only")
def _():
    os.environ.pop("GARM_GATING", None)
    assert garm_helper.GARM_ENABLED()
    os.environ["GARM_GATING"] = "OFF"
    assert not garm_helper.GARM_ENABLED()
    os.environ["GARM_GATING"] = "on"
    assert garm_helper.GARM_ENABLED()


@test("garm: vercel.json includeFiles carries garm_helper + access_helper")
def _():
    v = json.loads((ROOT / "web" / "vercel.json").read_text())
    inc = v["functions"]["api/**/*.py"]["includeFiles"]
    assert "garm_helper.py" in inc and "access_helper.py" in inc, inc


from auth_helper import make_token, COOKIE_NAME  # noqa: E402


def _hdr(token):
    return {"cookie": f"{COOKIE_NAME}={token}"}


@test("access: admin → projects None (unfiltered), no cookie refresh, Garm never called")
def _():
    os.environ["AUTH_SECRET"] = "s"
    called = []
    r = patch(access_helper, fetch_grants=lambda e: called.append(e) or {"x"})
    try:
        a = access_helper.resolve_access(_hdr(make_token("admin", "nlovejoy@me.com")))
    finally:
        r()
    assert a.role == "admin" and a.projects is None and a.set_cookie is None, a
    assert called == [], called
    assert access_helper.allowed(a, "anything")


@test("access: reader with fresh grants_at → projects from cookie, no Garm call")
def _():
    called = []
    r = patch(access_helper, fetch_grants=lambda e: called.append(e) or set())
    try:
        a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y", ["prntd"])))
    finally:
        r()
    assert a.projects == frozenset({"prntd"}) and a.set_cookie is None and called == []
    assert access_helper.allowed(a, "prntd") and not access_helper.allowed(a, "musicforge")


@test("access: reader with stale grants_at → re-resolves, returns Set-Cookie with new set")
def _():
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": ["prntd"], "grants_at": int(time.time()) - 601})
    r = patch(access_helper, fetch_grants=lambda e: {"musicforge"})
    try:
        a = access_helper.resolve_access(_hdr(stale))
    finally:
        r()
    assert a.projects == frozenset({"musicforge"}), a
    assert a.set_cookie and COOKIE_NAME in a.set_cookie


@test("access: stale + Garm down → empty projects for this request, cookie NOT rewritten")
def _():
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": ["prntd"], "grants_at": 0})
    r = patch(access_helper, fetch_grants=lambda e: None)
    try:
        a = access_helper.resolve_access(_hdr(stale))
    finally:
        r()
    assert a is not None and a.projects == frozenset() and a.set_cookie is None, a


@test("access: reader cookie with NO projects key (pre-Garm cookie) → treated as stale")
def _():
    r = patch(access_helper, fetch_grants=lambda e: {"prntd"})
    try:
        a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y")))
    finally:
        r()
    assert a.projects == frozenset({"prntd"}) and a.set_cookie


@test("access: wildcard grant allows everything; GARM_GATING=off → reader unfiltered")
def _():
    a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y", ["*"])))
    assert access_helper.allowed(a, "anything")
    os.environ["GARM_GATING"] = "off"
    try:
        a = access_helper.resolve_access(_hdr(make_token("reader", "p@x.y")))
        assert a.projects is None
    finally:
        os.environ.pop("GARM_GATING")


@test("access: filter_rows drops disallowed rows via canon()")
def _():
    a = access_helper.Access("reader", "p@x.y", frozenset({"raconte"}), None)
    rows = [{"project": "recountly"}, {"project": "prntd"}]
    out = access_helper.filter_rows(a, rows, canon=lambda n: {"recountly": "raconte"}.get(n, n))
    assert out == [{"project": "recountly"}], out


@test("access: unauthenticated → None")
def _():
    assert access_helper.resolve_access({}) is None


def _reader_hdr(projects):
    return {"cookie": f"{COOKIE_NAME}={make_token('reader', 'p@x.y', projects)}"}


@test("overview: reader sees only granted projects in cards, activity, all_projects")
def _():
    ov = load_endpoint("web/api/overview.py", "ov_garm")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return [{"alias": "recountly", "canonical": "raconte"}]
        if "project_metadata" in sql:
            # A real row for a project the reader is NOT granted — the
            # project_metadata roster is independent of daily_summaries/
            # snapshots, so this must be filtered on its own, not merely by
            # coincidence of what other tables returned.
            return [{"project": "raconte", "category": "Collabs",
                     "private": 0, "status": "active"}]
        if "daily_summaries" in sql:
            return [{"project": "prntd", "date": "2026-08-20", "prompt_count": 3},
                    {"project": "recountly", "date": "2026-08-20", "prompt_count": 5}]
        if "project_snapshots" in sql:
            return [{"project": "prntd", "snapshot_date": "2026-08-20", "data": "{}"},
                    {"project": "raconte", "snapshot_date": "2026-08-20", "data": "{}"}]
        return []
    r = patch_turso_query(ov, fake)
    try:
        cap = invoke(ov, "/api/overview", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    assert cap.body["all_projects"] == ["prntd"], cap.body["all_projects"]
    assert "raconte" not in json.dumps(cap.body), "raconte leaked into overview"
    assert "raconte" not in cap.body["project_metadata"], cap.body["project_metadata"]


@test("overview: admin unfiltered; reader with stale cookie gets Set-Cookie on the JSON response")
def _():
    ov = load_endpoint("web/api/overview.py", "ov_garm2")
    r1 = patch_turso_query(ov, lambda sql, args=None: [])
    from auth_helper import _sign
    stale = _sign({"exp": int(time.time()) + 1000, "role": "reader", "email": "p@x.y",
                   "projects": [], "grants_at": 0})
    r2 = patch(access_helper, fetch_grants=lambda e: {"prntd"})
    try:
        cap = invoke(ov, "/api/overview", {"cookie": f"{COOKIE_NAME}={stale}"})
    finally:
        r2()
        r1()
    assert any(k == "Set-Cookie" for k, _ in cap.response_headers), cap.response_headers


@test("day: reader sees only granted projects in `projects` and re-summed `totals`")
def _():
    dy = load_endpoint("web/api/day.py", "day_garm")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return [{"alias": "recountly", "canonical": "raconte"}]
        if "daily_summaries" in sql:
            return [{"project": "prntd", "summary": "p work", "key_decisions": "[]",
                      "prompts": 3, "sessions": 1, "commits": 1},
                     {"project": "recountly", "summary": "r work", "key_decisions": "[]",
                      "prompts": 5, "sessions": 2, "commits": 0}]
        if "api_costs" in sql:
            return [{"project": "prntd", "usd": 1.5}, {"project": "raconte", "usd": 2.5}]
        return []
    r = patch_turso_query(dy, fake)
    try:
        cap = invoke(dy, "/api/day?date=2026-08-20", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    names = [p["project"] for p in cap.body["projects"]]
    assert names == ["prntd"], names
    assert cap.body["totals"] == {"prompts": 3, "sessions": 1, "commits": 1}, cap.body["totals"]
    assert "raconte" not in json.dumps(cap.body), "raconte leaked into day"


@test("day: visitors/uptime are admin-only — omitted for a filtered reader, present for admin")
def _():
    def fake(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "daily_summaries" in sql:
            return [{"project": "prntd", "summary": "p work", "key_decisions": "[]",
                     "prompts": 1, "sessions": 1, "commits": 0}]
        if "page_views" in sql:
            return [{"site": "prompt-lab", "views": 4}]
        if "uptime_daily" in sql:
            return [{"monitor": "prntd", "uptime_1d": 100.0, "status": "up"}]
        return []

    dy_reader = load_endpoint("web/api/day.py", "day_garm_visibility_reader")
    r = patch_turso_query(dy_reader, fake)
    try:
        cap = invoke(dy_reader, "/api/day?date=2026-08-20", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    assert cap.body["visitors"] is None, cap.body["visitors"]
    assert cap.body["uptime"] is None, cap.body["uptime"]

    dy_admin = load_endpoint("web/api/day.py", "day_garm_visibility_admin")
    r = patch_turso_query(dy_admin, fake)
    r2 = patch(dy_admin, resolve_access=lambda h: access_helper.Access(
        "admin", "nlovejoy@me.com", None, None))
    try:
        cap = invoke(dy_admin, "/api/day?date=2026-08-20", {})
    finally:
        r2()
        r()
    assert cap.status_code == 200, cap.body
    assert cap.body["visitors"] is not None, cap.body["visitors"]
    assert cap.body["uptime"] is not None, cap.body["uptime"]


@test("activity_timeline: filter_rows runs before folding, so a disallowed row can't reach the sum")
def _():
    at = load_endpoint("web/api/activity_timeline.py", "at_garm_prefold")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "daily_summaries" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "sessions": 1, "prompts": 3, "commits": 1},
                    {"date": "2026-08-20", "project": "raconte", "sessions": 9, "prompts": 90, "commits": 9}]
        return []
    r = patch_turso_query(at, fake)
    try:
        cap = invoke(at, "/api/activity_timeline", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    rows = cap.body["rows"]
    assert len(rows) == 1 and rows[0]["project"] == "prntd", rows
    # If the disallowed row had leaked into the fold before filtering, prntd's
    # own counts would be inflated by raconte's — pin that they aren't.
    assert rows[0]["prompts"] == 3 and rows[0]["sessions"] == 1, rows[0]


@test("cost_overview: filter_rows runs before folding, so a disallowed row can't reach the sum")
def _():
    co = load_endpoint("web/api/cost_overview.py", "co_garm_prefold")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "api_costs" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "model": "opus", "cost_usd": 1.0},
                    {"date": "2026-08-20", "project": "raconte", "model": "opus", "cost_usd": 99.0}]
        return []
    r = patch_turso_query(co, fake)
    try:
        cap = invoke(co, "/api/cost_overview", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    rows = cap.body["rows"]
    assert len(rows) == 1 and rows[0]["project"] == "prntd", rows
    assert abs(rows[0]["cost_usd"] - 1.0) < 1e-9, rows[0]


@test("activity_timeline: reader sees no disallowed project rows")
def _():
    at = load_endpoint("web/api/activity_timeline.py", "at_garm")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return [{"alias": "recountly", "canonical": "raconte"}]
        if "daily_summaries" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "sessions": 1, "prompts": 3, "commits": 1},
                    {"date": "2026-08-20", "project": "recountly", "sessions": 2, "prompts": 5, "commits": 0}]
        return []
    r = patch_turso_query(at, fake)
    try:
        cap = invoke(at, "/api/activity_timeline", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    assert "raconte" not in json.dumps(cap.body), "raconte leaked into activity_timeline"
    assert all(row["project"] == "prntd" for row in cap.body["rows"]), cap.body["rows"]


@test("cost_overview: reader sees no disallowed project rows")
def _():
    co = load_endpoint("web/api/cost_overview.py", "co_garm")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return [{"alias": "recountly", "canonical": "raconte"}]
        if "api_costs" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "model": "opus", "cost_usd": 1.0},
                    {"date": "2026-08-20", "project": "recountly", "model": "opus", "cost_usd": 2.0}]
        return []
    r = patch_turso_query(co, fake)
    try:
        cap = invoke(co, "/api/cost_overview", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 200, cap.body
    assert "raconte" not in json.dumps(cap.body), "raconte leaked into cost_overview"
    assert all(row["project"] == "prntd" for row in cap.body["rows"]), cap.body["rows"]


# === project.py / cost_timeline.py: reader gating (Task 5) ===

@test("project: reader asking for a project outside their grants → 403, no Turso query")
def _():
    pj = load_endpoint("web/api/project.py", "pj_garm")
    calls = []
    r = patch_turso_query(pj, lambda sql, args=None: calls.append(sql) or [])
    try:
        cap = invoke(pj, "/api/project?name=musicforge", _reader_hdr(["prntd"]))
    finally:
        r()
    assert cap.status_code == 403, cap.status_code
    assert not [s for s in calls if "daily_summaries" in s], calls


@test("project: reader asking by ALIAS of a granted canonical → 200")
def _():
    pj = load_endpoint("web/api/project.py", "pj_garm2")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return [{"alias": "recountly", "canonical": "raconte"}]
        return []
    r = patch_turso_query(pj, fake)
    try:
        cap = invoke(pj, "/api/project?name=recountly", _reader_hdr(["raconte"]))
    finally:
        r()
    assert cap.status_code == 200, cap.status_code


@test("cost_timeline: reader without ?project → only granted projects' rows; disallowed ?project → 403")
def _():
    ct = load_endpoint("web/api/cost_timeline.py", "ct_garm")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "api_costs" in sql:
            return [{"date": "2026-08-20", "project": "prntd", "usd": 1},
                    {"date": "2026-08-20", "project": "musicforge", "usd": 2}]
        return []
    r = patch_turso_query(ct, fake)
    try:
        cap = invoke(ct, "/api/cost_timeline", _reader_hdr(["prntd"]))
        assert "musicforge" not in json.dumps(cap.body), cap.body
        cap2 = invoke(ct, "/api/cost_timeline?project=musicforge", _reader_hdr(["prntd"]))
        assert cap2.status_code == 403, cap2.status_code
    finally:
        r()


@test("cost_timeline: admin unscoped call gets byte-identical shape — no project key added")
def _():
    ct = load_endpoint("web/api/cost_timeline.py", "ct_garm_admin")

    def fake(sql, args=None):
        if "project_aliases" in sql:
            return []
        if "api_costs" in sql:
            return [{"date": "2026-08-20", "model": "opus", "cost_usd": 1}]
        if "api_usage" in sql:
            return [{"date": "2026-08-20", "model": "opus", "input_tokens": 1}]
        return []
    r = patch_turso_query(ct, fake)
    r2 = patch(ct, resolve_access=lambda h: access_helper.Access("admin", "a@b.c", None, None))
    try:
        cap = invoke(ct, "/api/cost_timeline")
        assert cap.status_code == 200, cap.status_code
        assert all("project" not in row for row in cap.body["costs"]), cap.body["costs"]
        assert all("project" not in row for row in cap.body["usage"]), cap.body["usage"]
    finally:
        r2()
        r()


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
