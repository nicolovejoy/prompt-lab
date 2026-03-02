"""Shared todo scanner used by dashboard/server.py and send-todos.py."""

import re
from pathlib import Path

SRC_DIR = Path.home() / "src"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

_SECTION_PATTERNS = [
    (re.compile(r"^##\s+(Next\s+Steps|Current\s+Next\s+Steps|What'?s\s+Next|Next\s+Session\s+TODO)\s*$", re.IGNORECASE), "next_steps"),
    (re.compile(r"^##\s+Backlog\s*$", re.IGNORECASE), "backlog"),
    (re.compile(r"^##\s+Planned\s+Features\s*$", re.IGNORECASE), "planned"),
]


def _parse_todo_sections(text):
    """Parse markdown text for todo sections, returning list of {section, text}."""
    results = []
    current_section = None

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("## "):
            current_section = None
            for pattern, section_name in _SECTION_PATTERNS:
                if pattern.match(stripped):
                    current_section = section_name
                    break
            continue

        if current_section and stripped:
            m = re.match(r"^(?:-|\d+\.)\s+(.+)$", stripped)
            if m:
                item_text = m.group(1)
                if re.match(r"^(DONE|SHIPPED)\b", item_text, re.IGNORECASE):
                    continue
                results.append({"section": current_section, "text": item_text})

    return results


def _scan_todos():
    """Scan CLAUDE.md and MEMORY.md files for todo items."""
    todos = []

    for claude_md in sorted(SRC_DIR.glob("*/CLAUDE.md")):
        project = claude_md.parent.name
        try:
            text = claude_md.read_text()
        except OSError:
            continue
        for item in _parse_todo_sections(text):
            todos.append({
                "project": project,
                "section": item["section"],
                "text": item["text"],
                "source": "CLAUDE.md",
            })

    for memory_md in sorted(CLAUDE_PROJECTS_DIR.glob("*/memory/MEMORY.md")):
        dir_name = memory_md.parent.parent.name
        m = re.search(r"-Users-\w+-src-(.+)$", dir_name)
        project = m.group(1) if m else dir_name
        try:
            text = memory_md.read_text()
        except OSError:
            continue
        for item in _parse_todo_sections(text):
            todos.append({
                "project": project,
                "section": item["section"],
                "text": item["text"],
                "source": "MEMORY.md",
            })

    return todos
