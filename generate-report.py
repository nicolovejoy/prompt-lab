#!/usr/bin/env python3
"""Generate a verbose narrative work review and save it to reports/."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from claude_api import OPUS, call_claude
from store import get_store

REPO_DIR = Path(__file__).resolve().parent
REPORTS_DIR = REPO_DIR / "reports"


REPORT_TOOL = {
    "name": "generate_report",
    "description": "Generate the Markdown work review report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "markdown": {"type": "string", "description": "Full Markdown report content"},
        },
        "required": ["markdown"],
    },
}


def build_prompt(sessions, daily_summaries, stats, days):
    def format_sessions(rows):
        return chr(10).join(f"[{s['date']}] {s['project']}: {s['summary']}" for s in rows) or "(none)"

    def format_summaries(rows):
        return chr(10).join(f"[{ds['date']}] {ds['project']}: {ds['summary']}" for ds in rows) or "(none)"

    def format_stats(st):
        lines = [f"Total: {st['total_prompts']} prompts, {st['total_sessions']} sessions, {st['total_projects']} projects"]
        lines.append("")
        lines.append("By project:")
        for p in st["projects"]:
            lines.append(f"  {p['name']}: {p['prompts']} prompts, {p['active_days']} active days")
        return chr(10).join(lines)

    today = datetime.now().strftime("%A, %B %-d, %Y")

    user_msg = f"""Date: {today}
Review period: last {days} days

== Activity stats ==

{format_stats(stats)}

== Session summaries ({len(sessions)}) ==

{format_sessions(sessions)}

== Daily summaries ({len(daily_summaries)}) ==

{format_summaries(daily_summaries)}"""

    system = f"""You write narrative work reviews summarizing a developer's recent sessions across all projects.

Write a comprehensive review in Markdown format. Structure:

1. **Header**: `# Work Review — Last {days} days` with today's date in italics

2. **Per-project sections** (H2 headings, ordered by significance):
   - Bold project name as heading
   - 2-3 paragraph narrative explaining what was worked on, why, and what was accomplished
   - Explain technical concepts briefly — spell out acronyms, say what tools do
   - Include context: what problem was being solved, what approach was taken, what the outcome was
   - Mention blockers hit and how they were resolved
   - If multiple sessions exist for a project, walk through them chronologically
   - Include commit counts and activity days from the stats when relevant

3. **Other Projects** section for projects with only 1-2 sessions — bullet points with one-line summaries

4. **Summary** section: 2-3 sentences on overall themes and patterns across all projects

Tone: matter-of-fact and informative. The reader is smart but not an engineer. This is a factual record of what happened — not a performance review. Do not praise, compliment, or editorialize about productivity. Do not declare anything "complete" or "done" — work is always ongoing, just at different stages. Describe where things stand, not that they're finished. Just describe the work clearly.

Use horizontal rules (---) between major project sections for readability."""

    return system, user_msg


def main():
    dry_run = "--dry-run" in sys.argv

    # Parse days argument (default 30)
    days = 30
    for arg in sys.argv[1:]:
        if arg.isdigit():
            days = int(arg)

    # Load environment
    env_path = REPO_DIR / ".env"
    synth_env = Path.home() / ".claude" / "synthesizer.env"
    if env_path.exists():
        load_dotenv(env_path)
    if synth_env.exists():
        load_dotenv(synth_env, override=False)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found in .env or ~/.claude/synthesizer.env", file=sys.stderr)
        sys.exit(1)

    store = get_store()
    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    sessions = store.get_raw_sessions(since_days=days)
    daily_summaries = store.get_daily_summaries(since=since_date)
    stats = store.get_period_stats(days)
    store.close()

    if not sessions and not daily_summaries:
        print("No sessions or summaries found for the period.")
        return

    system, user_msg = build_prompt(sessions, daily_summaries, stats, days)

    if dry_run:
        print(f"Would generate {days}-day report")
        print(f"  Sessions: {len(sessions)}")
        print(f"  Daily summaries: {len(daily_summaries)}")
        print(f"  Stats: {stats['total_prompts']} prompts, {stats['total_sessions']} sessions")
        print(f"\nPrompt length: {len(user_msg)} chars")
        return

    client = Anthropic()
    result = call_claude(client, model=OPUS, system=system, user_msg=user_msg,
                         tool=REPORT_TOOL, max_tokens=16384)

    markdown = result["parsed"].get("markdown", "")

    # Write to reports/
    REPORTS_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-review-{days}d.md"
    filepath = REPORTS_DIR / filename

    filepath.write_text(markdown + "\n")

    print(f"Generated {days}-day report in {result['duration_ms']/1000:.1f}s "
          f"({result['input_tokens']}+{result['output_tokens']} tokens)")
    print(f"Model: {OPUS}")
    print(f"Saved: {filepath}")

    # Persist the review
    store = get_store()
    store.migrate()
    store.save_review_snapshot(
        review_type="monthly_report", date=today, subject=f"{days}-day review",
        content_markdown=markdown, model=OPUS,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
    )
    store.close()


if __name__ == "__main__":
    main()
