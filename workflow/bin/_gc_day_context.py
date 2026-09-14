#!/usr/bin/env python3
"""Emit bounded, whole-day synthesis input for /handoff.

Counts describe every row returned by the store.  The prose-bearing arrays are
bounded, and their metadata says explicitly when text or rows were omitted.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import sys
from datetime import date as calendar_date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LAB_TZ = ZoneInfo("America/Los_Angeles")
MAX_PROMPTS = 50
MAX_PROMPT_CHARS = 500
MAX_COMMITS = 100
MAX_COMMIT_CHARS = 500
MAX_SESSION_SUMMARY_CHARS = 1_000


def lab_date(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=LAB_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=LAB_TZ)
    return now.astimezone(LAB_TZ).date().isoformat()


def _clip(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def day_bounds(date: str) -> tuple[str, str]:
    day = calendar_date.fromisoformat(date)
    start = datetime.combine(day, datetime.min.time(), LAB_TZ)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), LAB_TZ)
    return tuple(d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                 for d in (start, end))


def _day_data(store, project: str, date: str, session_id: int | None = None) -> dict:
    """Raw context is local only, with explicit Pacific boundaries on any host."""
    start, end = day_bounds(date)
    names = store.expand_project(project)
    ph = ",".join("?" for _ in names)
    conn = store.conn

    def rows(sql, params):
        return [dict(row) for row in conn.execute(sql, params)]

    prompts = rows(f"""
        SELECT id, timestamp, prompt, session_id FROM prompts
        WHERE project IN ({ph}) AND datetime(timestamp) >= ? AND datetime(timestamp) < ?
        ORDER BY datetime(timestamp), id
    """, (*names, start, end))
    commits = rows(f"""
        SELECT c.hash, c.message, c.timestamp,
               COALESCE(c.session_id, (SELECT p.session_id FROM prompts p
                                      WHERE p.id=c.prompt_id)) AS session_id
        FROM commits c
        WHERE datetime(c.timestamp) >= ? AND datetime(c.timestamp) < ?
          AND (EXISTS (SELECT 1 FROM sessions s WHERE s.id=c.session_id
                       AND s.project IN ({ph}))
               OR EXISTS (SELECT 1 FROM prompts p WHERE p.id=c.prompt_id
                          AND p.project IN ({ph})))
        ORDER BY datetime(c.timestamp), c.id
    """, (start, end, *names, *names))
    # Sessions that began before midnight still contribute when they record work
    # or close today. Do not count every ancient, never-closed row as active.
    active_ids = {r["session_id"] for r in prompts + commits if r["session_id"] is not None}
    # Codex has no prompt hook: a caller continuing past midnight can have no
    # recorded activity today yet. Its validated identity is direct evidence.
    if session_id is not None:
        active_ids.add(session_id)
    sessions = rows(f"""
        SELECT id, datetime(started_at) AS started_at,
               datetime(ended_at) AS ended_at, summary FROM sessions
        WHERE project IN ({ph}) ORDER BY started_at, id
    """, names)
    if session_id is not None and not any(s["id"] == session_id for s in sessions):
        raise ValueError("Session does not belong to this project")
    sessions = [s for s in sessions if s["id"] in active_ids or any(
        stamp and start <= stamp < end for stamp in (s["started_at"], s["ended_at"])
    )]
    unique_commits = {}
    for row in commits:
        unique_commits.setdefault(row["hash"], row)
    existing = rows(f"""
        SELECT project, date, summary, key_decisions, prompt_count, session_count, commit_count
        FROM daily_summaries WHERE project IN ({ph}) AND date=? ORDER BY project
    """, (*names, date))
    return {"prompts": prompts, "sessions": sessions,
            "commits": list(unique_commits.values()), "existing_daily": existing}


def build_context(store, project: str, date: str, session_id: int | None = None) -> dict:
    # A single read snapshot prevents counts and prose from observing different
    # concurrent commits. save_summary already holds a write transaction.
    owns_transaction = not store.conn.in_transaction
    if owns_transaction:
        store.conn.execute("BEGIN")
    try:
        data = _day_data(store, project, date, session_id)
    finally:
        if owns_transaction:
            store.conn.rollback()
    revision = hashlib.sha256(json.dumps(
        {"project": project, "date": date, "data": data}, sort_keys=True
    ).encode()).hexdigest()
    raw_prompts = data.get("prompts", [])
    raw_sessions = data.get("sessions", [])
    raw_commits = data.get("commits", [])

    # Keep every available session summary: these are the highest-signal record
    # of work in parallel agent sessions. Bound each value, never their count.
    sessions = []
    clipped_sessions = 0
    for row in raw_sessions:
        summary = row.get("summary") or ""
        summary, clipped = _clip(summary, MAX_SESSION_SUMMARY_CHARS)
        clipped_sessions += int(clipped)
        sessions.append({"id": row.get("id"), "summary": summary})

    prompts = []
    clipped_prompts = 0
    for row in raw_prompts[-MAX_PROMPTS:]:
        prompt, clipped = _clip(row.get("prompt") or "", MAX_PROMPT_CHARS)
        clipped_prompts += int(clipped)
        prompts.append(prompt)

    commits = []
    clipped_commits = 0
    for row in raw_commits[-MAX_COMMITS:]:
        message, clipped = _clip(row.get("message") or "", MAX_COMMIT_CHARS)
        clipped_commits += int(clipped)
        commits.append({"hash": (row.get("hash") or "")[:8], "message": message})

    return {
        "project": project,
        "date": date,
        "context_revision": revision,
        "synthesis_session_id": session_id,
        "existing_daily": data["existing_daily"],
        "counts": {
            "prompts": len(raw_prompts),
            "sessions": len(raw_sessions),
            "commits": len(raw_commits),
        },
        "sessions": sessions,
        "prompts": prompts,
        "commits": commits,
        "truncation": {
            "prompts_omitted": max(0, len(raw_prompts) - len(prompts)),
            "prompts_clipped": clipped_prompts,
            "session_summaries_omitted": 0,
            "session_summaries_clipped": clipped_sessions,
            "commits_omitted": max(0, len(raw_commits) - len(commits)),
            "commits_clipped": clipped_commits,
        },
    }


class StaleContextError(ValueError):
    pass


def save_summary(store, project: str, payload: dict) -> None:
    """Reject stale synthesis before replacing prose; serialize the check/write."""
    if payload.get("project") != project:
        raise ValueError("Daily summary project does not match the current repository")
    store.conn.execute("BEGIN IMMEDIATE")
    try:
        current = build_context(store, project, payload["date"], payload.get("synthesis_session_id"))
        if payload.get("context_revision") != current["context_revision"]:
            raise StaleContextError("Day context changed; fetch today-context and synthesize again")
        for field, count in (("prompt_count", "prompts"), ("session_count", "sessions"),
                             ("commit_count", "commits")):
            if payload.get(field) != current["counts"][count]:
                raise ValueError(f"{field} must equal the context count")
        fields = {k: v for k, v in payload.items()
                  if k not in {"context_revision", "synthesis_session_id"}}
        store.upsert_daily_summary(**fields)
    except Exception:
        store.conn.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--date", default=None)
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument("--session-id", type=int, default=None)
    args = parser.parse_args()

    prompt_lab_dir = Path(os.environ.get("PROMPT_LAB_DIR", "~/src/prompt-lab")).expanduser()
    sys.path.insert(0, str(prompt_lab_dir))
    from store import get_store

    # Raw tables exist only in SQLite, even when the caller selects Turso globally.
    store = get_store("sqlite")
    try:
        if args.save:
            with args.save.open() as source:
                payload = json.load(source)
            save_summary(store, args.project, payload)
            print("Daily summary saved for", args.project, payload["date"])
        else:
            print(json.dumps(build_context(store, args.project, args.date or lab_date(), args.session_id)))
    except (ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
