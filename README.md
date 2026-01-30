# prompt-lab

Workflow tools and dashboard for tracking your Claude Code prompts.

**Use Claude Code to get better at using Claude Code.**

Every prompt you send is raw material. Some prompts unlock exactly what you need in one shot. Others waste tokens going in circles. This toolkit helps you:

- **Track sessions** - Auto-log prompts, link commits to sessions
- **Learn what works** - Rate prompts by utility, spot patterns in effective requests
- **Curate examples** - Tag and collect high-quality prompts for reference
- **Review visually** - Web dashboard for browsing and rating prompts

## Installation

```bash
git clone https://github.com/your-username/prompt-lab.git
cd prompt-lab
./install.sh
```

This will:
- Install `/readup`, `/handoff`, `/prompts` commands to `~/.claude/commands/`
- Configure the prompt logging hook in `~/.claude/settings.json`
- Create the SQLite database at `~/.claude/prompt-history.db`
- Optionally install a `CLAUDE.md` template

Requirements: `jq`, `sqlite3`

## Commands

### /readup

Start a session. Registers session start time, lets you curate prompts from your last session (keep useful ones, delete noise), shows recent commits and Next Steps.

### /handoff

End a session. Logs commits made during the session, updates CLAUDE.md with new Next Steps, appends to devlog.md.

### /prompts

Query prompt history. Supports filters:
- `/prompts <project>` - filter by project
- `/prompts rated` - only utility 4+ prompts
- `/prompts tag:debugging` - filter by tag

## Dashboard

```bash
./dashboard.sh
```

Opens at http://localhost:5111

Features:
- Browse prompts by project, rated/unrated status
- Search by prompt text, tags, or project name
- Rate prompts 1-5 for utility tracking
- Tag prompts for categorization
- Bulk delete unwanted prompts

### Keyboard shortcuts

- `j` / `k` or arrows: Navigate prompts
- `1-5`: Rate selected prompt
- `t`: Focus tags input
- `e`: Expand/collapse prompt text
- `Space`: Toggle selection
- `x`: Delete selected prompts
- `?`: Show help

## Database schema

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    project TEXT,
    prompt TEXT,
    utility INTEGER,  -- 1-5 rating
    tags TEXT,        -- comma-separated
    notes TEXT,
    session_id INTEGER,
    context TEXT      -- last Claude response before this prompt
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    project TEXT,
    started_at TEXT,
    ended_at TEXT
);

CREATE TABLE commits (
    id INTEGER PRIMARY KEY,
    prompt_id INTEGER,
    hash TEXT,
    message TEXT,
    timestamp TEXT
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
│   ├── commands/
│   │   ├── readup.md
│   │   ├── handoff.md
│   │   └── prompts.md
│   ├── hooks/
│   │   └── log-prompt.sh
│   └── CLAUDE.md.template
├── install.sh          # Install workflow tools
├── dashboard.sh        # Start dashboard
└── README.md
```

## License

MIT
