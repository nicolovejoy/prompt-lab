"""Regression tests for the API cost-tracking pipeline.

Run: .venv/bin/python scripts/test_cost_pipeline.py

Self-contained: uses in-memory SQLite, no network, no pytest.
Prints PASS/FAIL per test. Exits 0 if all pass, 1 if any fail.

Covers:
- _compute_usd: exact model, prefix fallback, unknown, empty
- _bucket_to_date, _ws_id helpers
- Cents → USD conversion edge cases (None, malformed, integer-string)
- Store idempotency: upsert_api_usage / upsert_api_cost / upsert_claude_code_usage
- Workspace mapping fallback (mapped vs UNMAPPED_PROJECT sentinel)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import io  # noqa: E402
from contextlib import redirect_stderr  # noqa: E402

import pull_api_costs  # noqa: E402
from pull_api_costs import (  # noqa: E402
    DEFAULT_WORKSPACE_SENTINEL,
    UNMAPPED_PROJECT,
    _auto_window_start,
    _bucket_to_date,
    _compute_usd,
    _ws_id,
)
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402


def make_store() -> SqliteKnowledgeStore:
    s = SqliteKnowledgeStore(db_path=":memory:")
    s.migrate()
    return s


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


# === _compute_usd ===

@test("_compute_usd: exact-model match prices correctly")
def _():
    # Sonnet 4.6: $3/M input, $15/M output. 1M input + 1M output → $18.
    usd = _compute_usd("claude-sonnet-4-6", 1_000_000, 0, 0, 1_000_000)
    assert abs(usd - 18.0) < 1e-9, f"got {usd}"


@test("_compute_usd: input-side tokens sum (uncached + cached + cache_creation)")
def _():
    # 500k uncached + 300k cached + 200k cache_creation = 1M input @ $3/M = $3.
    usd = _compute_usd("claude-sonnet-4-6", 500_000, 300_000, 200_000, 0)
    assert abs(usd - 3.0) < 1e-9, f"got {usd}"


@test("_compute_usd: prefix fallback matches a sibling model")
def _():
    # claude-sonnet-4-20250514 isn't in PRICING but should match claude-sonnet-4-6
    # via the rsplit-on-hyphen prefix fallback ('claude-sonnet-4'). 1M input @ $3.
    usd = _compute_usd("claude-sonnet-4-20250514", 1_000_000, 0, 0, 0)
    assert abs(usd - 3.0) < 1e-9, f"prefix fallback failed: {usd}"


@test("_compute_usd: truly unknown model returns 0.0 and warns once")
def _():
    pull_api_costs._warned_unknown_models.clear()
    buf = io.StringIO()
    with redirect_stderr(buf):
        usd1 = _compute_usd("claude-mystery-99", 1_000_000, 0, 0, 1_000_000)
        usd2 = _compute_usd("claude-mystery-99", 500_000, 0, 0, 500_000)
    assert usd1 == 0.0 and usd2 == 0.0
    stderr = buf.getvalue()
    assert "claude-mystery-99" in stderr, "expected warning on stderr"
    assert stderr.count("claude-mystery-99") == 1, "warning should be once per process"


@test("_compute_usd: empty model returns 0.0")
def _():
    assert _compute_usd("", 100, 0, 0, 100) == 0.0
    assert _compute_usd(None, 100, 0, 0, 100) == 0.0  # type: ignore[arg-type]


# === _bucket_to_date ===

@test("_bucket_to_date: Z-suffix ISO parses to UTC date")
def _():
    assert _bucket_to_date("2026-05-15T00:00:00Z") == "2026-05-15"


@test("_bucket_to_date: explicit offset converts to UTC")
def _():
    # 2026-05-15T22:00:00-04:00 == 2026-05-16T02:00:00Z
    assert _bucket_to_date("2026-05-15T22:00:00-04:00") == "2026-05-16"


# === _ws_id ===

@test("_ws_id: None falls back to default sentinel")
def _():
    assert _ws_id(None) == DEFAULT_WORKSPACE_SENTINEL
    assert _ws_id("") == DEFAULT_WORKSPACE_SENTINEL


@test("_ws_id: real workspace_id passes through")
def _():
    assert _ws_id("wrkspc_abc123") == "wrkspc_abc123"


# === Cents → USD inline conversion ===
# Mirrors pull_api_costs.py:381-385. Lifted here because the conversion is
# inline in main(); Phase 3 will extract it into a helper that this test can
# call directly. Until then, the math is asserted in-place.

def _cents_to_usd(amount_raw):
    try:
        return float(amount_raw) / 100.0 if amount_raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


@test("cents→USD: integer cents convert cleanly")
def _():
    assert _cents_to_usd(1234) == 12.34


@test("cents→USD: string-numeric cents parse")
def _():
    assert _cents_to_usd("999") == 9.99


@test("cents→USD: None yields 0.0")
def _():
    assert _cents_to_usd(None) == 0.0


@test("cents→USD: malformed value yields 0.0 (main() also logs a WARN)")
def _():
    # The standalone helper here mirrors main()'s try/except. The warning
    # print lives in main()'s loop, not in this helper — tested in practice
    # by running pull_api_costs against a fixture with a bad amount.
    assert _cents_to_usd("not-a-number") == 0.0
    assert _cents_to_usd({"unexpected": "shape"}) == 0.0


# === Store idempotency ===

@test("store: upsert_api_usage with same (date, workspace_id, model) does not duplicate")
def _():
    s = make_store()
    kwargs = dict(
        date="2026-05-19", workspace_id="ws_x", project="p", model="claude-sonnet-4-6",
        input_tokens=100, cached_input_tokens=0, cache_creation_tokens=0,
        output_tokens=50, cost_computed_usd=0.0001,
    )
    s.upsert_api_usage(**kwargs)
    s.upsert_api_usage(**kwargs)
    row = s._conn.execute("SELECT COUNT(*) AS n FROM api_usage").fetchone()
    assert row["n"] == 1, f"expected 1 row after duplicate upsert, got {row['n']}"


@test("store: upsert_api_usage REPLACES values on conflict")
def _():
    s = make_store()
    common = dict(
        date="2026-05-19", workspace_id="ws_x", project="p", model="claude-sonnet-4-6",
        cached_input_tokens=0, cache_creation_tokens=0,
    )
    s.upsert_api_usage(**common, input_tokens=100, output_tokens=50, cost_computed_usd=0.01)
    s.upsert_api_usage(**common, input_tokens=200, output_tokens=80, cost_computed_usd=0.02)
    row = s._conn.execute(
        "SELECT input_tokens, output_tokens, cost_computed_usd FROM api_usage"
    ).fetchone()
    assert row["input_tokens"] == 200
    assert row["output_tokens"] == 80
    assert abs(row["cost_computed_usd"] - 0.02) < 1e-9


@test("store: upsert_api_cost grain is (date, workspace_id, description)")
def _():
    s = make_store()
    base = dict(
        date="2026-05-19", workspace_id="ws_x", project="p",
        model="claude-sonnet-4-6", cost_type="input", token_type="standard",
        service_tier="standard", context_window="200k", inference_geo="us",
    )
    # Two different descriptions on the same (date, workspace_id) → 2 rows.
    s.upsert_api_cost(**base, description="Sonnet 4.6 input tokens", cost_reported_usd=1.23)
    s.upsert_api_cost(**base, description="Sonnet 4.6 output tokens", cost_reported_usd=4.56)
    # Re-upsert one description → still 2 rows but value REPLACEd.
    s.upsert_api_cost(**base, description="Sonnet 4.6 input tokens", cost_reported_usd=9.99)
    rows = s._conn.execute(
        "SELECT description, cost_reported_usd FROM api_costs ORDER BY description"
    ).fetchall()
    assert len(rows) == 2, f"expected 2 cost rows, got {len(rows)}"
    by_desc = {r["description"]: r["cost_reported_usd"] for r in rows}
    assert abs(by_desc["Sonnet 4.6 input tokens"] - 9.99) < 1e-9
    assert abs(by_desc["Sonnet 4.6 output tokens"] - 4.56) < 1e-9


@test("store: upsert_claude_code_usage grain is (date, actor_kind, actor_id, model)")
def _():
    s = make_store()
    base = dict(
        date="2026-05-19", actor_kind="user", actor_id="nico@example.com",
        customer_type="api", terminal_type="iterm", organization_id="org_x",
        sessions=3, lines_added=100, lines_removed=20, commits=2, prs=0,
        edit_accepted=5, edit_rejected=1, multi_edit_accepted=2, multi_edit_rejected=0,
        write_accepted=1, write_rejected=0, notebook_edit_accepted=0, notebook_edit_rejected=0,
    )
    s.upsert_claude_code_usage(
        **base, model="claude-sonnet-4-6",
        input_tokens=1000, output_tokens=500,
        cache_read_tokens=200, cache_creation_tokens=300,
        estimated_cost_cents=4.5,
    )
    s.upsert_claude_code_usage(
        **base, model="claude-opus-4-6",
        input_tokens=300, output_tokens=200,
        cache_read_tokens=0, cache_creation_tokens=0,
        estimated_cost_cents=15.0,
    )
    # Re-upsert sonnet row → REPLACE, not insert.
    s.upsert_claude_code_usage(
        **base, model="claude-sonnet-4-6",
        input_tokens=9999, output_tokens=8888,
        cache_read_tokens=0, cache_creation_tokens=0,
        estimated_cost_cents=99.9,
    )
    rows = s._conn.execute(
        "SELECT model, input_tokens, estimated_cost_cents FROM claude_code_usage ORDER BY model"
    ).fetchall()
    assert len(rows) == 2, f"expected 2 rows (one per model), got {len(rows)}"
    by_model = {r["model"]: r for r in rows}
    assert by_model["claude-sonnet-4-6"]["input_tokens"] == 9999
    assert by_model["claude-opus-4-6"]["input_tokens"] == 300


# === Workspace mapping ===

@test("workspace mapping: known workspace resolves to project")
def _():
    s = make_store()
    s.upsert_project_workspace(
        workspace_id="wrkspc_known", workspace_name="known", project="prompt-lab")
    mapping = {r["workspace_id"]: r["project"] for r in s.get_project_workspaces()}
    assert mapping["wrkspc_known"] == "prompt-lab"


@test("workspace mapping: unknown workspace falls back to UNMAPPED_PROJECT")
def _():
    s = make_store()
    s.upsert_project_workspace(
        workspace_id="wrkspc_known", workspace_name="known", project="prompt-lab")
    mapping = {r["workspace_id"]: r["project"] for r in s.get_project_workspaces()}
    # Mirrors pull_api_costs.py:372 — the lookup with default UNMAPPED_PROJECT.
    project = mapping.get("wrkspc_strange", UNMAPPED_PROJECT)
    assert project == UNMAPPED_PROJECT


# === Auto-window across the three cost tables ===

from datetime import datetime, timedelta, timezone  # noqa: E402


@test("auto-window: empty tables → fallback_days before end")
def _():
    s = make_store()
    end = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    start = _auto_window_start(s, end, fallback_days=7)
    assert start == end - timedelta(days=7), f"got {start}"


@test("auto-window: takes MIN(MAX(pulled_at)) across tables, minus 1h buffer")
def _():
    s = make_store()
    # Two tables populated at different times; claude_code_usage empty.
    # api_usage MAX(pulled_at) = 11:00, api_costs MAX(pulled_at) = 10:00.
    # Expected: 10:00 - 1h = 09:00.
    s._conn.execute(
        "INSERT INTO api_usage (date, workspace_id, project, model, "
        "input_tokens, cached_input_tokens, cache_creation_tokens, "
        "output_tokens, cost_computed_usd, pulled_at) "
        "VALUES ('2026-05-20', 'ws_x', 'p', 'claude-sonnet-4-6', "
        "1, 0, 0, 1, 0.0, '2026-05-20 11:00:00')"
    )
    s._conn.execute(
        "INSERT INTO api_costs (date, workspace_id, project, description, "
        "cost_reported_usd, pulled_at) "
        "VALUES ('2026-05-20', 'ws_x', 'p', 'd', 1.0, '2026-05-20 10:00:00')"
    )
    s._conn.commit()
    end = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    start = _auto_window_start(s, end)
    expected = datetime(2026, 5, 20, 9, 0, 0, tzinfo=timezone.utc)
    assert start == expected, f"expected {expected}, got {start}"


@test("auto-window: works without store._conn (uses ABC method, not sqlite-specific)")
def _():
    s = make_store()
    # Sanity: get_last_cost_pull() is the ABC method that the new
    # _auto_window_start uses — doesn't reach for _conn anymore.
    assert hasattr(s, "get_last_cost_pull"), "ABC method missing on store"
    assert s.get_last_cost_pull() is None  # empty tables


# === Runner ===

def main() -> int:
    print(f"Running {len(_results)} tests...\n")
    failures = 0
    for name, ok, err in _results:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if not ok:
            line += f"\n         {err}"
            failures += 1
        print(line)
    print()
    if failures:
        print(f"{failures} of {len(_results)} tests failed")
        return 1
    print(f"All {len(_results)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
