"""SQLite backend for Ground Control knowledge store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .base import KnowledgeStore

DEFAULT_DB_PATH = Path.home() / ".claude" / "prompt-history.db"


class SqliteKnowledgeStore(KnowledgeStore):

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def migrate(self) -> None:
        self._conn.executescript("""
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
            );

            CREATE TABLE IF NOT EXISTS intentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                intention TEXT NOT NULL,
                evidence TEXT,
                status TEXT DEFAULT 'active'
                    CHECK(status IN ('active','completed','stalled','abandoned')),
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS themes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme TEXT NOT NULL,
                projects TEXT,
                intention_ids TEXT,
                status TEXT DEFAULT 'active'
                    CHECK(status IN ('active','completed','stalled','abandoned')),
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                model TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

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
            );

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
            );

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
            );

            CREATE TABLE IF NOT EXISTS project_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(project, snapshot_date)
            );

            CREATE INDEX IF NOT EXISTS idx_daily_summaries_project_date
                ON daily_summaries(project, date);
            CREATE INDEX IF NOT EXISTS idx_intentions_project
                ON intentions(project);
            CREATE INDEX IF NOT EXISTS idx_intentions_status
                ON intentions(status);
            CREATE INDEX IF NOT EXISTS idx_themes_status
                ON themes(status);
            CREATE INDEX IF NOT EXISTS idx_weekly_rollups_project_week
                ON weekly_rollups(project, week_start);
            CREATE INDEX IF NOT EXISTS idx_review_snapshots_type_date
                ON review_snapshots(review_type, date);
        """)
        self._conn.commit()

    # ---- Daily summaries ----

    def get_daily_summaries(self, *, project=None, since=None, until=None,
                            limit=None):
        clauses, params = ["1=1"], []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if since:
            clauses.append("date >= ?")
            params.append(since)
        if until:
            clauses.append("date <= ?")
            params.append(until)
        sql = f"SELECT * FROM daily_summaries WHERE {' AND '.join(clauses)} ORDER BY date DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def upsert_daily_summary(self, *, project, date, summary, key_decisions,
                             prompt_count, session_count, commit_count, model):
        self._conn.execute("""
            INSERT OR REPLACE INTO daily_summaries
                (project, date, summary, key_decisions, prompt_count,
                 session_count, commit_count, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, date, summary, json.dumps(key_decisions),
              prompt_count, session_count, commit_count, model))
        self._conn.commit()

    # ---- Weekly rollups ----

    def get_weekly_rollups(self, *, project=None, since=None, limit=None):
        clauses, params = ["1=1"], []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if since:
            clauses.append("week_start >= ?")
            params.append(since)
        sql = f"SELECT * FROM weekly_rollups WHERE {' AND '.join(clauses)} ORDER BY week_start DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def upsert_weekly_rollup(self, *, project, week_start, narrative,
                              highlights, daily_summary_ids,
                              prompt_count, session_count, commit_count, model):
        self._conn.execute("""
            INSERT OR REPLACE INTO weekly_rollups
                (project, week_start, narrative, highlights, daily_summary_ids,
                 prompt_count, session_count, commit_count, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, week_start, narrative, json.dumps(highlights),
              json.dumps(daily_summary_ids), prompt_count, session_count,
              commit_count, model))
        self._conn.commit()

    # ---- Intentions ----

    def get_intentions(self, *, project=None, status="active"):
        clauses, params = ["1=1"], []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)
        sql = f"SELECT * FROM intentions WHERE {' AND '.join(clauses)} ORDER BY last_seen DESC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def upsert_intention(self, *, id, project, intention,
                         evidence_summary_ids, status, model):
        today = datetime.now().strftime("%Y-%m-%d")
        if id is not None:
            self._conn.execute("""
                UPDATE intentions SET status = ?, last_seen = ?,
                       evidence = (SELECT json_group_array(value) FROM (
                           SELECT value FROM json_each(evidence)
                           UNION SELECT ? as value
                       ))
                WHERE id = ?
            """, (status, today, json.dumps(evidence_summary_ids), id))
        else:
            self._conn.execute("""
                INSERT INTO intentions
                    (project, intention, evidence, status, first_seen, last_seen, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project, intention, json.dumps(evidence_summary_ids),
                  status, today, today, model))
        self._conn.commit()

    def get_projects_with_recent_summaries(self, n_days=14):
        cutoff = (datetime.now() - timedelta(days=n_days)).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT DISTINCT project FROM daily_summaries WHERE date >= ?",
            (cutoff,)
        ).fetchall()
        return [r["project"] for r in rows]

    def get_weeks_without_rollups(self):
        """Find (project, week_start) pairs with daily summaries for a
        completed week (Mon-Sun, all 7 days past) but no rollup yet."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._conn.execute("""
            SELECT ds.project,
                   date(ds.date, 'weekday 1', '-7 days') as week_start
            FROM daily_summaries ds
            WHERE ds.date < ?
            GROUP BY ds.project, week_start
            HAVING COUNT(DISTINCT ds.date) >= 1
            EXCEPT
            SELECT project, week_start FROM weekly_rollups
        """, (today,)).fetchall()
        return [(r["project"], r["week_start"]) for r in rows]

    def get_daily_summaries_for_week(self, project, week_start):
        """Get daily summaries for a specific project-week (7-day window from week_start)."""
        week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
        return self.get_daily_summaries(project=project, since=week_start, until=week_end)

    # ---- Review snapshots ----

    def get_review_snapshots(self, *, review_type=None, limit=10):
        clauses, params = ["1=1"], []
        if review_type:
            clauses.append("review_type = ?")
            params.append(review_type)
        sql = f"SELECT * FROM review_snapshots WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def save_review_snapshot(self, *, review_type, date, subject,
                              content_html=None, content_text=None,
                              content_markdown=None, model,
                              input_tokens, output_tokens):
        self._conn.execute("""
            INSERT INTO review_snapshots
                (review_type, date, subject, content_html, content_text,
                 content_markdown, model, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (review_type, date, subject, content_html, content_text,
              content_markdown, model, input_tokens, output_tokens))
        self._conn.commit()

    # ---- Project snapshots ----

    def get_project_snapshot(self, project, *, date=None):
        if date:
            row = self._conn.execute(
                "SELECT * FROM project_snapshots WHERE project = ? AND snapshot_date = ?",
                (project, date)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM project_snapshots WHERE project = ? ORDER BY snapshot_date DESC LIMIT 1",
                (project,)
            ).fetchone()
        if row:
            result = dict(row)
            result["data"] = json.loads(result["data"])
            return result
        return None

    def save_project_snapshot(self, *, project, date, data):
        self._conn.execute("""
            INSERT OR REPLACE INTO project_snapshots (project, snapshot_date, data)
            VALUES (?, ?, ?)
        """, (project, date, json.dumps(data)))
        self._conn.commit()

    # ---- Synthesis log ----

    def log_synthesis(self, *, run_type, target_date=None, project=None,
                      model, input_tokens, output_tokens, cost_cents,
                      duration_ms, status, error_message=None):
        self._conn.execute("""
            INSERT INTO synthesis_log
                (run_type, target_date, project, model, input_tokens,
                 output_tokens, cost_cents, duration_ms, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_type, target_date, project, model, input_tokens,
              output_tokens, cost_cents, duration_ms, status, error_message))
        self._conn.commit()

    def get_synthesis_status(self):
        row = self._conn.execute("""
            SELECT created_at, status, error_message
            FROM synthesis_log ORDER BY created_at DESC LIMIT 1
        """).fetchone()
        if row:
            return {
                "last_run": row["created_at"],
                "status": row["status"],
                "error_message": row["error_message"],
            }
        return None

    def get_recent_synthesis_logs(self):
        """Logs from the last 5 minutes (for run summary display)."""
        return [dict(r) for r in self._conn.execute("""
            SELECT run_type, SUM(cost_cents) as total_cost, COUNT(*) as calls,
                   SUM(input_tokens) as total_in, SUM(output_tokens) as total_out
            FROM synthesis_log
            WHERE created_at > datetime('now', '-5 minutes')
            GROUP BY run_type
        """).fetchall()]

    # ---- Pipeline input (raw data) ----

    def get_unsummarized_days(self, target_date=None):
        date_filter, params = "", []
        if target_date:
            date_filter = "AND date(p.timestamp) = ?"
            params.append(target_date)
        rows = self._conn.execute(f"""
            SELECT p.project, date(p.timestamp) as day
            FROM prompts p
            WHERE p.project IS NOT NULL {date_filter}
            GROUP BY p.project, day
            HAVING COUNT(*) > 0
            EXCEPT
            SELECT ds.project, ds.date FROM daily_summaries ds
        """, params).fetchall()
        return [(r["project"], r["day"]) for r in rows]

    def get_day_data(self, project, date):
        prompts = [dict(r) for r in self._conn.execute("""
            SELECT id, prompt, outcome, utility, tags, context, hostname
            FROM prompts WHERE project = ? AND date(timestamp) = ?
            ORDER BY timestamp
        """, (project, date)).fetchall()]

        sessions = [dict(r) for r in self._conn.execute("""
            SELECT id, started_at, ended_at, summary, utility, hostname
            FROM sessions WHERE project = ? AND date(started_at) = ?
            ORDER BY started_at
        """, (project, date)).fetchall()]

        commits_from_prompts = self._conn.execute("""
            SELECT c.hash, c.message, c.timestamp
            FROM commits c JOIN prompts p ON c.prompt_id = p.id
            WHERE p.project = ? AND date(c.timestamp) = ?
            ORDER BY c.timestamp
        """, (project, date)).fetchall()

        commits_from_sessions = self._conn.execute("""
            SELECT c.hash, c.message, c.timestamp
            FROM commits c JOIN sessions s ON c.session_id = s.id
            WHERE s.project = ? AND date(c.timestamp) = ?
            ORDER BY c.timestamp
        """, (project, date)).fetchall()

        seen_hashes = set()
        all_commits = []
        for c in list(commits_from_prompts) + list(commits_from_sessions):
            if c["hash"] not in seen_hashes:
                seen_hashes.add(c["hash"])
                all_commits.append(dict(c))

        return {"prompts": prompts, "sessions": sessions, "commits": all_commits}

    def get_raw_sessions(self, *, project=None, since_days=None):
        clauses = ["summary IS NOT NULL"]
        params = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        if since_days is not None:
            clauses.append("started_at >= datetime('now', printf('-%d days', ?))")
            params.append(since_days)
        sql = f"""
            SELECT project, date(started_at) as date, summary, started_at, hostname
            FROM sessions WHERE {' AND '.join(clauses)}
            ORDER BY started_at DESC
        """
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def get_period_stats(self, days):
        row = self._conn.execute("""
            SELECT COUNT(*) as prompts, COUNT(DISTINCT project) as projects
            FROM prompts
            WHERE timestamp >= datetime('now', printf('-%d days', ?))
        """, (days,)).fetchone()

        sessions_row = self._conn.execute("""
            SELECT COUNT(*) as sessions FROM sessions
            WHERE started_at >= datetime('now', printf('-%d days', ?))
        """, (days,)).fetchone()

        project_rows = self._conn.execute("""
            SELECT project, COUNT(*) as prompts,
                   COUNT(DISTINCT date(timestamp)) as active_days
            FROM prompts
            WHERE timestamp >= datetime('now', printf('-%d days', ?))
            GROUP BY project ORDER BY prompts DESC
        """, (days,)).fetchall()

        return {
            "total_prompts": row["prompts"],
            "total_projects": row["projects"],
            "total_sessions": sessions_row["sessions"],
            "projects": [
                {"name": r["project"], "prompts": r["prompts"],
                 "active_days": r["active_days"]}
                for r in project_rows
            ],
        }

    # ---- Dashboard reads ----

    def get_sessions_with_commits(self, *, project=None):
        clauses = ["ended_at IS NOT NULL", "summary IS NOT NULL", "summary != ''"]
        params = []
        if project:
            clauses.append("project = ?")
            params.append(project)
        sql = f"SELECT * FROM sessions WHERE {' AND '.join(clauses)} ORDER BY started_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        sessions = [dict(r) for r in rows]

        if sessions:
            session_ids = [s["id"] for s in sessions]
            placeholders = ",".join("?" * len(session_ids))
            commits = self._conn.execute(
                f"SELECT session_id, hash, message FROM commits "
                f"WHERE session_id IN ({placeholders}) ORDER BY timestamp",
                session_ids
            ).fetchall()
            commits_by_session = {}
            for c in commits:
                commits_by_session.setdefault(c["session_id"], []).append(
                    {"hash": c["hash"], "message": c["message"]}
                )
            for s in sessions:
                s["commits"] = commits_by_session.get(s["id"], [])

        return sessions

    def get_all_project_names(self):
        rows = self._conn.execute("""
            SELECT DISTINCT project FROM (
                SELECT DISTINCT project FROM prompts
                UNION SELECT DISTINCT project FROM sessions WHERE project IS NOT NULL
                UNION SELECT DISTINCT project FROM intentions WHERE project IS NOT NULL
            ) ORDER BY project
        """).fetchall()
        return {r["project"] for r in rows}

    def get_non_active_projects(self):
        rows = self._conn.execute(
            "SELECT name FROM projects WHERE status != 'active'"
        ).fetchall()
        return {r["name"] for r in rows}

    def get_project_detail(self, name):
        self.ensure_project(name)

        project_row = self._conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()

        session_count = self._conn.execute("""
            SELECT COUNT(*) as n FROM sessions
            WHERE project = ? AND ended_at IS NOT NULL
                  AND summary IS NOT NULL AND summary != ''
        """, (name,)).fetchone()["n"]

        last_session_row = self._conn.execute("""
            SELECT id, summary, started_at FROM sessions
            WHERE project = ? AND ended_at IS NOT NULL
                  AND summary IS NOT NULL AND summary != ''
            ORDER BY started_at DESC LIMIT 1
        """, (name,)).fetchone()

        intention_rows = self._conn.execute("""
            SELECT intention FROM intentions
            WHERE project = ? AND status = 'active'
            ORDER BY last_seen DESC LIMIT 3
        """, (name,)).fetchall()

        return {
            "name": name,
            "status": project_row["status"] if project_row else "active",
            "category": project_row["category"] if project_row else None,
            "notes": project_row["notes"] if project_row else None,
            "created_at": project_row["created_at"] if project_row else None,
            "session_count": session_count,
            "last_session": dict(last_session_row) if last_session_row else None,
            "intentions": [r["intention"] for r in intention_rows],
        }

    def get_overview(self):
        week_prompts = self._conn.execute(
            "SELECT COUNT(*) as n FROM prompts WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]
        week_sessions = self._conn.execute(
            "SELECT COUNT(*) as n FROM sessions WHERE started_at >= datetime('now', '-7 days') "
            "AND ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''"
        ).fetchone()["n"]
        week_commits = self._conn.execute(
            "SELECT COUNT(*) as n FROM commits WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()["n"]

        session_data = {}
        for row in self._conn.execute("""
            SELECT project, COUNT(*) as session_count,
                   MAX(started_at) as last_started,
                   AVG(token_count) as avg_tokens,
                   MAX(token_count) as peak_tokens
            FROM sessions
            WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
            GROUP BY project
        """).fetchall():
            session_data[row["project"]] = {
                "session_count": row["session_count"],
                "last_started": row["last_started"],
                "avg_tokens": row["avg_tokens"],
                "peak_tokens": row["peak_tokens"],
            }

        last_sessions = {}
        for row in self._conn.execute("""
            SELECT s.project, s.summary, s.started_at
            FROM sessions s
            INNER JOIN (
                SELECT project, MAX(started_at) as max_start FROM sessions
                WHERE ended_at IS NOT NULL AND summary IS NOT NULL AND summary != ''
                GROUP BY project
            ) latest ON s.project = latest.project AND s.started_at = latest.max_start
            WHERE s.ended_at IS NOT NULL AND s.summary IS NOT NULL AND s.summary != ''
        """).fetchall():
            last_sessions[row["project"]] = {
                "summary": row["summary"],
                "started_at": row["started_at"],
            }

        intentions_by_project = {}
        for row in self._conn.execute(
            "SELECT project, intention FROM intentions WHERE status = 'active' ORDER BY last_seen DESC"
        ).fetchall():
            intentions_by_project.setdefault(row["project"], []).append(row["intention"])

        intention_last_seen = {}
        for row in self._conn.execute(
            "SELECT project, MAX(last_seen) as last_seen FROM intentions WHERE status = 'active' GROUP BY project"
        ).fetchall():
            intention_last_seen[row["project"]] = row["last_seen"]

        project_statuses = self._get_project_statuses_map()

        return {
            "week": {"sessions": week_sessions, "prompts": week_prompts, "commits": week_commits},
            "session_data": session_data,
            "last_sessions": last_sessions,
            "intentions_by_project": intentions_by_project,
            "intention_last_seen": intention_last_seen,
            "project_statuses": project_statuses,
        }

    def get_prompts(self, *, project=None):
        clauses, params = ["1=1"], []
        if project:
            clauses.append("project = ?")
            params.append(project)
        sql = f"SELECT * FROM prompts WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ---- Dashboard mutations ----

    def ensure_project(self, name):
        self._conn.execute(
            "INSERT OR IGNORE INTO projects (name) VALUES (?)", (name,)
        )
        self._conn.commit()

    def update_project(self, name, **fields):
        allowed = {"status", "category", "notes"}
        updates, params = [], []
        for field in allowed:
            if field in fields:
                updates.append(f"{field} = ?")
                params.append(fields[field])
        if updates:
            self.ensure_project(name)
            params.append(name)
            self._conn.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE name = ?", params
            )
            self._conn.commit()

    def update_prompt(self, prompt_id, **fields):
        allowed = {"tags", "notes"}
        updates, params = [], []
        for field in allowed:
            if field in fields:
                updates.append(f"{field} = ?")
                params.append(fields[field] if fields[field] != "" else None)
        if updates:
            params.append(prompt_id)
            self._conn.execute(
                f"UPDATE prompts SET {', '.join(updates)} WHERE id = ?", params
            )
            self._conn.commit()

    def update_session(self, session_id, **fields):
        allowed = {"summary"}
        updates, params = [], []
        for field in allowed:
            if field in fields:
                updates.append(f"{field} = ?")
                params.append(fields[field] if fields[field] != "" else None)
        if updates:
            params.append(session_id)
            self._conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params
            )
            self._conn.commit()

    # ---- Internal helpers ----

    def _get_project_statuses_map(self):
        rows = self._conn.execute("SELECT name, status FROM projects").fetchall()
        return {r["name"]: r["status"] for r in rows}
