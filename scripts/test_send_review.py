"""Regression tests for the review email's "Today" window (the 2:30am bug).

Run: .venv/bin/python scripts/test_send_review.py

The nightly review fires at 2:30am and used to ask for *today's* data —
structurally empty, since a day's summaries are written at the end of that
day — and picked sessions by `started_at` in a rolling UTC day, so a long
session was invisible to the day it actually worked (raconte ran 31 hours
across Aug 10-11 and never appeared in an Aug 11 "today").

Pinned here:
- "Today" means yesterday's completed lab-day (Pacific), never the run date.
- Sessions are selected by *overlap* with that day's UTC bounds, not by
  started_at, and an unfinished session (ended_at NULL) still counts.
- The Pacific-day → UTC bounds conversion is DST-correct.

No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from day_helper import lab_today  # noqa: E402
from store.sqlite_store import SqliteKnowledgeStore  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except AssertionError as e:
            _results.append((name, False, str(e) or "assertion failed"))
        except Exception as e:  # noqa: BLE001
            _results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn

    return deco


def _load_send_review():
    spec = importlib.util.spec_from_file_location("send_review", ROOT / "send-review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_store_with_sessions(rows):
    """In-memory store with a hand-made sessions table (the hook owns its DDL)."""
    store = SqliteKnowledgeStore(":memory:")
    store.migrate()
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, project TEXT, started_at TEXT,
            ended_at TEXT, summary TEXT, utility INTEGER, hostname TEXT
        )
    """)
    store._conn.executemany(
        "INSERT INTO sessions (id, project, started_at, ended_at, summary, hostname)"
        " VALUES (?, ?, ?, ?, ?, 'testhost')", rows)
    store._conn.commit()
    return store


@test("clocks: lab_day_bounds_utc is DST-correct (PDT summer, PST winter)")
def _():
    from day_helper import lab_day_bounds_utc
    assert lab_day_bounds_utc("2026-08-11") == ("2026-08-11 07:00:00", "2026-08-12 07:00:00"), \
        f"summer bounds wrong: {lab_day_bounds_utc('2026-08-11')}"
    assert lab_day_bounds_utc("2026-01-15") == ("2026-01-15 08:00:00", "2026-01-16 08:00:00"), \
        f"winter bounds wrong: {lab_day_bounds_utc('2026-01-15')}"


@test("sessions are selected by overlap with the day, not by started_at")
def _():
    # Lab-day 2026-08-11 = UTC [2026-08-11 07:00, 2026-08-12 07:00)
    store = _mem_store_with_sessions([
        # the raconte case: 31h session spanning into the day — must count
        ("s1", "raconte", "2026-08-10 16:03:00", "2026-08-11 22:51:00", "long session"),
        # entirely before the day — must not count
        ("s2", "oldwork", "2026-08-09 12:00:00", "2026-08-09 13:00:00", "done earlier"),
        # started inside the day, still running (ended_at NULL) — must count
        ("s3", "ongoing", "2026-08-11 20:00:00", None, "in flight"),
        # started after the day ended — must not count
        ("s4", "tomorrow", "2026-08-12 08:00:00", "2026-08-12 09:00:00", "next day"),
        # overlaps but never summarized — excluded (nothing to narrate)
        ("s5", "silent", "2026-08-11 10:00:00", "2026-08-11 11:00:00", None),
    ])
    got = store.get_raw_sessions(
        overlap_utc=("2026-08-11 07:00:00", "2026-08-12 07:00:00"))
    projects = sorted(s["project"] for s in got)
    store.close()
    assert projects == ["ongoing", "raconte"], f"got {projects}"


@test("since_days selection still works unchanged")
def _():
    store = _mem_store_with_sessions([
        ("s1", "recent", "2099-01-01 00:00:00", "2099-01-01 01:00:00", "future = recent"),
        ("s2", "ancient", "2000-01-01 00:00:00", "2000-01-01 01:00:00", "old"),
    ])
    got = store.get_raw_sessions(since_days=1)
    store.close()
    assert [s["project"] for s in got] == ["recent"], f"got {got}"


@test("review window: 'today' is yesterday's completed lab-day, week reaches 7 back")
def _():
    mod = _load_send_review()
    w = mod.review_windows()
    yesterday = (lab_today() - timedelta(days=1)).isoformat()
    week_since = (lab_today() - timedelta(days=7)).isoformat()
    assert w["review_day"] == yesterday, f"review_day={w['review_day']}, want {yesterday}"
    assert w["week_since"] == week_since, f"week_since={w['week_since']}, want {week_since}"
    assert "day_start_utc" not in w, "UTC bounds should be gone with the raw-session read"


@test("send-review no longer queries daily summaries with the run date")
def _():
    src = (ROOT / "send-review.py").read_text()
    assert "get_daily_summaries(since=today_str)" not in src, \
        "the 2:30am bug is back: daily summaries fetched with the run date"
    assert "get_raw_sessions" not in src, \
        "send-review must not read the raw tier: it is machine-local, and " \
        "reading it is why the email said 'no new work' on busy days"
    assert 'get_store("turso")' in src, \
        "reads must go through the merged (Turso) store"
    assert 'until=w["review_day"]' in src, \
        "the Today window must be closed on both ends (until is inclusive)"


@test("build_prompt composes from summaries and rollups, with counts inline")
def _():
    mod = _load_send_review()
    daily = [{"date": "2026-08-12", "project": "raconte", "summary": "Shipped the exporter.",
              "prompt_count": 24, "session_count": 3}]
    weekly = daily + [{"date": "2026-08-10", "project": "musicforge",
                       "summary": "Fixed the mixer.", "prompt_count": 10, "session_count": 1}]
    rollups = [{"project": "raconte", "week_start": "2026-08-03", "narrative": "A big week."}]
    system, user_msg = mod.build_prompt(daily, weekly, rollups, is_weekly=False)
    assert "raconte" in user_msg and "musicforge" in user_msg
    assert "24 prompts" in user_msg, "per-day counts must reach the model"
    assert "A big week." in user_msg
    assert "Session summaries" not in user_msg, "raw-session sections must be gone"


@test("get_store honors an explicit backend argument over the env default")
def _():
    import os

    from store import get_store

    # turso: constructor only reads env, no connection made — safe to build
    had_url = os.environ.get("TURSO_DATABASE_URL")
    had_tok = os.environ.get("TURSO_AUTH_TOKEN")
    os.environ["TURSO_DATABASE_URL"] = "libsql://test.invalid"
    os.environ["TURSO_AUTH_TOKEN"] = "test-token"
    try:
        s = get_store("turso")
        assert type(s).__name__ == "TursoKnowledgeStore", type(s).__name__
    finally:
        if had_url is None:
            del os.environ["TURSO_DATABASE_URL"]
        else:
            os.environ["TURSO_DATABASE_URL"] = had_url
        if had_tok is None:
            del os.environ["TURSO_AUTH_TOKEN"]
        else:
            os.environ["TURSO_AUTH_TOKEN"] = had_tok

    # unknown backend still raises, same as the env path
    try:
        get_store("nope")
        raise AssertionError("unknown backend must raise ValueError")
    except ValueError:
        pass


@test("clocks: a normal call renders as one plain duration")
def test_elapsed_normal():
    from claude_api import describe_elapsed

    out = describe_elapsed(136.3, 136.1)
    assert out == "136.3s", out
    assert "SLEPT" not in out, out


@test("clocks: divergence just under the threshold stays quiet")
def test_elapsed_under_threshold():
    from claude_api import HOST_SLEEP_THRESHOLD_S, describe_elapsed

    out = describe_elapsed(100.0, 100.0 - (HOST_SLEEP_THRESHOLD_S - 1))
    assert "SLEPT" not in out, out


@test("clocks: a sleep-stretched call names the sleep, not API latency")
def test_elapsed_host_slept():
    # The real 2026-08-19->20 numbers: 3h19m wall, ~10min awake.
    from claude_api import describe_elapsed

    out = describe_elapsed(11942.4, 638.0)
    assert "HOST SLEPT" in out, out
    assert "11942.4s wall" in out, out
    assert "638.0s awake" in out, out
    # The whole point is that a reader cannot mistake the wall figure for
    # how long Anthropic took.
    assert "not API latency" in out, out


@test("call_claude returns awake_ms alongside duration_ms")
def test_call_claude_reports_awake():
    import types

    from claude_api import call_claude

    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(input={"ok": True})],
        usage=types.SimpleNamespace(input_tokens=11, output_tokens=22),
    )
    client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=lambda **kw: resp))

    got = call_claude(client, model="m", system="s", user_msg="u",
                      tool={"name": "t"})
    assert got["parsed"] == {"ok": True}, got
    assert "awake_ms" in got, got
    # On a machine that never slept mid-call the two agree closely; the
    # detector is only meaningful because both are recorded.
    assert abs(got["duration_ms"] - got["awake_ms"]) < 1000, got


@test("clocks: both nightly readers still surface the sleep diagnostic")
def test_readers_use_describe_elapsed():
    # A grep, not a behavioural assert, for the same reason the other clocks:
    # guards are greps — if a reader quietly goes back to printing bare
    # duration_ms, the next 3h19m night is undiagnosable again and no
    # functional test would notice.
    for name in ("send-review.py", "generate-report.py"):
        src = (ROOT / name).read_text()
        assert "describe_elapsed" in src, f"{name} no longer reports awake time"


# === #56 guard: local prompts must not go unreported as "no activity" ======
#
# send-review.py binds `get_store` at import time (`from store import
# get_store`), so a fake must sit in sys.modules *before* the module
# executes — the same technique test_nightly_pipeline.py uses for
# nightly_pipeline.py's lazy `import store`.


class _FakeTursoStore:
    """Answers get_daily_summaries/get_weekly_rollups exactly like main() calls them.

    main() calls get_daily_summaries twice: once with `until` set (the 1-day
    window) and once without (the 7-day window) — dispatch on that, not on
    call order.
    """

    def __init__(self, daily_1d=None, weekly=None, rollups=None):
        self.daily_1d = daily_1d or []
        self.weekly = weekly or []
        self.rollups = rollups or []
        self.closed = False

    def get_daily_summaries(self, *, since=None, until=None):
        return self.daily_1d if until else self.weekly

    def get_weekly_rollups(self, *, since=None):
        return self.rollups

    def close(self):
        self.closed = True


class _FakeLocalGuardStore:
    """Tracks whether/how the guard consulted the local prompt count."""

    def __init__(self, count):
        self.count = count
        self.queried_for = None
        self.closed = False

    def count_prompts_on(self, date):
        self.queried_for = date
        return self.count

    def close(self):
        self.closed = True


def _load_send_review_with_store(get_store_fn):
    """Load send-review.py fresh with `store.get_store` replaced by `get_store_fn`."""
    fake_mod = types.ModuleType("store")
    fake_mod.get_store = get_store_fn
    saved = sys.modules.get("store")
    sys.modules["store"] = fake_mod
    try:
        return _load_send_review()
    finally:
        if saved is None:
            sys.modules.pop("store", None)
        else:
            sys.modules["store"] = saved


def _refuse_client():
    raise AssertionError("Claude must not be called")


@test("count_prompts_on buckets by the pinned Pacific zone, independent of host TZ")
def _():
    # Pinned-zone bucketing (the `lab_day` SQLite function) must give the same
    # answer no matter what timezone the host process is running in — unlike
    # 'localtime', which resolves through the OS and made this test (and the
    # guard it covers) silently depend on the machine running it. Run this
    # file under both `TZ=UTC` and `TZ=America/Los_Angeles` to prove it.
    store = SqliteKnowledgeStore(":memory:")
    store.migrate()
    store._conn.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY, project TEXT, timestamp TEXT, prompt TEXT
        )
    """)
    store._conn.executemany(
        "INSERT INTO prompts (project, timestamp, prompt) VALUES (?, ?, ?)",
        [
            # 5:30pm Pacific on Aug 11 (PDT, UTC-7) is 00:30 UTC Aug 12 — the
            # #48 case a bare date(timestamp) (and 'localtime' on a non-Pacific
            # host) would misfile as Aug 12.
            ("raconte", "2026-08-12 00:30:00", "5:30pm Pacific Aug 11"),
            ("raconte", "2026-08-11 20:00:00", "1pm Pacific Aug 11"),
            ("raconte", "2026-08-13 00:30:00", "a different day entirely"),
            # No project — get_unsummarized_days excludes these when producing
            # daily_summaries, so the guard's count must match and exclude it too.
            (None, "2026-08-11 20:00:00", "orphaned prompt, no project"),
        ],
    )
    store._conn.commit()
    got = store.count_prompts_on("2026-08-11")
    store.close()
    assert got == 2, f"expected 2 prompts bucketed into 2026-08-11 Pacific, got {got}"


@test("guard: empty Turso daily + local prompts on review_day exits non-zero, no send")
def _():
    import os

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    turso = _FakeTursoStore(daily_1d=[], weekly=[], rollups=[])
    local = _FakeLocalGuardStore(count=5)

    def get_store(backend=None):
        if backend == "turso":
            return turso
        if backend == "sqlite":
            return local
        raise AssertionError(
            f"guard should exit before any other store is opened (backend={backend!r})")

    mod = _load_send_review_with_store(get_store)
    mod.get_client = _refuse_client
    mod.send_email = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("email must not be sent"))

    review_day = mod.review_windows()["review_day"]
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            mod.main()
        raise AssertionError("main() should have exited non-zero")
    except SystemExit as e:
        assert e.code == 1, f"exit code {e.code}"

    msg = err.getvalue()
    assert review_day in msg, msg
    assert "5" in msg, msg
    assert "Turso has no daily_summaries" in msg, msg
    assert local.queried_for == review_day, local.queried_for
    assert local.closed, "local store handle leaked"
    assert turso.closed, "turso store handle leaked"


@test("guard: empty Turso daily + zero local prompts leaves current behaviour unchanged")
def _():
    import os

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    turso = _FakeTursoStore(daily_1d=[], weekly=[], rollups=[])
    local = _FakeLocalGuardStore(count=0)

    def get_store(backend=None):
        if backend == "turso":
            return turso
        if backend == "sqlite":
            return local
        raise AssertionError(f"unexpected get_store(backend={backend!r})")

    mod = _load_send_review_with_store(get_store)
    mod.get_client = _refuse_client

    out = io.StringIO()
    with redirect_stdout(out):
        result = mod.main()  # falls through to the pre-existing early return

    assert result is None, "should return, not raise or exit"
    assert "No summaries or rollups found" in out.getvalue(), out.getvalue()
    assert local.queried_for is not None, "the guard should still consult the local count"
    assert local.closed, "local store handle leaked"


@test("guard: non-empty Turso daily means the local store is never opened")
def _():
    import os

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    daily = [{"date": "2026-08-12", "project": "raconte", "summary": "Shipped the exporter.",
              "prompt_count": 3, "session_count": 1}]
    turso = _FakeTursoStore(daily_1d=daily, weekly=daily, rollups=[])

    def get_store(backend=None):
        if backend == "turso":
            return turso
        raise AssertionError(
            f"local store must not be opened when Turso already has the day (backend={backend!r})")

    mod = _load_send_review_with_store(get_store)
    mod.get_client = lambda: object()
    mod.call_claude = lambda client, **kw: {
        "parsed": {"subject": "s", "html": "<p>x</p>", "text": "x"},
        "duration_ms": 10, "awake_ms": 10, "input_tokens": 1, "output_tokens": 1,
    }

    saved_argv = sys.argv
    sys.argv = ["send-review.py", "--dry-run"]
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            result = mod.main()
    finally:
        sys.argv = saved_argv

    assert result is None, "dry run should return cleanly"
    assert "(dry run, not sent)" in out.getvalue(), out.getvalue()
    assert turso.closed, "turso store handle leaked"


if __name__ == "__main__":
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    sys.exit(1 if failed else 0)
