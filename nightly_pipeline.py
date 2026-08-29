#!/usr/bin/env python3
"""One nightly run, in dependency order: cost pull -> synthesizer -> review ->
report (when due) -> publish. Replaces four racing LaunchAgents
(nightly-pipeline-plan step 2).

Why one process instead of four schedules: launchd coalesces missed
StartCalendarIntervals onto one wake, so agents scheduled 45 minutes apart
start *simultaneously* after a closed-lid night. A scheduler is not a
dependency mechanism; the ordering lives here, where it can be read and
tested.

Rules this file carries forward from the scripts it replaced:

- Pull and publish MUST be coupled (ex run-cost-pull.sh): the pull writes only
  local SQLite while the dashboard reads Turso, so a pull without a sync
  silently drifts the dashboard. Here the coupling is structural — publish is
  the unconditional last stage, downstream of every local write.
- Timeouts are MONOTONIC, never wall-clock. A sleeping Mac stretches
  wall-clock hours around a healthy run (2026-08-20: 11,942s wall / 638s
  awake); subprocess timeouts count monotonic time, which stops during sleep,
  so they bound real work without aborting a slept-through night.
- The cost-pull heartbeat fires only after the publish leg lands — a ping
  after the pull alone would report fresh through exactly the drift the
  coupling exists to prevent.
- The bi-monthly report is artifact-keyed, not schedule-keyed: it runs when
  the current half-month (1st/16th split, Pacific calendar) has no
  monthly_report snapshot yet. A closed lid on the 1st now means a late
  report, not a skipped month.

A failed stage skips its dependents (a review composed over a failed
synthesis would email "no new work" on a busy day — this repo's signature
failure), but publish always runs: syncing a partial night beats leaving
Turso a day behind. Exit is non-zero if any stage failed, and the per-stage
lines in the log are what to read first.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent

LAB_TZ = ZoneInfo("America/Los_Angeles")


@dataclass
class Stage:
    name: str
    argv: list
    timeout: int  # seconds, monotonic
    needs: tuple = ()
    # () -> (should_run, reason); reason is printed when should_run is False
    condition: object = None
    always: bool = False  # run regardless of earlier failures


@dataclass
class StageResult:
    name: str
    outcome: str  # "ok" | "failed" | "timeout" | "skipped" | "not-due"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


def report_period_start(today: date) -> date:
    """The bi-monthly report periods are 1st-15th and 16th-end (Pacific)."""
    return today.replace(day=1 if today.day < 16 else 16)


def report_due(newest_report_date: str | None, today: date) -> tuple[bool, str]:
    """Due when the current half-month has no monthly_report snapshot yet."""
    period = report_period_start(today)
    if newest_report_date and date.fromisoformat(newest_report_date) >= period:
        return False, f"monthly_report {newest_report_date} already covers the period from {period}"
    return True, ""


def _report_due_from_store() -> tuple[bool, str]:
    from store import get_store

    store = get_store()
    try:
        rows = store.get_review_snapshots(review_type="monthly_report", limit=1)
    finally:
        store.close()
    newest = rows[0]["date"] if rows else None
    return report_due(newest, datetime.now(LAB_TZ).date())


def build_stages(py: str = sys.executable) -> list[Stage]:
    return [
        Stage("cost-pull", [py, "pull_api_costs.py"], timeout=900),
        Stage("synthesizer", [py, "synthesizer.py", "--all"], timeout=3600),
        Stage("review", [py, "send-review.py"], timeout=1800,
              needs=("synthesizer",)),
        Stage("report", [py, "generate-report.py", "30"], timeout=1800,
              needs=("synthesizer",), condition=_report_due_from_store),
        Stage("publish", [py, "sync_to_turso.py", "--days", "7"], timeout=900,
              always=True),
    ]


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _elapsed(wall_s: float, mono_s: float) -> str:
    note = ""
    if wall_s - mono_s > 60:
        note = f" — HOST SLEPT ~{(wall_s - mono_s) / 60:.0f}min mid-stage"
    return f"{mono_s:.1f}s awake / {wall_s:.1f}s wall{note}"


def run_stage(stage: Stage, cwd: Path = ROOT) -> StageResult:
    wall0, mono0 = time.time(), time.monotonic()
    print(f"--- stage {stage.name}: start {_stamp()} ---", flush=True)
    try:
        proc = subprocess.run(stage.argv, cwd=cwd, timeout=stage.timeout)
        outcome = "ok" if proc.returncode == 0 else "failed"
        detail = "" if proc.returncode == 0 else f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        outcome, detail = "timeout", f"killed after {stage.timeout}s of awake time"
    elapsed = _elapsed(time.time() - wall0, time.monotonic() - mono0)
    print(f"--- stage {stage.name}: {outcome}{' (' + detail + ')' if detail else ''}"
          f" | {elapsed} ---", flush=True)
    return StageResult(stage.name, outcome, detail)


def run_pipeline(stages: list[Stage], cwd: Path = ROOT) -> list[StageResult]:
    results: dict[str, StageResult] = {}
    for stage in stages:
        unmet = [n for n in stage.needs if not (n in results and results[n].ok)]
        if unmet and not stage.always:
            reason = ", ".join(f"{n}: {results[n].outcome if n in results else 'missing'}"
                               for n in unmet)
            print(f"--- stage {stage.name}: skipped ({reason}) ---", flush=True)
            results[stage.name] = StageResult(stage.name, "skipped", reason)
            continue
        if stage.condition is not None:
            due, reason = stage.condition()
            if not due:
                print(f"--- stage {stage.name}: not due ({reason}) ---", flush=True)
                results[stage.name] = StageResult(stage.name, "not-due", reason)
                continue
        results[stage.name] = run_stage(stage, cwd=cwd)
    return list(results.values())


def run_identity(now_utc: datetime, host: str) -> tuple:
    """(run_id, started_at, lab_date) for a run starting at `now_utc`.

    run_id is deterministic from the pair that identifies a run, so the start
    write and the finish write address the same row without carrying state,
    and a catch-up push cannot mint a second row for a run already sent.

    lab_date is the PACIFIC calendar day (#48). The nightly slot is 02:30
    Pacific, which is 09:30 UTC — the same date — but a run that starts
    before 5pm Pacific on the preceding evening is a different UTC day, and
    grading freshness on a UTC bucket is the phantom-tomorrow bug.
    """
    started_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    lab_date = now_utc.astimezone(LAB_TZ).date().isoformat()
    return f"{started_at}|{host}", started_at, lab_date


def overall_status(results: list) -> str:
    """ok when nothing failed, partial when some did, failed when none ran."""
    if not results:
        return "failed"
    bad = {"failed", "timeout", "skipped"}
    failures = [r for r in results if r.outcome in bad]
    if not failures:
        return "ok"
    return "failed" if len(failures) == len(results) else "partial"


def record_run(store, **fields) -> bool:
    """Write the run record. NEVER raises — returns True if the write landed.

    Same rule as heartbeat.ping and record_login: a monitoring write must not
    be able to fail the work it monitors. A dropped record costs one false
    staleness line in the health email; an exception here would cost the
    night's actual work, which is the wrong trade in every direction.
    """
    try:
        store.upsert_nightly_run(**fields)
        return True
    except Exception as e:  # noqa: BLE001 — deliberately swallowed, see above
        print(f"run record: write failed ({type(e).__name__}: {e})", flush=True)
        return False


def machine_host() -> str:
    """This machine's label, shared with the Turso sync so both agree.

    Imported lazily: sync_to_turso pulls in the store and env loading, and
    nightly_pipeline must stay importable by tests without that cost.
    """
    from sync_to_turso import machine_label
    return machine_label()


def main() -> int:
    from store import get_store

    host = machine_host()
    run_id, started_at, lab_date = run_identity(
        datetime.now(timezone.utc), host)

    store = get_store()
    try:
        store.migrate()
    except Exception as e:  # noqa: BLE001
        print(f"run record: migrate failed ({type(e).__name__}: {e})", flush=True)

    # Written before any stage so a host powered off mid-run leaves a
    # started-never-finished row. "Died mid-run" and "never ran" are
    # different facts and this is the only thing that tells them apart.
    record_run(store, run_id=run_id, host=host, started_at=started_at,
               lab_date=lab_date, status="running")

    stages = build_stages()
    results = run_pipeline(stages)
    by_name = {r.name: r for r in results}

    # Heartbeat only when both legs actually landed (see module docstring).
    if by_name.get("cost-pull") and by_name["cost-pull"].ok \
            and by_name.get("publish") and by_name["publish"].ok:
        subprocess.run([sys.executable, str(ROOT / "heartbeat.py"), "cost-pull"],
                       cwd=ROOT, timeout=60)

    failed = [r for r in results if r.outcome in ("failed", "timeout", "skipped")]
    exit_code = 1 if failed else 0
    summary = " · ".join(f"{r.name}={r.outcome}" for r in results)
    print(f"pipeline: {summary}", flush=True)

    record_run(store, run_id=run_id, host=host, started_at=started_at,
               lab_date=lab_date, status=overall_status(results),
               finished_at=datetime.now(timezone.utc).strftime(
                   "%Y-%m-%dT%H:%M:%SZ"),
               stages=[{"name": r.name, "outcome": r.outcome,
                        "detail": r.detail} for r in results],
               exit_code=exit_code)
    try:
        store.close()
    except Exception:  # noqa: BLE001
        pass
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
