"""Tests for nightly_pipeline.py (nightly-pipeline-plan step 2).

The runner is exercised with real subprocesses (tiny python one-liners), so
ordering, dependency skips, timeouts, and the publish-always property are
asserted on actual end state, not on mocks of subprocess.

Run: .venv/bin/python scripts/test_nightly_pipeline.py
No pytest. Prints PASS/FAIL per test, exits 1 if any fail.
"""

from __future__ import annotations

import sys
import tempfile
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


def main() -> int:
    failed = 0
    for name, ok, msg in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
        failed += 0 if ok else 1
    print(f"\n{len(_results) - failed}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
