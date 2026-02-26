# prompt-lab

Workflow tools and dashboard for tracking your Claude Code prompts.

**Use Claude Code to get better at using Claude Code.**

Every prompt you send is raw material. Some prompts unlock exactly what you need in one shot. Others waste tokens going in circles. This toolkit helps you:

- **Track sessions** - Auto-log prompts, link commits to sessions
- **Synthesize patterns** - Daily summaries, intention extraction, theme analysis
- **Curate examples** - Tag and collect high-quality prompts for reference
- **Review visually** - Web dashboard with 5 views: Prompts, Summaries, Daily, Intentions, Themes

## Installation

```bash
git clone https://github.com/your-username/prompt-lab.git
cd prompt-lab
./install.sh
```

This will:
- Install slash commands to `~/.claude/commands/`
- Configure the prompt logging hook in `~/.claude/settings.json`
- Create the SQLite database at `~/.claude/prompt-history.db`
- Optionally install a `CLAUDE.md` template

Requirements: `jq`, `sqlite3`

## Slash Commands

All commands live in `~/.claude/commands/` (global) — they work across every repo. This project is the source of truth; `install.sh` copies them into place.

### /readup

Start a session. Registers session, reads CLAUDE.md, shows recent git history.

### /handoff

End a session. Logs commits, writes session summary, updates CLAUDE.md Next Steps.

### /report [N]

Generate a work summary for the last N days (default: 1), grouped by project.

### /review

Summarize recent work across sessions.

### /prompts [filters]

Query prompt history. Supports filters:
- `/prompts <project>` - filter by project
- `/prompts tag:debugging` - filter by tag

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
├── install.sh          # Install commands + hook to ~/.claude/
├── dashboard.sh        # Start dashboard
└── README.md
```

Slash commands are installed to `~/.claude/commands/` by `install.sh` — they are not kept in this repo's tree.

## License

MIT
