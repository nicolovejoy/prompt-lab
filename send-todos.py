#!/usr/bin/env python3
"""Email todo digest via Resend."""

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

from todos import _scan_todos

DB_PATH = Path.home() / ".claude" / "prompt-history.db"


def _active_projects():
    """Return set of project names with status='active' (or no record) from DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        non_active = {row[0] for row in conn.execute(
            "SELECT name FROM projects WHERE status != 'active'"
        ).fetchall()}
        conn.close()
        return non_active
    except Exception:
        return set()

_SECTION_LABELS = {
    "next_steps": "Next Steps",
    "backlog": "Backlog",
    "planned": "Planned Features",
}

# --- Email formatting ---

SECTION_ORDER = ["next_steps", "backlog", "planned"]


def format_html(todos):
    """Group todos by project/section and render as HTML email."""
    # Group: {project: {section: [items]}}
    grouped = {}
    for t in todos:
        grouped.setdefault(t["project"], {}).setdefault(t["section"], []).append(t)

    projects = set(t["project"] for t in todos)

    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>",
        "<body style='font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #222;'>",
        "<h1 style='font-size: 20px; border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 20px;'>Todo Digest</h1>",
    ]

    for project in sorted(grouped):
        lines.append(f"<h2 style='font-size: 16px; margin: 24px 0 8px 0; color: #111;'>{project}</h2>")
        sections = grouped[project]
        for section in SECTION_ORDER:
            if section not in sections:
                continue
            label = _SECTION_LABELS[section]
            is_secondary = section in ("backlog", "planned")
            color = "#888" if is_secondary else "#222"
            lines.append(f"<h3 style='font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: {color}; margin: 12px 0 4px 0;'>{label}</h3>")
            lines.append(f"<ul style='margin: 0 0 8px 0; padding-left: 20px; color: {color};'>")
            for item in sections[section]:
                badge = ""
                if item["source"] == "MEMORY.md":
                    badge = " <span style='font-size: 10px; background: #e8e8e8; color: #666; padding: 1px 5px; border-radius: 3px; margin-left: 4px;'>MEMORY</span>"
                lines.append(f"<li style='margin: 3px 0; font-size: 14px;'>{item['text']}{badge}</li>")
            lines.append("</ul>")

    lines.append(f"<p style='font-size: 12px; color: #999; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px;'>{len(todos)} items across {len(projects)} projects</p>")
    lines.append("</body></html>")
    return "\n".join(lines)


def format_text(todos):
    """Plain text version of the digest."""
    grouped = {}
    for t in todos:
        grouped.setdefault(t["project"], {}).setdefault(t["section"], []).append(t)

    projects = set(t["project"] for t in todos)
    lines = ["TODO DIGEST", "=" * 40, ""]

    for project in sorted(grouped):
        lines.append(project.upper())
        sections = grouped[project]
        for section in SECTION_ORDER:
            if section not in sections:
                continue
            label = _SECTION_LABELS[section]
            lines.append(f"  {label}:")
            for item in sections[section]:
                suffix = " [MEMORY]" if item["source"] == "MEMORY.md" else ""
                lines.append(f"    - {item['text']}{suffix}")
        lines.append("")

    lines.append(f"{len(todos)} items across {len(projects)} projects")
    return "\n".join(lines)

# --- Resend API ---


def send_email(html, text, count, num_projects):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("Error: RESEND_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps({
        "from": "todos@soiree.pianohouseproject.org",
        "to": ["nlovejoy@me.com"],
        "subject": f"Todo Digest — {count} items across {num_projects} projects",
        "html": html,
        "text": text,
    }).encode()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "prompt-lab/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Resend API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)


def main():
    dry_run = "--dry-run" in sys.argv

    non_active = _active_projects()
    todos = [t for t in _scan_todos() if t["project"] not in non_active]
    if not todos:
        print("No todos found.")
        return

    projects = set(t["project"] for t in todos)
    html = format_html(todos)
    text = format_text(todos)

    if dry_run:
        print(text)
        print(f"\n--- {len(todos)} items across {len(projects)} projects (dry run, not sent) ---")
        return

    result = send_email(html, text, len(todos), len(projects))
    print(f"Sent: {len(todos)} items across {len(projects)} projects (id: {result.get('id', '?')})")
    print(f"\nCron example (every 3 days at 9am):")
    print(f"  0 9 */3 * * RESEND_API_KEY=$RESEND_API_KEY /usr/bin/python3 {Path(__file__).resolve()}")


if __name__ == "__main__":
    main()
