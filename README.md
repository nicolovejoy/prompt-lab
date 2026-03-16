# prompt-lab / Ground Control

Workflow tools and dashboard for tracking Claude Code sessions across projects.

Every session is logged, summarized, and surfaced in a local web dashboard. Slash commands handle session start/end and review. Optional nightly email reviews via the Anthropic API and Resend.

## What it does

- **Auto-logs prompts** via a Claude Code hook on every submission
- **Tracks sessions** with summaries, commit links, and token usage
- **Synthesizes patterns** nightly — daily summaries and active intentions per project
- **Dashboard** at localhost:5111 — project cards, session history, todos, intentions
- **Email reviews** (optional) — daily + weekly session digests via Resend

## Setup

### 1. Clone and install

```bash
git clone https://github.com/nicolovejoy/prompt-lab.git ~/src/prompt-lab
cd ~/src/prompt-lab
./workflow/install.sh
```

This will:
- Create a Python virtualenv and install dependencies
- Copy slash commands to `~/.claude/commands/`
- Generate and load launchd plists (macOS scheduled jobs)
- Print the `~/.claude/settings.json` snippet to add manually

Then add the printed snippet to `~/.claude/settings.json` and restart Claude Code.

### 2. Configure environment

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your keys and email addresses. See [Configuration](#configuration) below for details on each variable.

### 3. Set up CLAUDE.md (optional)

`workflow/CLAUDE.md.template` is a starting point for `~/.claude/CLAUDE.md`:

```bash
cp workflow/CLAUDE.md.template ~/.claude/CLAUDE.md
```

## Configuration

All configuration lives in `.env` (gitignored — never committed). See `.env.example` for the template.

### Required

- `ANTHROPIC_API_KEY` — needed for the synthesizer (nightly summaries) and review emails. Get one at [console.anthropic.com](https://console.anthropic.com). Can also be placed in `~/.claude/synthesizer.env`.

### Optional (email reviews)

Review emails are entirely optional. Without these, everything else works — dashboard, slash commands, synthesizer, prompt logging.

- `RESEND_API_KEY` — API key from [Resend](https://resend.com). Free tier allows 100 emails/day.
- `REVIEW_FROM_EMAIL` — sender address (e.g. `reviews@yourdomain.com`). Must be from a domain you've verified in Resend.
- `REVIEW_TO_EMAIL` — recipient address (e.g. `you@example.com`).

#### Setting up Resend

To send review emails, each user needs their own [Resend](https://resend.com) account:

1. Sign up at resend.com (free tier is fine)
2. Add and verify a sending domain (Resend walks you through adding DNS records)
3. Create an API key
4. Set all four email-related variables in your `.env`

If you don't want email reviews, simply omit the Resend variables. The synthesizer and dashboard work independently.

### What's private

These files contain your personal configuration and are **never committed** (gitignored):

- `.env` — API keys and email addresses
- `~/.claude/synthesizer.env` — alternative location for `ANTHROPIC_API_KEY`
- `~/.claude/prompt-history.db` — your session data

Everything else in the repo is shared infrastructure with no personal details.

## Dashboard

```bash
./dashboard.sh
```

Opens at http://localhost:5111

Project cards show: last session summary, todo count, active intentions, peak context usage. Click a card for the detail view — edit session summaries inline, manage status.

## Slash commands

All commands live in `~/.claude/commands/` and work across every repo. Source of truth is `workflow/commands/` — run `install.sh` to sync after updates.

`/readup` — start a session: registers it in DB, reads CLAUDE.md, shows recent git log

`/handoff` — end a session: logs commits, writes summary, updates CLAUDE.md Next Steps

`/review [N] [project] [-v]` — session review across projects for last N days (default: 7), optional verbose mode for non-technical audience

## Scheduled jobs

Two launchd jobs installed by `install.sh` (macOS only):

`com.promptlab.synthesizer` — runs `synthesizer.py --all` nightly at 2am, logs to `synthesizer.log`

`com.promptlab.review` — runs `send-review.py` daily at 2:30am (after synthesizer), logs to `send-review.log`. Includes both daily and weekly recaps; Saturday emails get deeper weekly analysis. Only runs if Resend is configured.

Manage them:

```bash
launchctl list | grep promptlab       # verify both registered
launchctl start com.promptlab.review  # trigger manually
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
│   │   └── review.md
│   ├── hooks/
│   │   ├── log-prompt.sh      # UserPromptSubmit hook
│   │   └── session-stop.sh    # Stop hook (final token count)
│   ├── com.promptlab.synthesizer.plist
│   ├── com.promptlab.review.plist
│   ├── CLAUDE.md.template
│   └── install.sh
├── synthesizer.py         # Nightly synthesis (summaries, intentions)
├── send-review.py         # Daily review email (optional)
├── todos.py               # Shared todo scanner
├── dashboard.sh           # Start dashboard
├── .env.example           # Configuration template
└── README.md
```

## Database

SQLite at `~/.claude/prompt-history.db` — created automatically on first prompt.

Key tables: `prompts`, `sessions` (with `token_count`), `commits`, `daily_summaries`, `intentions`, `projects`, `synthesis_log`.

Not included in this repo (`.gitignore`). Back up or sync separately.

## License

[MIT](LICENSE)
