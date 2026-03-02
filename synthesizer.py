#!/usr/bin/env python3
"""Synthesizer — generates daily summaries and intentions from prompt-history.db."""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from anthropic import Anthropic, RateLimitError
from dotenv import load_dotenv

DB_PATH = Path.home() / ".claude" / "prompt-history.db"
ENV_PATH = Path.home() / ".claude" / "synthesizer.env"

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def migrate(db: sqlite3.Connection):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            date TEXT NOT NULL,
            summary TEXT NOT NULL,
            key_decisions TEXT,  -- JSON array
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
            evidence TEXT,  -- JSON array of daily_summary IDs
            status TEXT DEFAULT 'active' CHECK(status IN ('active','completed','stalled','abandoned')),
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            model TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS themes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            projects TEXT,  -- JSON array
            intention_ids TEXT,  -- JSON array
            status TEXT DEFAULT 'active' CHECK(status IN ('active','completed','stalled','abandoned')),
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

        CREATE INDEX IF NOT EXISTS idx_daily_summaries_project_date ON daily_summaries(project, date);
        CREATE INDEX IF NOT EXISTS idx_intentions_project ON intentions(project);
        CREATE INDEX IF NOT EXISTS idx_intentions_status ON intentions(status);
        CREATE INDEX IF NOT EXISTS idx_themes_status ON themes(status);
    """)
    db.commit()


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def get_unsummarized_days(db: sqlite3.Connection, target_date: str | None = None):
    """Find (project, date) pairs with prompts but no daily_summary row."""
    date_filter = ""
    params = []
    if target_date:
        date_filter = "AND date(p.timestamp) = ?"
        params.append(target_date)

    rows = db.execute(f"""
        SELECT p.project, date(p.timestamp) as day
        FROM prompts p
        WHERE p.project IS NOT NULL
          {date_filter}
        GROUP BY p.project, day
        HAVING COUNT(*) > 0
        EXCEPT
        SELECT ds.project, ds.date FROM daily_summaries ds
    """, params).fetchall()
    return [(r["project"], r["day"]) for r in rows]


def get_day_data(db: sqlite3.Connection, project: str, date: str) -> dict:
    """Fetch all prompts, sessions, commits for a project+date."""
    prompts = db.execute("""
        SELECT id, prompt, outcome, utility, tags, context
        FROM prompts
        WHERE project = ? AND date(timestamp) = ?
        ORDER BY timestamp
    """, (project, date)).fetchall()

    sessions = db.execute("""
        SELECT id, started_at, ended_at, summary, utility
        FROM sessions
        WHERE project = ? AND date(started_at) = ?
        ORDER BY started_at
    """, (project, date)).fetchall()

    commits = db.execute("""
        SELECT c.hash, c.message, c.timestamp
        FROM commits c
        JOIN prompts p ON c.prompt_id = p.id
        WHERE p.project = ? AND date(c.timestamp) = ?
        ORDER BY c.timestamp
    """, (project, date)).fetchall()

    # Also get commits linked via session
    session_commits = db.execute("""
        SELECT c.hash, c.message, c.timestamp
        FROM commits c
        JOIN sessions s ON c.session_id = s.id
        WHERE s.project = ? AND date(c.timestamp) = ?
        ORDER BY c.timestamp
    """, (project, date)).fetchall()

    # Dedupe commits by hash
    seen_hashes = set()
    all_commits = []
    for c in list(commits) + list(session_commits):
        if c["hash"] not in seen_hashes:
            seen_hashes.add(c["hash"])
            all_commits.append(c)

    return {
        "prompts": [dict(p) for p in prompts],
        "sessions": [dict(s) for s in sessions],
        "commits": [dict(c) for c in all_commits],
    }


def get_recent_summaries(db: sqlite3.Connection, project: str, n_days: int = 14):
    return db.execute("""
        SELECT id, project, date, summary, key_decisions
        FROM daily_summaries
        WHERE project = ?
        ORDER BY date DESC
        LIMIT ?
    """, (project, n_days)).fetchall()


def get_all_active_intentions(db: sqlite3.Connection):
    return db.execute("""
        SELECT id, project, intention, evidence, status, first_seen, last_seen
        FROM intentions
        WHERE status = 'active'
        ORDER BY project, last_seen DESC
    """).fetchall()


def get_projects_with_recent_summaries(db: sqlite3.Connection, n_days: int = 14):
    cutoff = (datetime.now() - timedelta(days=n_days)).strftime("%Y-%m-%d")
    rows = db.execute("""
        SELECT DISTINCT project FROM daily_summaries WHERE date >= ?
    """, (cutoff,)).fetchall()
    return [r["project"] for r in rows]


# ---------------------------------------------------------------------------
# Claude API calls with retry
# ---------------------------------------------------------------------------

def call_claude(client: Anthropic, model: str, system: str, user_msg: str, max_retries: int = 3) -> dict:
    """Call Claude API with exponential backoff. Returns parsed JSON response + usage."""
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            resp = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            duration_ms = int((time.time() - t0) * 1000)
            text = resp.content[0].text

            # Try to parse as JSON (strip markdown fences if present)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parsed = json.loads(text)
            return {
                "parsed": parsed,
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "duration_ms": duration_ms,
                "model": model,
            }
        except RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
        except json.JSONDecodeError as e:
            # Return raw text if JSON parsing fails
            return {
                "parsed": {"summary": text, "key_decisions": []},
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "duration_ms": duration_ms,
                "model": model,
                "json_error": str(e),
            }


def estimate_cost_cents(model: str, input_tokens: int, output_tokens: int) -> float:
    # Pricing per million tokens (as of 2025)
    prices = {
        HAIKU: {"input": 100, "output": 500},       # $1/$5 per MTok
        SONNET: {"input": 300, "output": 1500},      # $3/$15 per MTok
    }
    p = prices.get(model, prices[HAIKU])
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def log_synthesis(db: sqlite3.Connection, run_type: str, target_date: str | None,
                  project: str | None, model: str, input_tokens: int, output_tokens: int,
                  cost_cents: float, duration_ms: int, status: str, error_message: str | None = None):
    db.execute("""
        INSERT INTO synthesis_log (run_type, target_date, project, model, input_tokens,
                                   output_tokens, cost_cents, duration_ms, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_type, target_date, project, model, input_tokens, output_tokens,
          cost_cents, duration_ms, status, error_message))
    db.commit()


# ---------------------------------------------------------------------------
# Synthesis functions
# ---------------------------------------------------------------------------

def synthesize_daily_summaries(db: sqlite3.Connection, client: Anthropic, target_date: str | None = None):
    """Generate daily summaries for all unsummarized (project, date) pairs."""
    pairs = get_unsummarized_days(db, target_date)
    if not pairs:
        print("No unsummarized days found.")
        return

    print(f"Found {len(pairs)} unsummarized day(s).")

    for project, date in pairs:
        print(f"  Summarizing {project} / {date}...", end=" ", flush=True)
        data = get_day_data(db, project, date)

        # Build prompt
        prompt_texts = [f"- {p['prompt']}" for p in data["prompts"] if p.get("prompt")]
        commit_texts = [f"- {c['hash'][:8]}: {c['message']}" for c in data["commits"] if c.get("message")]
        session_texts = [f"- {s.get('summary', '(no summary)')}" for s in data["sessions"]]

        user_msg = f"""Project: {project}
Date: {date}

Prompts ({len(data['prompts'])}):
{chr(10).join(prompt_texts) or '(none)'}

Commits ({len(data['commits'])}):
{chr(10).join(commit_texts) or '(none)'}

Sessions ({len(data['sessions'])}):
{chr(10).join(session_texts) or '(none)'}"""

        system = """You summarize a developer's daily work on a project.
Return JSON: {"summary": "2-4 sentence summary of what was accomplished", "key_decisions": ["decision 1", "decision 2"]}
Focus on WHAT was done and WHY, not low-level details. Be concise."""

        try:
            result = call_claude(client, HAIKU, system, user_msg)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"], result["output_tokens"])

            db.execute("""
                INSERT OR REPLACE INTO daily_summaries
                    (project, date, summary, key_decisions, prompt_count, session_count, commit_count, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project, date,
                parsed.get("summary", ""),
                json.dumps(parsed.get("key_decisions", [])),
                len(data["prompts"]),
                len(data["sessions"]),
                len(data["commits"]),
                result["model"],
            ))
            db.commit()

            log_synthesis(db, "daily", date, project, result["model"],
                          result["input_tokens"], result["output_tokens"],
                          cost, result["duration_ms"], "success")

            print(f"OK ({result['input_tokens']}+{result['output_tokens']} tokens, ${cost/100:.4f})")

        except Exception as e:
            log_synthesis(db, "daily", date, project, HAIKU, 0, 0, 0, 0, "error", str(e))
            print(f"ERROR: {e}")


def synthesize_intentions(db: sqlite3.Connection, client: Anthropic):
    """Update/create/close intentions for each project with recent summaries."""
    projects = get_projects_with_recent_summaries(db)
    if not projects:
        print("No projects with recent summaries.")
        return

    print(f"Updating intentions for {len(projects)} project(s).")

    for project in projects:
        print(f"  Intentions for {project}...", end=" ", flush=True)

        summaries = get_recent_summaries(db, project, 14)
        summary_texts = []
        summary_ids = []
        for s in summaries:
            summary_texts.append(f"[{s['date']}] {s['summary']}")
            summary_ids.append(s["id"])

        current_intentions = db.execute("""
            SELECT id, intention, status, first_seen, last_seen
            FROM intentions WHERE project = ? AND status = 'active'
        """, (project,)).fetchall()

        current_text = ""
        if current_intentions:
            current_text = "\n\nCurrent active intentions:\n" + "\n".join(
                f"- [ID {i['id']}] {i['intention']} (since {i['first_seen']})"
                for i in current_intentions
            )

        user_msg = f"""Project: {project}

Recent daily summaries (last 14 days):
{chr(10).join(summary_texts)}
{current_text}"""

        system = """You analyze a developer's recent work to identify project intentions (goals/directions).
Return JSON: {"intentions": [{"intention": "...", "status": "active|completed|stalled|abandoned", "id": null_or_existing_id}]}
- For existing intentions: include their ID and update status if needed
- For new intentions: set id to null
- An intention is a high-level goal like "Add user authentication" or "Migrate to new DB schema"
- Mark intentions completed if the summaries show the work is done
- Mark stalled if no recent activity on that goal
- Keep the list focused: 3-8 intentions per project max"""

        try:
            result = call_claude(client, SONNET, system, user_msg)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"], result["output_tokens"])
            today = datetime.now().strftime("%Y-%m-%d")

            for item in parsed.get("intentions", []):
                existing_id = item.get("id")
                status = item.get("status", "active")
                intention_text = item.get("intention", "")

                if existing_id:
                    # Update existing
                    db.execute("""
                        UPDATE intentions SET status = ?, last_seen = ?,
                               evidence = (SELECT json_group_array(value) FROM (
                                   SELECT value FROM json_each(evidence)
                                   UNION SELECT ? as value
                               ))
                        WHERE id = ?
                    """, (status, today, json.dumps(summary_ids), existing_id))
                else:
                    # Create new
                    db.execute("""
                        INSERT INTO intentions (project, intention, evidence, status, first_seen, last_seen, model)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (project, intention_text, json.dumps(summary_ids), status, today, today, result["model"]))

            db.commit()

            log_synthesis(db, "intentions", today, project, result["model"],
                          result["input_tokens"], result["output_tokens"],
                          cost, result["duration_ms"], "success")

            n_intentions = len(parsed.get("intentions", []))
            print(f"OK ({n_intentions} intentions, ${cost/100:.4f})")

        except Exception as e:
            log_synthesis(db, "intentions", None, project, SONNET, 0, 0, 0, 0, "error", str(e))
            print(f"ERROR: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Synthesize daily summaries and intentions.")
    parser.add_argument("--daily", action="store_true", help="Generate missing daily summaries")
    parser.add_argument("--intentions", action="store_true", help="Update project intentions")
    parser.add_argument("--all", action="store_true", help="Run all synthesis steps")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD) for --daily")
    args = parser.parse_args()

    if not any([args.daily, args.intentions, args.all]):
        parser.print_help()
        sys.exit(1)

    # Load API key
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"Error: ANTHROPIC_API_KEY not found. Create {ENV_PATH} with:")
        print(f"  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    client = Anthropic()
    db = get_db()
    migrate(db)

    if args.all or args.daily:
        print("\n=== Daily Summaries ===")
        synthesize_daily_summaries(db, client, args.date)

    if args.all or args.intentions:
        print("\n=== Intentions ===")
        synthesize_intentions(db, client)

    # Print totals from this run
    recent_logs = db.execute("""
        SELECT run_type, SUM(cost_cents) as total_cost, COUNT(*) as calls,
               SUM(input_tokens) as total_in, SUM(output_tokens) as total_out
        FROM synthesis_log
        WHERE created_at > datetime('now', '-5 minutes')
        GROUP BY run_type
    """).fetchall()

    if recent_logs:
        print("\n=== Run Summary ===")
        total_cost = 0
        for log in recent_logs:
            print(f"  {log['run_type']}: {log['calls']} call(s), "
                  f"{log['total_in']}+{log['total_out']} tokens, ${log['total_cost']/100:.4f}")
            total_cost += log["total_cost"]
        print(f"  Total cost: ${total_cost/100:.4f}")

    db.close()


if __name__ == "__main__":
    main()
