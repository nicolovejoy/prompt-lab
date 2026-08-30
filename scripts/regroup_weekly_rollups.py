"""Audit (and where unambiguous, fix) weekly_rollups damaged by the Monday
week-grouping bug.

Until 2026-08-08 the shared week bucket was `date(d,'weekday 1','-7 days')`.
SQLite's 'weekday N' is next-or-SAME day, so a Monday mapped to the PREVIOUS
Monday: every Monday was filed under the prior week. The related
completed-weeks filter `date < date('now','weekday 1')` resolved to NEXT
Monday on Tue-Sun, admitting the in-progress week.

What that left in weekly_rollups (keys are written at /handoff and
synthesizer time, so fixing the read expression does not repair them):

  1. non-monday-keys   week_start values that aren't Mondays. None are
                       expected (the buggy expression still returned a
                       Monday); the fix is mechanical and unambiguous, so
                       this is the only section --apply touches.
  2. folded-mondays    rollups whose daily_summary_ids include a summary
                       dated week_start+7 — /handoff's GROUP_CONCAT folded
                       the next Monday into the prior week's prose and
                       counts. Prose cannot be unfolded mechanically:
                       REPORT ONLY.
  3. missing-weeks     completed (project, week) pairs with daily summaries
                       but no rollup — Monday-only weeks the bug routed into
                       an already-rolled-up prior week. REPORT ONLY: the
                       fixed synthesizer//handoff check now sees these and
                       will generate them; where the Monday was also folded
                       (section 2) the prior week's prose will still mention
                       it — de-duplication is a human call.
  4. frozen-partials   summaries that sit in a week which HAS a rollup but
                       are referenced by none of that week's rollups. The
                       completed-weeks filter admitted in-progress weeks, a
                       mid-week rollup got written, and the never-revisit
                       join froze it — later days never made it in. The
                       repair is delete-and-let-the-fixed-pipeline
                       regenerate, which destroys existing prose: REPORT
                       ONLY, with the DELETE to run by hand.

Dry run by default; --apply executes section 1 only. Respects
GROUND_CONTROL_STORE, so `GROUND_CONTROL_STORE=turso python
scripts/regroup_weekly_rollups.py` audits Turso (which mirrors local via
sync_to_turso.py — note a local key fix syncs as a NEW Turso row, leaving
the stale-keyed row to delete by hand).

Usage:
  python scripts/regroup_weekly_rollups.py            # audit, no writes
  python scripts/regroup_weekly_rollups.py --apply    # fix non-Monday keys
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store

WEEK_EXPR = "date({col}, 'weekday 0', '-6 days')"  # Monday of the containing week


def q(store, sql: str, args: list | None = None) -> list[dict]:
    """Run a read query on either backend, returning list-of-dicts."""
    args = args or []
    if hasattr(store, "_conn"):  # sqlite
        return [dict(r) for r in store._conn.execute(sql, args).fetchall()]
    return store._rows_to_dicts(store._execute(sql, args))


def execute(store, sql: str, args: list) -> None:
    if hasattr(store, "_conn"):
        store._conn.execute(sql, args)
        store._conn.commit()
    else:
        store._execute(sql, args)


def current_monday() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def audit_non_monday_keys(store) -> list[dict]:
    return q(store, """
        SELECT id, project, week_start,
               date(week_start, 'weekday 0', '-6 days') AS correct_key
        FROM weekly_rollups
        WHERE week_start != date(week_start, 'weekday 0', '-6 days')
        ORDER BY week_start
    """)


def audit_folded_mondays(store) -> list[dict]:
    # Turso's daily_summaries mirrors local, and both backends have json_each.
    return q(store, """
        WITH linked AS (
            SELECT wr.id AS rollup_id, wr.project, wr.week_start,
                   ds.id AS ds_id, ds.date
            FROM weekly_rollups wr
            JOIN json_each(wr.daily_summary_ids) je
            JOIN daily_summaries ds ON ds.id = je.value
        )
        SELECT m.rollup_id, m.project, m.week_start, m.ds_id, m.date,
               date(m.date, 'weekday 0', '-6 days') AS correct_week,
               EXISTS (
                   SELECT 1 FROM linked l
                   WHERE l.ds_id = m.ds_id
                     AND l.week_start = date(m.date, 'weekday 0', '-6 days')
               ) AS also_in_correct_rollup
        FROM linked m
        WHERE m.date < m.week_start OR m.date > date(m.week_start, '+6 days')
        ORDER BY m.date
    """)


def audit_missing_weeks(store, monday: str) -> list[dict]:
    return q(store, """
        WITH ds AS (
            SELECT COALESCE(a.canonical, d.project) AS project,
                   date(d.date, 'weekday 0', '-6 days') AS week_start,
                   COUNT(*) AS days,
                   SUM(d.date = date(d.date, 'weekday 0', '-6 days')) AS mondays
            FROM daily_summaries d
            LEFT JOIN project_aliases a ON a.alias = d.project
            WHERE d.date < ?
            GROUP BY 1, 2
        ),
        wr AS (
            SELECT DISTINCT COALESCE(a.canonical, w.project) AS project,
                   w.week_start
            FROM weekly_rollups w
            LEFT JOIN project_aliases a ON a.alias = w.project
        )
        SELECT ds.project, ds.week_start, ds.days, ds.mondays
        FROM ds LEFT JOIN wr
            ON wr.project = ds.project AND wr.week_start = ds.week_start
        WHERE wr.project IS NULL
        ORDER BY ds.week_start
    """, [monday])


def audit_frozen_partials(store) -> list[dict]:
    # Canonicalize both sides: a summary counts as covered if ANY rollup of
    # its project-week references it (aliased pairs must not read as damage).
    return q(store, """
        WITH canon_wr AS (
            SELECT w.id, COALESCE(a.canonical, w.project) AS project,
                   w.week_start, w.daily_summary_ids
            FROM weekly_rollups w
            LEFT JOIN project_aliases a ON a.alias = w.project
        ),
        canon_ds AS (
            SELECT d.id, COALESCE(a.canonical, d.project) AS project, d.date
            FROM daily_summaries d
            LEFT JOIN project_aliases a ON a.alias = d.project
        ),
        missed AS (
            SELECT DISTINCT ds.id AS ds_id, ds.project, ds.date,
                   date(ds.date, 'weekday 0', '-6 days') AS week_start
            FROM canon_ds ds
            JOIN canon_wr wr ON wr.project = ds.project
                AND wr.week_start = date(ds.date, 'weekday 0', '-6 days')
            WHERE NOT EXISTS (
                SELECT 1 FROM canon_wr w2, json_each(w2.daily_summary_ids) je
                WHERE w2.project = ds.project
                  AND w2.week_start = date(ds.date, 'weekday 0', '-6 days')
                  AND je.value = ds.id)
        )
        SELECT m.project, m.week_start,
               GROUP_CONCAT(m.date) AS missing_dates,
               (SELECT GROUP_CONCAT(w3.id) FROM canon_wr w3
                WHERE w3.project = m.project
                  AND w3.week_start = m.week_start) AS rollup_ids
        FROM missed m
        GROUP BY m.project, m.week_start
        ORDER BY m.week_start, m.project
    """)


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    store = get_store()
    monday = current_monday()
    exit_code = 0
    try:
        print(f"mode: {'APPLY' if apply else 'dry run'}   "
              f"current week's Monday: {monday}")

        total = q(store, "SELECT COUNT(*) AS n FROM weekly_rollups")[0]["n"]
        print(f"weekly_rollups rows: {int(total)}\n")

        # 1. non-Monday keys — the only mechanical fix
        bad_keys = audit_non_monday_keys(store)
        print(f"[1] non-Monday week keys: {len(bad_keys)}")
        for r in bad_keys:
            clash = q(store,
                      "SELECT 1 FROM weekly_rollups WHERE project = ? "
                      "AND week_start = ?",
                      [r["project"], r["correct_key"]])
            if clash:
                print(f"    id={r['id']} {r['project']} {r['week_start']} → "
                      f"{r['correct_key']} COLLIDES with an existing rollup — "
                      f"not touched, human call")
                exit_code = 1
            elif apply:
                execute(store,
                        "UPDATE weekly_rollups SET week_start = ? WHERE id = ?",
                        [r["correct_key"], r["id"]])
                print(f"    id={r['id']} {r['project']} {r['week_start']} → "
                      f"{r['correct_key']} FIXED")
            else:
                print(f"    id={r['id']} {r['project']} {r['week_start']} → "
                      f"{r['correct_key']} (would fix)")

        # 2. Mondays folded into the prior week's rollup
        folded = audit_folded_mondays(store)
        print(f"\n[2] rollups with a summary outside their Mon-Sun window "
              f"(report only): {len(folded)}")
        for r in folded:
            dup = ("also in its own week's rollup — double-counted"
                   if int(r["also_in_correct_rollup"] or 0)
                   else "absent from its own week's rollup")
            print(f"    rollup id={r['rollup_id']} {r['project']} week "
                  f"{r['week_start']}: folds ds id={r['ds_id']} ({r['date']}, "
                  f"belongs to {r['correct_week']}) — {dup}")

        # 3. completed weeks with summaries but no rollup
        missing = audit_missing_weeks(store, monday)
        print(f"\n[3] completed weeks with summaries but no rollup "
              f"(report only — the fixed check will generate them): "
              f"{len(missing)}")
        for r in missing:
            tag = (" [Monday-only — the bug's signature]"
                   if int(r["days"]) == 1 and int(r["mondays"] or 0) == 1
                   else "")
            print(f"    {r['project']} week {r['week_start']} "
                  f"({int(r['days'])} day(s)){tag}")

        # 4. frozen partial weeks: in-week summaries no rollup references
        partial = audit_frozen_partials(store)
        n_days = sum(len(str(r["missing_dates"]).split(",")) for r in partial)
        print(f"\n[4] weeks whose rollup is missing summaries from its own "
              f"Mon-Sun window (report only): {len(partial)} project-weeks, "
              f"{n_days} summaries")
        for r in partial:
            print(f"    {r['project']} week {r['week_start']} "
                  f"(rollup id {r['rollup_ids']}): missing "
                  f"{r['missing_dates']}")
        if partial:
            ids = sorted({int(i) for r in partial
                          for i in str(r["rollup_ids"]).split(",")})
            id_list = ", ".join(map(str, ids))
            # Archive before delete (nightly-pipeline-plan step 5): this
            # narrative cost an API call, so the doomed rows are copied into
            # weekly_rollups_superseded (sqlite-local only) before the
            # DELETE a human runs by hand.
            print(f"    repair = archive + delete + let the fixed pipeline "
                  f"regenerate (human call):\n"
                  f"    INSERT INTO weekly_rollups_superseded\n"
                  f"      (project, week_start, narrative, highlights, model, "
                  f"prompt_version, original_created_at)\n"
                  f"    SELECT project, week_start, narrative, highlights, "
                  f"model, prompt_version, created_at\n"
                  f"      FROM weekly_rollups WHERE id IN ({id_list});\n"
                  f"    DELETE FROM weekly_rollups WHERE id IN ({id_list});")

        if not apply:
            print("\ndry run — nothing written. --apply fixes section 1 only.")
        print(json.dumps({
            "non_monday_keys": len(bad_keys),
            "folded_mondays": len(folded),
            "missing_weeks": len(missing),
            "frozen_partial_weeks": len(partial),
        }))
        return exit_code
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
