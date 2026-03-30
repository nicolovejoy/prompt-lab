"""Turso (libSQL over HTTP) backend for Ground Control knowledge store.

Uses Turso's HTTP pipeline API — no extra Python dependencies needed.
Requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN environment variables.

Setup:
  1. Install Turso CLI: curl -sSfL https://get.tur.so/install.sh | bash
  2. turso auth login
  3. turso db create ground-control
  4. turso db show ground-control --url   → TURSO_DATABASE_URL
  5. turso db tokens create ground-control → TURSO_AUTH_TOKEN
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta

from .base import KnowledgeStore


class TursoKnowledgeStore(KnowledgeStore):

    def __init__(self, url: str | None = None, token: str | None = None):
        self._url = url or os.environ["TURSO_DATABASE_URL"]
        self._token = token or os.environ["TURSO_AUTH_TOKEN"]
        # Convert libsql:// to https:// for HTTP API
        if self._url.startswith("libsql://"):
            self._url = "https://" + self._url[len("libsql://"):]
        if not self._url.endswith("/"):
            self._url += "/"

    def _pipeline(self, statements: list[dict]) -> list[dict]:
        """Execute statements via Turso's HTTP pipeline API."""
        requests = [{"type": "execute", "stmt": s} for s in statements]
        requests.append({"type": "close"})

        payload = json.dumps({"requests": requests}).encode()
        req = urllib.request.Request(
            self._url + "v3/pipeline",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        results = []
        for r in data.get("results", []):
            if r["type"] == "ok" and r["response"]["type"] == "execute":
                results.append(r["response"]["result"])
            elif r["type"] == "error":
                raise RuntimeError(f"Turso error: {r['error']}")
        return results

    def _execute(self, sql: str, args: list | None = None) -> dict:
        """Execute a single statement and return the result."""
        stmt = {"sql": sql}
        if args:
            stmt["args"] = [{"type": _turso_type(v), "value": _turso_value(v)} for v in args]
        results = self._pipeline([stmt])
        return results[0] if results else {"cols": [], "rows": []}

    def _execute_many(self, statements: list[tuple[str, list]]) -> list[dict]:
        """Execute multiple statements in a single pipeline."""
        stmts = []
        for sql, args in statements:
            stmt = {"sql": sql}
            if args:
                stmt["args"] = [{"type": _turso_type(v), "value": _turso_value(v)} for v in args]
            stmts.append(stmt)
        return self._pipeline(stmts)

    def _rows_to_dicts(self, result: dict) -> list[dict]:
        """Convert Turso result {cols, rows} to list of dicts."""
        cols = [c["name"] for c in result.get("cols", [])]
        return [
            {col: row[i].get("value") if isinstance(row[i], dict) else row[i]
             for i, col in enumerate(cols)}
            for row in result.get("rows", [])
        ]

    def _row_to_dict(self, result: dict) -> dict | None:
        rows = self._rows_to_dicts(result)
        return rows[0] if rows else None

    def close(self) -> None:
        pass  # HTTP — no persistent connection

    def migrate(self) -> None:
        self._pipeline([
            {"sql": """
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    date TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_decisions TEXT,
                    prompt_count INTEGER DEFAULT 0,
                    session_count INTEGER DEFAULT 0,
                    commit_count INTEGER DEFAULT 0,
                    model TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(project, date)
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS weekly_rollups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    week_start TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    highlights TEXT,
                    daily_summary_ids TEXT,
                    prompt_count INTEGER DEFAULT 0,
                    session_count INTEGER DEFAULT 0,
                    commit_count INTEGER DEFAULT 0,
                    model TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(project, week_start)
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS intentions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    intention TEXT NOT NULL,
                    evidence TEXT,
                    status TEXT DEFAULT 'active',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    model TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS review_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_type TEXT NOT NULL,
                    date TEXT NOT NULL,
                    subject TEXT,
                    content_html TEXT,
                    content_text TEXT,
                    content_markdown TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS project_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    snapshot_date TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(project, snapshot_date)
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS synthesis_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    target_date TEXT,
                    project TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_cents REAL,
                    duration_ms INTEGER,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS project_aliases (
                    alias     TEXT PRIMARY KEY,
                    canonical TEXT NOT NULL
                )
            """},
        ])

    # ---- Daily summaries ----

    def get_daily_summaries(self, *, project=None, since=None, until=None,
                            limit=None):
        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)
        if since:
            clauses.append("date >= ?")
            args.append(since)
        if until:
            clauses.append("date <= ?")
            args.append(until)
        sql = f"SELECT * FROM daily_summaries WHERE {' AND '.join(clauses)} ORDER BY date DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return self._rows_to_dicts(self._execute(sql, args))

    def upsert_daily_summary(self, *, project, date, summary, key_decisions,
                             prompt_count, session_count, commit_count, model):
        self._execute("""
            INSERT OR REPLACE INTO daily_summaries
                (project, date, summary, key_decisions, prompt_count,
                 session_count, commit_count, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [project, date, summary, json.dumps(key_decisions),
              prompt_count, session_count, commit_count, model])

    # ---- Weekly rollups ----

    def get_weekly_rollups(self, *, project=None, since=None, limit=None):
        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)
        if since:
            clauses.append("week_start >= ?")
            args.append(since)
        sql = f"SELECT * FROM weekly_rollups WHERE {' AND '.join(clauses)} ORDER BY week_start DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return self._rows_to_dicts(self._execute(sql, args))

    def upsert_weekly_rollup(self, *, project, week_start, narrative,
                              highlights, daily_summary_ids,
                              prompt_count, session_count, commit_count, model):
        self._execute("""
            INSERT OR REPLACE INTO weekly_rollups
                (project, week_start, narrative, highlights, daily_summary_ids,
                 prompt_count, session_count, commit_count, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [project, week_start, narrative, json.dumps(highlights),
              json.dumps(daily_summary_ids), prompt_count, session_count,
              commit_count, model])

    # ---- Intentions ----

    def get_intentions(self, *, project=None, status="active"):
        clauses, args = ["1=1"], []
        if project:
            clauses.append("project = ?")
            args.append(project)
        if status and status != "all":
            clauses.append("status = ?")
            args.append(status)
        sql = f"SELECT * FROM intentions WHERE {' AND '.join(clauses)} ORDER BY last_seen DESC"
        return self._rows_to_dicts(self._execute(sql, args))

    def upsert_intention(self, *, id, project, intention,
                         evidence_summary_ids, status, model):
        today = datetime.now().strftime("%Y-%m-%d")
        if id is not None:
            self._execute("""
                UPDATE intentions SET status = ?, last_seen = ?,
                       evidence = ? WHERE id = ?
            """, [status, today, json.dumps(evidence_summary_ids), id])
        else:
            self._execute("""
                INSERT INTO intentions
                    (project, intention, evidence, status, first_seen, last_seen, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [project, intention, json.dumps(evidence_summary_ids),
                  status, today, today, model])

    def get_projects_with_recent_summaries(self, n_days=14):
        cutoff = (datetime.now() - timedelta(days=n_days)).strftime("%Y-%m-%d")
        result = self._execute(
            "SELECT DISTINCT project FROM daily_summaries WHERE date >= ?",
            [cutoff]
        )
        return [r["project"] for r in self._rows_to_dicts(result)]

    def get_weeks_without_rollups(self):
        today = datetime.now().strftime("%Y-%m-%d")
        result = self._execute("""
            SELECT ds.project, ds.week_start FROM (
                SELECT project, date(date, 'weekday 1', '-7 days') as week_start
                FROM daily_summaries WHERE date < ?
                GROUP BY project, week_start HAVING COUNT(DISTINCT date) >= 1
            ) ds LEFT JOIN weekly_rollups wr
                ON wr.project = ds.project AND wr.week_start = ds.week_start
            WHERE wr.id IS NULL
        """, [today])
        return [(r["project"], r["week_start"]) for r in self._rows_to_dicts(result)]

    # ---- Review snapshots ----

    def get_review_snapshots(self, *, review_type=None, limit=10):
        clauses, args = ["1=1"], []
        if review_type:
            clauses.append("review_type = ?")
            args.append(review_type)
        sql = f"SELECT * FROM review_snapshots WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return self._rows_to_dicts(self._execute(sql, args))

    def save_review_snapshot(self, *, review_type, date, subject,
                              content_html=None, content_text=None,
                              content_markdown=None, model,
                              input_tokens, output_tokens):
        self._execute("""
            INSERT INTO review_snapshots
                (review_type, date, subject, content_html, content_text,
                 content_markdown, model, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [review_type, date, subject, content_html, content_text,
              content_markdown, model, input_tokens, output_tokens])

    # ---- Project snapshots ----

    def get_project_snapshot(self, project, *, date=None):
        if date:
            result = self._execute(
                "SELECT * FROM project_snapshots WHERE project = ? AND snapshot_date = ?",
                [project, date]
            )
        else:
            result = self._execute(
                "SELECT * FROM project_snapshots WHERE project = ? ORDER BY snapshot_date DESC LIMIT 1",
                [project]
            )
        row = self._row_to_dict(result)
        if row and row.get("data"):
            row["data"] = json.loads(row["data"])
        return row

    def save_project_snapshot(self, *, project, date, data):
        self._execute("""
            INSERT OR REPLACE INTO project_snapshots (project, snapshot_date, data)
            VALUES (?, ?, ?)
        """, [project, date, json.dumps(data)])

    # ---- Synthesis log ----

    def log_synthesis(self, *, run_type, target_date=None, project=None,
                      model, input_tokens, output_tokens, cost_cents,
                      duration_ms, status, error_message=None):
        self._execute("""
            INSERT INTO synthesis_log
                (run_type, target_date, project, model, input_tokens,
                 output_tokens, cost_cents, duration_ms, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [run_type, target_date, project, model, input_tokens,
              output_tokens, cost_cents, duration_ms, status, error_message])

    def get_synthesis_status(self):
        result = self._execute("""
            SELECT created_at, status, error_message
            FROM synthesis_log ORDER BY created_at DESC LIMIT 1
        """)
        return self._row_to_dict(result)

    # ---- Pipeline input (raw data) — not available in Turso ----
    # These methods access raw prompts/sessions which are NOT synced to Turso.
    # They raise NotImplementedError since the pipeline always runs locally.

    def get_unsummarized_days(self, target_date=None):
        raise NotImplementedError("Raw data not available in Turso — run pipeline locally")

    def get_day_data(self, project, date):
        raise NotImplementedError("Raw data not available in Turso — run pipeline locally")

    def get_raw_sessions(self, *, project=None, since_days=None):
        raise NotImplementedError("Raw data not available in Turso — run pipeline locally")

    def get_period_stats(self, days):
        raise NotImplementedError("Raw data not available in Turso — run pipeline locally")

    # ---- Dashboard reads ----

    def get_sessions_with_commits(self, *, project=None):
        raise NotImplementedError("Raw sessions not available in Turso")

    def get_all_project_names(self):
        result = self._execute("""
            SELECT DISTINCT project FROM (
                SELECT DISTINCT project FROM daily_summaries
                UNION SELECT DISTINCT project FROM intentions
                UNION SELECT DISTINCT project FROM weekly_rollups
            ) ORDER BY project
        """)
        return {r["project"] for r in self._rows_to_dicts(result)}

    def get_non_active_projects(self):
        return set()  # No projects table in Turso

    def get_project_detail(self, name):
        summaries = self.get_daily_summaries(project=name, limit=7)
        intentions = self.get_intentions(project=name, status="active")
        snapshot = self.get_project_snapshot(name)

        return {
            "name": name,
            "status": "active",
            "category": None,
            "notes": None,
            "created_at": None,
            "session_count": snapshot["data"].get("session_count_7d", 0) if snapshot else 0,
            "last_session": None,
            "intentions": [i["intention"] for i in intentions[:3]],
            "daily_summaries": summaries,
        }

    def get_overview(self):
        summaries_7d = self.get_daily_summaries(
            since=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        )
        intentions = self.get_intentions(status="active")

        # Aggregate from summaries
        projects_data = {}
        for s in summaries_7d:
            p = s["project"]
            if p not in projects_data:
                projects_data[p] = {"prompts": 0, "sessions": 0, "commits": 0, "days": 0}
            projects_data[p]["prompts"] += s.get("prompt_count", 0) or 0
            projects_data[p]["sessions"] += s.get("session_count", 0) or 0
            projects_data[p]["commits"] += s.get("commit_count", 0) or 0
            projects_data[p]["days"] += 1

        intentions_by_project = {}
        for i in intentions:
            intentions_by_project.setdefault(i["project"], []).append(i["intention"])

        total_prompts = sum(d["prompts"] for d in projects_data.values())
        total_sessions = sum(d["sessions"] for d in projects_data.values())
        total_commits = sum(d["commits"] for d in projects_data.values())

        return {
            "week": {"sessions": total_sessions, "prompts": total_prompts, "commits": total_commits},
            "session_data": {p: {"session_count": d["sessions"], "last_started": None,
                                  "avg_tokens": None, "peak_tokens": None}
                             for p, d in projects_data.items()},
            "last_sessions": {},
            "intentions_by_project": intentions_by_project,
            "intention_last_seen": {},
            "project_statuses": {},
        }

    def get_prompts(self, *, project=None):
        raise NotImplementedError("Raw prompts not available in Turso")

    # ---- Dashboard mutations — not applicable for Turso (read-only) ----

    def ensure_project(self, name):
        pass

    def update_project(self, name, **fields):
        raise NotImplementedError("Turso store is read-only")

    def update_prompt(self, prompt_id, **fields):
        raise NotImplementedError("Turso store is read-only")

    def update_session(self, session_id, **fields):
        raise NotImplementedError("Turso store is read-only")


# ---- Helpers for Turso HTTP API type mapping ----

def _turso_type(value):
    if value is None:
        return "null"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "text"


def _turso_value(value):
    if value is None:
        return None
    return str(value)
