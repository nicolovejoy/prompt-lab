# prompt-lab

Workflow tools and dashboard for tracking your Claude Code prompts.

**Use Claude Code to get better at using Claude Code.**

Every prompt you send is raw material. Some prompts unlock exactly what you need in one shot. Others waste tokens going in circles. This toolkit helps you:

- **Track sessions** - Auto-log prompts, link commits to sessions
- **Synthesize patterns** - Daily summaries, intention extraction, theme analysis
- **Curate examples** - Tag and collect high-quality prompts for reference
- **Review visually** - Web dashboard with 5 views: Prompts, Summaries, Daily, Intentions, Themes

## Setup (new machine)

1. Clone this repo
2. Copy slash commands: `cp ~/.claude/commands/*.md` won't exist yet — copy from a backup or recreate from this repo's git history (they lived in `workflow/commands/` before being moved to global)
3. Add the prompt-logging hook to `~/.claude/settings.json`:
   ```json
   "hooks": {
     "UserPromptSubmit": [{
       "hooks": [{"type": "command", "command": "<path-to>/workflow/hooks/log-prompt.sh", "timeout": 5000}]
     }]
   }
   ```
4. Add the sqlite3 allowlist rule to `~/.claude/settings.json`:
   ```json
   "permissions": {
     "allow": ["Bash(sqlite3 ~/.claude/prompt-history.db *)"]
   }
   ```
5. The DB (`~/.claude/prompt-history.db`) is created automatically by the hook on first prompt

Requirements: `sqlite3`

## Slash Commands

All commands live in `~/.claude/commands/` (global) — they work across every repo.

### /readup

Start a session. Registers session, reads CLAUDE.md, shows recent git history.

### /handoff

End a session. Logs commits, writes session summary, updates CLAUDE.md Next Steps.

### /report [N]

Generate a work summary for the last N days (default: 1), grouped by project.

### /review

Summarize recent work across sessions.

## Dashboard

```bash
./dashboard.sh
```

Opens at http://localhost:5111

Features:
- 5 views: Prompts, Summaries, Daily, Intentions, Themes
- Search by prompt text, tags, or project name
- Tag prompts for categorization
- Bulk delete unwanted prompts

### Keyboard shortcuts

- `j` / `k` or arrows: Navigate items
- `t`: Focus tags input
- `e`: Expand/collapse text
- `Space`: Toggle selection
- `x`: Delete selected
- `?`: Show help

## Database schema

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    project TEXT,
    prompt TEXT,
    tags TEXT,
    notes TEXT,
    session_id INTEGER,
    context TEXT
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    project TEXT,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT
);

CREATE TABLE commits (
    id INTEGER PRIMARY KEY,
    session_id INTEGER,
    hash TEXT,
    message TEXT,
    timestamp TEXT
);

CREATE TABLE daily_summaries (
    id INTEGER PRIMARY KEY,
    date TEXT,
    summary TEXT
);
```

## Repository structure

```
prompt-lab/
├── dashboard/          # Web UI
│   ├── server.py
│   ├── index.html
│   └── requirements.txt
├── workflow/           # Claude Code integrations
│   ├── hooks/
│   │   └── log-prompt.sh
│   └── CLAUDE.md.template
├── synthesizer.py      # Daily synthesis (summaries, intentions, themes)
├── dashboard.sh        # Start dashboard
└── README.md
```

Slash commands live in `~/.claude/commands/` (global, not tracked in this repo).

## License

MIT
