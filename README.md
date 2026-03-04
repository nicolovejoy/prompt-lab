# prompt-lab / Ground Control

Workflow tools and dashboard for tracking Claude Code sessions across projects.

Every session is logged, summarized, and surfaced in a local web dashboard. Slash commands handle session start/end, reporting, and review.

## What it does

- **Auto-logs prompts** via a Claude Code hook on every submission
- **Tracks sessions** with summaries, commit links, and token usage
- **Synthesizes patterns** nightly — daily summaries and active intentions per project
- **Emails todo digests** Mon/Thu from your CLAUDE.md and MEMORY.md files
- **Dashboard** at localhost:5111 — project cards, session history, todos, intentions

## Setup (new machine)

Install script handles everything:

```bash
git clone https://github.com/nicolovejoy/prompt-lab.git ~/src/prompt-lab
cd ~/src/prompt-lab
./workflow/install.sh
```

This will:
- Copy slash commands to `~/.claude/commands/`
- Generate and load launchd plists (nightly synthesizer, Mon/Thu todo emails)
- Print the `~/.claude/settings.json` snippet to add manually

Then add the printed snippet to `~/.claude/settings.json` and restart Claude Code.

### .env (required for todo emails)

Create `~/src/prompt-lab/.env`:

```
RESEND_API_KEY=your_key_here
TODO_EMAIL_TO=you@example.com
```

### CLAUDE.md template

`workflow/CLAUDE.md.template` is a starting point for `~/.claude/CLAUDE.md`. Copy and customize:

```bash
cp workflow/CLAUDE.md.template ~/.claude/CLAUDE.md
```

## Dashboard

Start it:

```bash
./dashboard.sh
```

Opens at http://localhost:5111

Project cards show: last session summary, todo count, active intentions, peak context usage. Click a card for the detail view — edit session summaries inline, manage status.

## Slash commands

All commands live in `~/.claude/commands/` and work across every repo. Source of truth is `workflow/commands/` — run `install.sh` to sync after updates.

`/readup` — start a session: registers it in DB, reads CLAUDE.md, shows recent git log

`/handoff` — end a session: logs commits, writes summary, updates CLAUDE.md Next Steps

`/report [N] [-v]` — work summary for last N days (default: 1), optional verbose mode

`/review [N] [project]` — session review across projects for last N days (default: 7)

## Scheduled jobs

Two launchd jobs installed by `install.sh` (macOS only):

`com.promptlab.synthesizer` — runs `synthesizer.py --all` nightly at 2am, logs to `synthesizer.log`

`com.promptlab.todos` — runs `send-todos.py` Monday and Thursday at 9am, logs to `send-todos.log`

Manage them:

```bash
launchctl list | grep promptlab       # verify both registered
launchctl start com.promptlab.todos   # trigger manually
```

## Repository structure

```
prompt-lab/
├── dashboard/
│   ├── server.py          # Flask API (port 5111)
│   ├── index.html         # Frontend (Preact + HTM, no build step)
│   └── requirements.txt
├── workflow/
│   ├── commands/          # Slash command source of truth
│   │   ├── readup.md
│   │   ├── handoff.md
│   │   ├── report.md
│   │   └── review.md
│   ├── hooks/
│   │   ├── log-prompt.sh      # UserPromptSubmit hook
│   │   └── session-stop.sh    # Stop hook (final token count)
│   ├── com.promptlab.synthesizer.plist
│   ├── com.promptlab.todos.plist
│   ├── CLAUDE.md.template
│   └── install.sh
├── synthesizer.py         # Nightly synthesis (summaries, intentions)
├── send-todos.py          # Todo email digest
├── todos.py               # Shared todo scanner
├── dashboard.sh           # Start dashboard
└── README.md
```

## Database

SQLite at `~/.claude/prompt-history.db` — created automatically on first prompt.

Key tables: `prompts`, `sessions` (with `token_count`), `commits`, `daily_summaries`, `intentions`, `projects`, `synthesis_log`.

Not included in this repo (`.gitignore`). Back up or sync separately.

## License

MIT
