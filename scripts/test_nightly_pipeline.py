"""Tests for nightly_pipeline.py (nightly-pipeline-plan step 2).

The runner is exercised with real subprocesses (tiny python one-liners), so
ordering, dependency skips, timeouts, and the publish-always property are
asserted on actual end state, not on mocks of subprocess.

Run: .venv/bin/python scripts/test_nightly_pipeline.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nightly_pipeline as np  # noqa: E402

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


PY = sys.executable


def touch_stage(name: str, out_dir: str, exit_code: int = 0) -> np.Stage:
    """A stage that appends its name to an order file, then exits."""
    code = (f"open({str(Path(out_dir) / 'order')!r}, 'a').write('{name} ');"
            f"import sys; sys.exit({exit_code})")
    return np.Stage(name, [PY, "-c", code], timeout=30)


def order_in(out_dir: str) -> list[str]:
    p = Path(out_dir) / "order"
    return p.read_text().split() if p.exists() else []


@test("stages run in declared order")
def _():
    with tempfile.TemporaryDirectory() as d:
        stages = [touch_stage(n, d) for n in ("a", "b", "c")]
        results = np.run_pipeline(stages, cwd=Path(d))
        assert order_in(d) == ["a", "b", "c"], f"ran {order_in(d)}"
        assert all(r.ok for r in results)


@test("a failed stage skips its dependents")
def _():
    with tempfile.TemporaryDirectory() as d:
        synth = touch_stage("synth", d, exit_code=1)
        review = touch_stage("review", d)
        review.needs = ("synth",)
        results = {r.name: r for r in np.run_pipeline([synth, review], cwd=Path(d))}
        assert results["synth"].outcome == "failed"
        assert results["review"].outcome == "skipped", results["review"]
        assert "review" not in order_in(d), "dependent ran despite failed need"


@test("publish (always=True) runs even when everything upstream failed")
def _():
    with tempfile.TemporaryDirectory() as d:
        synth = touch_stage("synth", d, exit_code=1)
        review = touch_stage("review", d)
        review.needs = ("synth",)
        publish = touch_stage("publish", d)
        publish.always = True
        results = {r.name: r for r in
                   np.run_pipeline([synth, review, publish], cwd=Path(d))}
        assert results["publish"].outcome == "ok", results["publish"]
        assert order_in(d) == ["synth", "publish"]


@test("a hung stage is killed at its (monotonic) timeout and later stages continue")
def _():
    with tempfile.TemporaryDirectory() as d:
        hung = np.Stage("hung", [PY, "-c", "import time; time.sleep(30)"], timeout=1)
        after = touch_stage("after", d)
        after.always = True
        results = {r.name: r for r in np.run_pipeline([hung, after], cwd=Path(d))}
        assert results["hung"].outcome == "timeout", results["hung"]
        assert results["after"].outcome == "ok"


@test("a false condition marks the stage not-due and does not fail the run")
def _():
    with tempfile.TemporaryDirectory() as d:
        report = touch_stage("report", d)
        report.condition = lambda: (False, "already produced")
        results = {r.name: r for r in np.run_pipeline([report], cwd=Path(d))}
        assert results["report"].outcome == "not-due"
        assert order_in(d) == [], "stage ran despite false condition"


@test("a true condition lets the stage run")
def _():
    with tempfile.TemporaryDirectory() as d:
        report = touch_stage("report", d)
        report.condition = lambda: (True, "")
        results = {r.name: r for r in np.run_pipeline([report], cwd=Path(d))}
        assert results["report"].outcome == "ok"


@test("report_due: no snapshot ever -> due")
def _():
    due, _reason = np.report_due(None, date(2026, 8, 29))
    assert due


@test("report_due: current period already covered -> not due")
def _():
    due, reason = np.report_due("2026-08-16", date(2026, 8, 29))
    assert not due, "16th snapshot covers the 16th-EOM period"
    assert "2026-08-16" in reason


@test("report_due: last period's snapshot does not cover this one -> due")
def _():
    # Snapshot from the 1st-15th period; today is in the 16th-EOM period.
    due, _reason = np.report_due("2026-08-01", date(2026, 8, 16))
    assert due
    # Late catch-up: the 1st slept through, machine wakes on the 3rd.
    due, _reason = np.report_due("2026-07-16", date(2026, 8, 3))
    assert due


@test("report_period_start: 1st-15th maps to the 1st, 16th-EOM to the 16th")
def _():
    assert np.report_period_start(date(2026, 8, 1)) == date(2026, 8, 1)
    assert np.report_period_start(date(2026, 8, 15)) == date(2026, 8, 1)
    assert np.report_period_start(date(2026, 8, 16)) == date(2026, 8, 16)
    assert np.report_period_start(date(2026, 8, 31)) == date(2026, 8, 16)


@test("build_stages wires the real pipeline: order, needs, publish always")
def _():
    stages = np.build_stages("python")
    names = [s.name for s in stages]
    assert names == ["cost-pull", "synthesizer", "review", "report", "publish"], names
    by = {s.name: s for s in stages}
    assert by["review"].needs == ("synthesizer",)
    assert by["report"].needs == ("synthesizer",)
    assert by["report"].condition is not None, "report must be artifact-gated"
    assert by["publish"].always, "publish must run unconditionally"
    assert not by["publish"].needs
    for s in stages:
        assert s.timeout > 0


@test("run_identity derives run_id from started_at and host")
def _():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 30, 9, 30, 4, tzinfo=timezone.utc)
    run_id, started_at, lab_date = np.run_identity(now, "laptop")
    assert started_at == "2026-08-30T09:30:04Z", started_at
    # 09:30 UTC on Aug 30 is 02:30 Pacific the SAME day — the nightly slot.
    assert lab_date == "2026-08-30", lab_date
    assert run_id == "2026-08-30T09:30:04Z|laptop", run_id


@test("lab_date is Pacific, not UTC (the 5pm rollover trap)")
def _():
    from datetime import datetime, timezone
    # 02:00 UTC on Aug 30 is 19:00 Pacific on Aug 29.
    now = datetime(2026, 8, 30, 2, 0, 0, tzinfo=timezone.utc)
    _, _, lab_date = np.run_identity(now, "laptop")
    assert lab_date == "2026-08-29", lab_date


@test("overall_status distinguishes ok, partial and failed")
def _():
    R = np.StageResult
    assert np.overall_status([R("a", "ok"), R("b", "not-due")]) == "ok"
    assert np.overall_status([R("a", "ok"), R("b", "failed")]) == "partial"
    assert np.overall_status([R("a", "failed"), R("b", "timeout")]) == "failed"
    assert np.overall_status([]) == "failed"


@test("record_run never raises when the store blows up")
def _():
    class Exploding:
        def upsert_nightly_run(self, **kw):
            raise RuntimeError("turso is down")

    ok = np.record_run(Exploding(), run_id="r1", host="laptop",
                       started_at="2026-08-30T09:30:04Z",
                       lab_date="2026-08-30", status="running")
    assert ok is False, "a failed monitoring write must report False, not raise"


@test("record_run returns True on success and forwards every field")
def _():
    seen = {}

    class Capturing:
        def upsert_nightly_run(self, **kw):
            seen.update(kw)

    ok = np.record_run(Capturing(), run_id="r1", host="laptop",
                       started_at="2026-08-30T09:30:04Z",
                       lab_date="2026-08-30", status="ok",
                       finished_at="2026-08-30T09:34:00Z",
                       stages=[{"name": "publish", "outcome": "ok"}],
                       exit_code=0)
    assert ok is True
    assert seen["status"] == "ok"
    assert seen["stages"][0]["name"] == "publish"
    assert seen["exit_code"] == 0


@test("collect_claims reports a max date per artifact and never raises")
def _():
    class _Cursor:
        """Mirrors sqlite3.Cursor's fetchone(), which production code calls."""

        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class FakeStore:
        def __init__(self, rows):
            self.rows = rows

        class _Conn:
            def __init__(self, rows):
                self.rows = rows

            def execute(self, sql, params=None):
                return _Cursor((self.rows.get(sql),))

        @property
        def conn(self):
            return self._Conn(self.rows)

    from web.artifact_checks import ARTIFACT_CHECKS
    rows = {sql: "2026-08-29" for _, sql, _ in ARTIFACT_CHECKS}
    claims = np.collect_claims(FakeStore(rows))
    assert set(claims) == {label for label, _, _ in ARTIFACT_CHECKS}, claims
    assert all(v == "2026-08-29" for v in claims.values()), claims


@test("collect_claims survives a store that raises")
def _():
    class Exploding:
        @property
        def conn(self):
            raise RuntimeError("db gone")

    assert np.collect_claims(Exploding()) == {}


@test("ARTIFACT_CHECKS excludes uptime archive (no local counterpart)")
def _():
    from web.artifact_checks import ARTIFACT_CHECKS
    labels = {label for label, _, _ in ARTIFACT_CHECKS}
    assert "uptime archive" not in labels, (
        "uptime_daily is cloud-direct — the pipeline cannot claim it locally")


class _FakeRemote:
    """Minimal store double: records upserts, answers get_nightly_runs."""

    def __init__(self, existing=None, explode=False):
        self.rows = dict(existing or {})
        self.explode = explode

    def upsert_nightly_run(self, **kw):
        if self.explode:
            raise RuntimeError("turso down")
        self.rows[kw["run_id"]] = kw

    def get_nightly_runs(self, *, limit=10, started_after=None):
        rows = sorted(self.rows.values(), key=lambda r: r["started_at"],
                      reverse=True)
        if started_after:
            rows = [r for r in rows if r["started_at"] > started_after]
        return rows[:limit]


class _FakeLocal(_FakeRemote):
    pass


@test("push_runs sends only rows newer than the remote high-water mark")
def _():
    local = _FakeLocal()
    for n, ts in [("a", "2026-08-27T09:30:00Z"), ("b", "2026-08-28T09:30:00Z"),
                  ("c", "2026-08-29T09:30:00Z")]:
        local.upsert_nightly_run(run_id=n, host="laptop", started_at=ts,
                                 lab_date=ts[:10], status="ok")
    remote = _FakeRemote()
    remote.upsert_nightly_run(run_id="a", host="laptop",
                              started_at="2026-08-27T09:30:00Z",
                              lab_date="2026-08-27", status="ok")
    pushed = np.push_runs(local, remote)
    assert pushed == 2, pushed
    assert set(remote.rows) == {"a", "b", "c"}, remote.rows


@test("push_runs backfills every run when the remote is empty")
def _():
    local = _FakeLocal()
    for n, ts in [("a", "2026-08-27T09:30:00Z"), ("b", "2026-08-28T09:30:00Z")]:
        local.upsert_nightly_run(run_id=n, host="laptop", started_at=ts,
                                 lab_date=ts[:10], status="ok")
    remote = _FakeRemote()
    assert np.push_runs(local, remote) == 2
    assert set(remote.rows) == {"a", "b"}


@test("push_runs is a no-op when the remote is already current")
def _():
    local = _FakeLocal()
    local.upsert_nightly_run(run_id="a", host="laptop",
                             started_at="2026-08-27T09:30:00Z",
                             lab_date="2026-08-27", status="ok")
    remote = _FakeRemote(existing={"a": {"run_id": "a", "host": "laptop",
                                         "started_at": "2026-08-27T09:30:00Z",
                                         "lab_date": "2026-08-27",
                                         "status": "ok"}})
    assert np.push_runs(local, remote) == 0


@test("push_runs never raises when the remote is down")
def _():
    local = _FakeLocal()
    local.upsert_nightly_run(run_id="a", host="laptop",
                             started_at="2026-08-27T09:30:00Z",
                             lab_date="2026-08-27", status="ok")
    assert np.push_runs(local, _FakeRemote(explode=True)) == 0


# === main(): the bracket around a run =======================================
#
# The ordering these pin is what the whole run record rests on: a "running"
# row before the first stage, the final row after the last, the Turso push
# after that. And the failure envelope around it — a prelude that cannot set
# the monitoring up, or a monitoring call that raises mid-run, must never
# cost the night's actual work or leave the local row stuck on "running".


class _StubCursor:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return (self._value,)


class _StubConn:
    """Answers collect_claims' queries so it stays quiet in these tests."""

    def execute(self, sql, params=None):
        return _StubCursor("2026-08-29")


class _MainStore:
    """A store double that logs every run-record write into a shared list."""

    def __init__(self, events, name):
        self.events, self.name = events, name
        self.rows: dict = {}
        self.closed = self.migrated = False

    def migrate(self):
        self.migrated = True

    def upsert_nightly_run(self, **kw):
        self.events.append((self.name, kw.get("status")))
        self.rows[kw["run_id"]] = kw

    def get_nightly_runs(self, *, limit=10, started_after=None):
        rows = sorted(self.rows.values(), key=lambda r: r["started_at"],
                      reverse=True)
        if started_after:
            rows = [r for r in rows if r["started_at"] > started_after]
        return rows[:limit]

    def close(self):
        self.closed = True

    @property
    def conn(self):
        return _StubConn()


@contextmanager
def fake_main_env(results, *, prelude_error=None):
    """Run main() against stubbed stages, stores and machine label.

    `store` is replaced in sys.modules because main() imports it lazily, by
    name, exactly as the real pipeline does — stubbing the import is what
    lets this exercise the real bracket rather than a copy of it.
    """
    events: list = []
    local = _MainStore(events, "local")
    remote = _MainStore(events, "remote")
    calls = {"run_pipeline": 0}

    def get_store(backend=None):
        if backend == "turso":
            return remote
        if prelude_error is not None:
            raise prelude_error
        return local

    fake_store_mod = types.ModuleType("store")
    fake_store_mod.get_store = get_store
    saved_mod = sys.modules.get("store")
    sys.modules["store"] = fake_store_mod

    def fake_run_pipeline(stages, cwd=None):
        calls["run_pipeline"] += 1
        return results

    saved = (np.machine_host, np.build_stages, np.run_pipeline)
    np.machine_host = lambda: "testhost"
    np.build_stages = lambda: []
    np.run_pipeline = fake_run_pipeline
    try:
        yield events, local, remote, calls
    finally:
        np.machine_host, np.build_stages, np.run_pipeline = saved
        if saved_mod is None:
            sys.modules.pop("store", None)
        else:
            sys.modules["store"] = saved_mod


def ok_results() -> list:
    return [np.StageResult(n, "ok") for n in
            ("cost-pull", "synthesizer", "review", "publish")]


@test("main brackets the run: running row, then final row, then the push")
def _():
    with fake_main_env(ok_results()) as (events, local, remote, _):
        saved_run = np.subprocess.run
        np.subprocess.run = lambda *a, **kw: None  # the cost-pull heartbeat
        try:
            code = np.main()
        finally:
            np.subprocess.run = saved_run
    assert code == 0, code
    assert events == [("local", "running"), ("local", "ok"), ("remote", "ok")], \
        events
    assert local.closed, "the local store handle leaked"
    assert remote.migrated, "push_runs ran against an unmigrated remote"


@test("main records the run's real status and exit code when a stage fails")
def _():
    results = [np.StageResult("cost-pull", "ok"),
               np.StageResult("synthesizer", "failed", "exit 1"),
               np.StageResult("publish", "ok")]
    with fake_main_env(results) as (events, local, _remote, _):
        code = np.main()
    assert code == 1, code
    assert events[1] == ("local", "partial"), events
    row = local.rows[next(iter(local.rows))]
    assert row["exit_code"] == 1, row
    assert [s["outcome"] for s in row["stages"]] == ["ok", "failed", "ok"], row


@test("a run-record prelude that raises still runs the night's stages")
def _():
    """The whole point of the guard: the cost pull, synthesizer, review and
    publish must happen even when the monitoring cannot be set up at all."""
    with fake_main_env(ok_results(),
                       prelude_error=RuntimeError("db unreachable")) as (
            events, local, _remote, calls):
        saved_run = np.subprocess.run
        np.subprocess.run = lambda *a, **kw: None
        try:
            code = np.main()
        finally:
            np.subprocess.run = saved_run
    assert calls["run_pipeline"] == 1, "the stages never ran"
    assert code == 0, code
    assert events == [], events  # nothing to write to, and nothing raised


@test("a raising heartbeat still writes the finish record")
def _():
    """subprocess.run raises TimeoutExpired, and it sits between the stages
    and the finish write. Unguarded, the local row stays "running" forever
    and the next morning's email reports "died mid-run" about a night that
    completed every stage — the second axis manufacturing a false verdict
    about the first."""
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="heartbeat.py", timeout=60)

    with fake_main_env(ok_results()) as (events, local, _remote, _):
        saved_run = np.subprocess.run
        np.subprocess.run = boom
        try:
            code = np.main()
        finally:
            np.subprocess.run = saved_run
    assert code == 0, code
    assert events == [("local", "running"), ("local", "ok"), ("remote", "ok")], \
        events
    assert local.closed, "the local store handle leaked"


@test("a bare invocation is accepted and runs the night")
def _():
    assert np.parse_argv([]) is None


@test("--help prints usage and runs nothing")
def _():
    assert np.parse_argv(["--help"]) == 0
    assert np.parse_argv(["-h"]) == 0


@test("an unrecognized argument refuses to run the night")
def _():
    """The whole point. nightly_pipeline.py sends the review email, writes
    review_snapshots and pushes to Turso, and this repo's own habit is to run
    nightly stages by hand while awake. A no-op-looking flag that silently
    triggers a full production run is the failure to prevent: on 2026-08-29 a
    `--help` probe did exactly that, ran the cost pull and left a spurious
    failed nightly_runs row. Anything unrecognized must exit non-zero having
    run nothing at all."""
    for argv in (["--help-me"], ["--dry-run"], ["--dryrun"], ["today"],
                 ["-n"], ["--help", "--dry-run"]):
        assert np.parse_argv(argv) == 2, argv


@test("the argv guard runs before the run record, so a typo writes no row")
def _():
    """A refused invocation must not appear in nightly_runs. The run record is
    the thing the morning health email grades; a typo at the keyboard writing
    a row there would manufacture a fact about a night that never ran."""
    with fake_main_env(ok_results()) as (events, _local, _remote, _):
        code = np.main(["--nope"])
    assert code == 2, code
    assert events == [], events


@test("the pipeline loads .env itself before opening the remote store")
def _():
    """Found by the 2026-08-30 acceptance run, which otherwise passed clean:
    every STAGE is a subprocess whose script calls load_env() itself, which is
    why publish reached Turso — but push_runs is the one piece that runs
    IN-PROCESS, inheriting launchd's bare environment. It died on
    KeyError: 'TURSO_DATABASE_URL', best-effort swallowed it, and Turso's
    nightly_runs stayed empty while every stage reported ok.

    Pinned as source text, not behaviour: the bug is the ABSENCE of a call,
    and a test that fakes the environment would pass with the call deleted —
    which is exactly how this shipped. Same grep-guard shape the repo already
    uses for describe_elapsed and the 'weekday 1' week expression."""
    src = (ROOT / "nightly_pipeline.py").read_text()
    assert "load_env" in src, \
        "nightly_pipeline.py must load .env — push_runs runs in-process " \
        "and launchd supplies no TURSO_DATABASE_URL"

    # Behavioural, not textual: _finish_run is DEFINED above main() but CALLED
    # from inside it, so asserting on source order compares file position to
    # execution order and gets the wrong answer. Assert the call actually
    # happens, and happens before the run opens any store.
    import claude_api
    calls: list = []
    saved = claude_api.load_env
    claude_api.load_env = lambda *a, **kw: calls.append("load_env")
    try:
        with fake_main_env(ok_results()) as (events, _local, _remote, _):
            np.main()
    finally:
        claude_api.load_env = saved
    assert calls == ["load_env"], \
        f"expected exactly one load_env() call in the prelude, got {calls}"
    assert events and events[0] == ("local", "running"), \
        f"env must load before the first store write, got {events[:1]}"


def main() -> int:
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
