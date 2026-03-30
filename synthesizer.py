#!/usr/bin/env python3
"""Synthesizer — generates daily summaries, weekly rollups, intentions, and project snapshots."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

from claude_api import OPUS, SONNET, call_claude, estimate_cost_cents, load_env
from store import get_store


# ---------------------------------------------------------------------------
# Tool definitions for structured output
# ---------------------------------------------------------------------------

SUMMARY_TOOL = {
    "name": "generate_summary",
    "description": "Generate a daily summary of the developer's work.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "2-4 sentence summary of what was accomplished"},
            "key_decisions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key decisions made during the day",
            },
        },
        "required": ["summary", "key_decisions"],
    },
}

INTENTIONS_TOOL = {
    "name": "generate_intentions",
    "description": "Analyze recent work and return project intentions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intentions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intention": {"type": "string"},
                        "status": {"type": "string", "enum": ["active", "completed", "stalled", "abandoned"]},
                        "id": {"type": ["integer", "null"]},
                    },
                    "required": ["intention", "status", "id"],
                },
                "description": "List of project intentions",
            },
        },
        "required": ["intentions"],
    },
}


# ---------------------------------------------------------------------------
# Synthesis functions
# ---------------------------------------------------------------------------

def synthesize_daily_summaries(store, client, target_date=None):
    """Generate daily summaries for all unsummarized (project, date) pairs."""
    pairs = store.get_unsummarized_days(target_date)
    if not pairs:
        print("No unsummarized days found.")
        return

    print(f"Found {len(pairs)} unsummarized day(s).")

    for project, date in pairs:
        print(f"  Summarizing {project} / {date}...", end=" ", flush=True)
        data = store.get_day_data(project, date)

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
Focus on WHAT was done and WHY, not low-level details. Be concise."""

        try:
            result = call_claude(client, model=OPUS, system=system,
                                 user_msg=user_msg, tool=SUMMARY_TOOL)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"],
                                       result["output_tokens"])

            store.upsert_daily_summary(
                project=project, date=date,
                summary=parsed.get("summary", ""),
                key_decisions=parsed.get("key_decisions", []),
                prompt_count=len(data["prompts"]),
                session_count=len(data["sessions"]),
                commit_count=len(data["commits"]),
                model=result["model"],
            )

            store.log_synthesis(
                run_type="daily", target_date=date, project=project,
                model=result["model"], input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"], cost_cents=cost,
                duration_ms=result["duration_ms"], status="success",
            )

            print(f"OK ({result['input_tokens']}+{result['output_tokens']} tokens, ${cost/100:.4f})")

        except Exception as e:
            store.log_synthesis(
                run_type="daily", target_date=date, project=project,
                model=OPUS, input_tokens=0, output_tokens=0,
                cost_cents=0, duration_ms=0, status="error",
                error_message=str(e),
            )
            print(f"ERROR: {e}")


def synthesize_intentions(store, client):
    """Update/create/close intentions for each project with recent summaries."""
    projects = store.get_projects_with_recent_summaries()
    if not projects:
        print("No projects with recent summaries.")
        return

    print(f"Updating intentions for {len(projects)} project(s).")

    for project in projects:
        print(f"  Intentions for {project}...", end=" ", flush=True)

        summaries = store.get_daily_summaries(project=project, limit=14)
        summary_texts = []
        summary_ids = []
        for s in summaries:
            summary_texts.append(f"[{s['date']}] {s['summary']}")
            summary_ids.append(s["id"])

        current_intentions = store.get_intentions(project=project, status="active")

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
- For existing intentions: include their ID and update status if needed
- For new intentions: set id to null
- An intention is a high-level goal like "Add user authentication" or "Migrate to new DB schema"
- Mark intentions completed if the summaries show the work is done
- Mark stalled if no recent activity on that goal
- Keep the list focused: 3-8 intentions per project max"""

        try:
            result = call_claude(client, model=OPUS, system=system,
                                 user_msg=user_msg, tool=INTENTIONS_TOOL)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"],
                                       result["output_tokens"])

            for item in parsed.get("intentions", []):
                store.upsert_intention(
                    id=item.get("id"),
                    project=project,
                    intention=item.get("intention", ""),
                    evidence_summary_ids=summary_ids,
                    status=item.get("status", "active"),
                    model=result["model"],
                )

            today = datetime.now().strftime("%Y-%m-%d")
            store.log_synthesis(
                run_type="intentions", target_date=today, project=project,
                model=result["model"], input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"], cost_cents=cost,
                duration_ms=result["duration_ms"], status="success",
            )

            n_intentions = len(parsed.get("intentions", []))
            print(f"OK ({n_intentions} intentions, ${cost/100:.4f})")

        except Exception as e:
            store.log_synthesis(
                run_type="intentions", target_date=None, project=project,
                model=OPUS, input_tokens=0, output_tokens=0,
                cost_cents=0, duration_ms=0, status="error",
                error_message=str(e),
            )
            print(f"ERROR: {e}")


WEEKLY_ROLLUP_TOOL = {
    "name": "generate_weekly_rollup",
    "description": "Generate a weekly rollup from daily summaries.",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {"type": "string", "description": "3-5 sentence narrative of the week's work"},
            "highlights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key accomplishments or milestones from the week",
            },
        },
        "required": ["narrative", "highlights"],
    },
}


def synthesize_weekly_rollups(store, client):
    """Generate weekly rollups for completed weeks missing them."""
    pairs = store.get_weeks_without_rollups()
    if not pairs:
        print("No weeks need rollups.")
        return

    print(f"Found {len(pairs)} week(s) to roll up.")

    for project, week_start in pairs:
        print(f"  Rollup {project} / week of {week_start}...", end=" ", flush=True)

        summaries = store.get_daily_summaries_for_week(project, week_start)
        if not summaries:
            print("SKIP (no summaries)")
            continue

        summary_texts = [f"[{s['date']}] {s['summary']}" for s in summaries]
        summary_ids = [s["id"] for s in summaries]
        total_prompts = sum(s.get("prompt_count", 0) for s in summaries)
        total_sessions = sum(s.get("session_count", 0) for s in summaries)
        total_commits = sum(s.get("commit_count", 0) for s in summaries)

        user_msg = f"""Project: {project}
Week of: {week_start}
Active days: {len(summaries)}

Daily summaries:
{chr(10).join(summary_texts)}"""

        system = """You write concise weekly rollups of a developer's work on a project.
Synthesize the daily summaries into a cohesive narrative of what happened that week.
Focus on progress, decisions, and direction — not individual tasks."""

        try:
            result = call_claude(client, model=OPUS, system=system,
                                 user_msg=user_msg, tool=WEEKLY_ROLLUP_TOOL)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"],
                                       result["output_tokens"])

            store.upsert_weekly_rollup(
                project=project, week_start=week_start,
                narrative=parsed.get("narrative", ""),
                highlights=parsed.get("highlights", []),
                daily_summary_ids=summary_ids,
                prompt_count=total_prompts,
                session_count=total_sessions,
                commit_count=total_commits,
                model=result["model"],
            )

            store.log_synthesis(
                run_type="weekly_rollup", target_date=week_start, project=project,
                model=result["model"], input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"], cost_cents=cost,
                duration_ms=result["duration_ms"], status="success",
            )

            print(f"OK ({len(summaries)} days, ${cost/100:.4f})")

        except Exception as e:
            store.log_synthesis(
                run_type="weekly_rollup", target_date=week_start, project=project,
                model=OPUS, input_tokens=0, output_tokens=0,
                cost_cents=0, duration_ms=0, status="error",
                error_message=str(e),
            )
            print(f"ERROR: {e}")


PROJECT_STATE_TOOL = {
    "name": "generate_project_state",
    "description": "Generate a concise project state summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "state_summary": {
                "type": "string",
                "description": "2-4 sentence summary of where this project stands right now: what it is, recent direction, current status, and what's next",
            },
        },
        "required": ["state_summary"],
    },
}


def synthesize_project_states(store, client):
    """Generate weekly project state summaries. Runs on Sundays."""
    projects = store.get_projects_with_recent_summaries(n_days=14)
    if not projects:
        print("No projects with recent activity.")
        return

    print(f"Generating state summaries for {len(projects)} project(s).")

    for project in projects:
        print(f"  State for {project}...", end=" ", flush=True)

        rollups = store.get_weekly_rollups(project=project, limit=3)
        intentions = store.get_intentions(project=project, status="active")
        summaries = store.get_daily_summaries(project=project, limit=7)

        rollup_texts = [f"[Week of {r['week_start']}] {r['narrative']}" for r in rollups]
        intention_texts = [f"- {i['intention']}" for i in intentions]
        decision_texts = []
        for s in summaries:
            kd = s.get("key_decisions", "[]")
            if isinstance(kd, str):
                try:
                    kd = json.loads(kd)
                except Exception:
                    kd = []
            for d in (kd or []):
                decision_texts.append(f"- {d}")

        user_msg = f"""Project: {project}

Recent weekly rollups:
{chr(10).join(rollup_texts) or '(none)'}

Active intentions:
{chr(10).join(intention_texts) or '(none)'}

Recent key decisions:
{chr(10).join(decision_texts[:10]) or '(none)'}"""

        system = """You write concise project state summaries for a developer's dashboard.
Describe what this project IS, what's been happening recently, where it's headed, and its current momentum.
Be direct and specific — no filler. 2-4 sentences max."""

        try:
            result = call_claude(client, model=SONNET, system=system,
                                 user_msg=user_msg, tool=PROJECT_STATE_TOOL)
            parsed = result["parsed"]
            cost = estimate_cost_cents(result["model"], result["input_tokens"],
                                       result["output_tokens"])

            # Store in project_snapshots data blob
            existing = store.get_project_snapshot(project)
            snapshot_data = {}
            if existing and existing.get("data"):
                d = existing["data"]
                snapshot_data = d if isinstance(d, dict) else json.loads(d)

            snapshot_data["state_summary"] = parsed.get("state_summary", "")

            today = datetime.now().strftime("%Y-%m-%d")
            store.save_project_snapshot(project=project, date=today, data=snapshot_data)

            store.log_synthesis(
                run_type="project_state", target_date=today, project=project,
                model=result["model"], input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"], cost_cents=cost,
                duration_ms=result["duration_ms"], status="success",
            )

            print(f"OK (${cost/100:.4f})")

        except Exception as e:
            store.log_synthesis(
                run_type="project_state", target_date=None, project=project,
                model=SONNET, input_tokens=0, output_tokens=0,
                cost_cents=0, duration_ms=0, status="error",
                error_message=str(e),
            )
            print(f"ERROR: {e}")


def generate_project_snapshots(store):
    """Generate project snapshots from current data. Pure SQL, no Claude call."""
    projects = store.get_projects_with_recent_summaries(n_days=7)
    if not projects:
        print("No projects with recent activity.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"Generating snapshots for {len(projects)} project(s).")

    # Load project metadata (github_url, site_url) if available
    project_meta = {}
    try:
        for row in store._conn.execute(
            "SELECT name, github_url, site_url FROM projects"
        ).fetchall():
            project_meta[row["name"]] = {
                "github_url": row["github_url"],
                "site_url": row["site_url"],
            }
    except Exception:
        pass  # Turso or missing columns — skip gracefully

    for project in projects:
        intentions = store.get_intentions(project=project, status="active")
        summaries_7d = store.get_daily_summaries(project=project, limit=7)

        total_prompts = sum(s.get("prompt_count", 0) for s in summaries_7d)
        total_sessions = sum(s.get("session_count", 0) for s in summaries_7d)
        total_commits = sum(s.get("commit_count", 0) for s in summaries_7d)

        data = {
            "active_intentions": [i["intention"] for i in intentions],
            "session_count_7d": total_sessions,
            "prompt_count_7d": total_prompts,
            "commit_count_7d": total_commits,
            "active_days_7d": len(summaries_7d),
        }

        # Include URLs from projects table if available
        meta = project_meta.get(project, {})
        if meta.get("github_url"):
            data["github_url"] = meta["github_url"]
        if meta.get("site_url"):
            data["site_url"] = meta["site_url"]

        store.save_project_snapshot(project=project, date=today, data=data)
        print(f"  {project}: {len(summaries_7d)} days, {len(intentions)} intentions")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Synthesize daily summaries, weekly rollups, and intentions.")
    parser.add_argument("--daily", action="store_true", help="Generate missing daily summaries")
    parser.add_argument("--weekly", action="store_true", help="Generate missing weekly rollups")
    parser.add_argument("--intentions", action="store_true", help="Update project intentions")
    parser.add_argument("--snapshots", action="store_true", help="Generate project snapshots")
    parser.add_argument("--states", action="store_true", help="Generate project state summaries (weekly)")
    parser.add_argument("--all", action="store_true", help="Run all synthesis steps")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD) for --daily")
    args = parser.parse_args()

    if not any([args.daily, args.weekly, args.intentions, args.snapshots, args.states, args.all]):
        parser.print_help()
        sys.exit(1)

    # Load environment
    needs_api = args.all or args.daily or args.weekly or args.intentions or args.states
    load_env()
    if needs_api and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found. Set in .env.local or ~/.claude/synthesizer.env")
        sys.exit(1)

    client = Anthropic() if needs_api else None
    store = get_store()
    store.migrate()

    if args.all or args.daily:
        print("\n=== Daily Summaries ===")
        synthesize_daily_summaries(store, client, args.date)

    if args.all or args.intentions:
        print("\n=== Intentions ===")
        synthesize_intentions(store, client)

    if args.all or args.weekly:
        print("\n=== Weekly Rollups ===")
        synthesize_weekly_rollups(store, client)

    if args.all or args.states:
        # Only run states on Sundays (or when explicitly requested)
        is_sunday = datetime.now().weekday() == 6
        if args.states or is_sunday:
            print("\n=== Project State Summaries ===")
            synthesize_project_states(store, client)
        elif args.all:
            print("\n=== Project State Summaries ===")
            print("Skipped (runs on Sundays only; use --states to force)")

    if args.all or args.snapshots:
        print("\n=== Project Snapshots ===")
        generate_project_snapshots(store)

    # Print totals from this run
    recent_logs = store.get_recent_synthesis_logs()

    if recent_logs:
        print("\n=== Run Summary ===")
        total_cost = 0
        for log in recent_logs:
            print(f"  {log['run_type']}: {log['calls']} call(s), "
                  f"{log['total_in']}+{log['total_out']} tokens, ${log['total_cost']/100:.4f}")
            total_cost += log["total_cost"]
        print(f"  Total cost: ${total_cost/100:.4f}")

    store.close()


if __name__ == "__main__":
    main()
