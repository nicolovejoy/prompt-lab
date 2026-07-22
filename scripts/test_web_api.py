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


# === cost_overview.py ===

@test("cost_overview: 401 when not authenticated")
def _():
    mod = load_endpoint("web/api/cost_overview.py", "endpoint_costov_unauth")
    restore_q = patch_turso_query(mod, lambda *a, **kw: [])
    restore_a = patch(mod, is_authenticated=lambda _: False)

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
    restore_a = patch(mod, is_authenticated=lambda _: True)

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
    restore_a = patch(mod, is_authenticated=lambda _: True)

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
    os.environ.setdefault("AUTH_SECRET", "test-secret")
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
    bad = [json.dumps({"path": "/", "event": "login"}).encode(),  # not allowed yet
           json.dumps({"path": "no-slash"}).encode(),
           json.dumps(["not", "a", "dict"]).encode(),
           b"not json at all"]
    for body in bad:
        assert mod.parse_event(GOOD_HEADERS, body) is None, f"not dropped: {body!r}"


@test("beacon: visitor hash varies by IP, never exposes it")
def _():
    import os
    mod = load_endpoint("web/api/beacon.py", "endpoint_beacon_hash")
    os.environ.setdefault("AUTH_SECRET", "test-secret")
    a = mod._visitor_hash("203.0.113.9", GOOD_UA)
    b = mod._visitor_hash("203.0.113.10", GOOD_UA)
    a2 = mod._visitor_hash("203.0.113.9", GOOD_UA)
    assert a != b, "different IPs should hash differently"
    assert a == a2, "same-day same-input hash should be stable"
    assert "203" not in a


@test("beacon: BEACON_SALT is the salt of record and pins the hash byte-for-byte")
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
        # BEACON_SALT is set — this is what survives the OAuth cutover.
        os.environ["AUTH_SECRET"] = "auth-secret-B"
        assert mod._visitor_hash(ip, ua) == got, "AUTH_SECRET rotation moved the hash"
        # Fallback: with BEACON_SALT unset, it falls back to AUTH_SECRET.
        del os.environ["BEACON_SALT"]
        os.environ["AUTH_SECRET"] = "legacy-secret"
        fb = hashlib.sha256(
            f"legacy-secret|{day}|{ip}|{ua}".encode()).hexdigest()[:16]
        assert mod._visitor_hash(ip, ua) == fb, "fallback to AUTH_SECRET broken"
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
        assert len(inserts[0][1]) == 8

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
        assert all("pageview" in s for s, _ in captured), "event filter missing"
    finally:
        restore()


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
    restore_a = patch(mod, is_authenticated=lambda _: True)
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
    restore_a = patch(mod, is_authenticated=lambda _: True)
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


@test("login GET bare unauthenticated: 401 with password_login=true (non-prod)")
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
    finally:
        restore()


@test("login GET bare unauthenticated: password_login=false in production")
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
        "AUTH_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "ADMIN_EMAILS")
    os.environ["AUTH_SECRET"] = "test-secret"
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
    os.environ["ADMIN_EMAILS"] = "nlovejoy@me.com"
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
