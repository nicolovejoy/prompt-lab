# prompt-lab / Ground Control

Workflow tools and dashboards for tracking Claude Code sessions across projects.

Every session is logged, summarized, and surfaced in a cloud dashboard. Slash commands handle session start/end and review. Nightly synthesis generates daily summaries, weekly rollups, and project snapshots. Optional email reviews and bi-monthly reports via the Anthropic API and Resend.

## What it does

- **Auto-logs prompts** via a Claude Code hook on every submission
- **Tracks sessions** with summaries, commit links, and token usage
- **Synthesizes patterns** nightly — daily summaries, weekly rollups, project snapshots
- **Cloud dashboard** on Vercel — auth-protected, reads from Turso; project cards, session history, cost tracking, and Ask (NLP Q&A)
- **Email reviews** (optional) — daily + weekly session digests via Resend
- **Bi-monthly reports** (optional) — longer-form markdown reports saved locally

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

- `ANTHROPIC_API_KEY` — needed for the synthesizer (nightly summaries) and review emails. Get one at [console.anthropic.com](https://console.anthropic.com). Place it in `.env.local`.

### Optional (email reviews)

Review emails are entirely optional. Without these, everything else works — dashboards, slash commands, synthesizer, prompt logging.

- `RESEND_API_KEY` — API key from [Resend](https://resend.com). Free tier allows 100 emails/day.
- `REVIEW_FROM_EMAIL` — sender address (e.g. `reviews@yourdomain.com`). Must be from a domain you've verified in Resend.
- `REVIEW_TO_EMAIL` — recipient address (e.g. `you@example.com`).

#### Setting up Resend

To send review emails, each user needs their own [Resend](https://resend.com) account:

1. Sign up at resend.com (free tier is fine)
2. Add and verify a sending domain (Resend walks you through adding DNS records)
3. Create an API key
4. Set all four email-related variables in your `.env`

If you don't want email reviews, simply omit the Resend variables. The synthesizer and dashboards work independently.

### Optional (cloud dashboard)

The cloud dashboard reads from Turso (hosted SQLite) and is deployed to Vercel.

- `TURSO_DATABASE_URL` — Turso database URL
- `TURSO_AUTH_TOKEN` — Turso auth token
- `AUTH_SECRET` — HMAC token-signing key, plus the preview-only password login (production auth is Google OAuth, see below)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS`, `READER_EMAILS` — Google sign-in for production (`ADMIN_EMAILS`/`READER_EMAILS` are email allowlists, not secrets)
- `BEACON_SALT` — visitor-hash salt for the page-view beacon, independent of `AUTH_SECRET`
- `ANTHROPIC_API_KEY` — also used for the cloud dashboard's Ask feature

To self-host: fork the repo, create a Turso database, set the env vars above in Vercel, deploy `web/` to Vercel.

### What's private

These files contain your personal configuration and are **never committed** (gitignored):

- `.env` / `.env.local` — API keys and email addresses
- `~/.claude/prompt-history.db` — your session data
- `reports/` — generated reports (personal project details)

Everything else in the repo is shared infrastructure with no personal details.

## Dashboard

The dashboard is the Vercel app in `web/` (Preact + HTM frontend, Python serverless API, reads from Turso).

```bash
cd web && vercel --prod
```

Auth-protected (cookie-based, single password). Features: overview stats, project detail, cost tracking, weekly rollups, review snapshots, and Ask (NLP Q&A powered by Claude). Push local SQLite data up with `python sync_to_turso.py`.

## Slash commands

All commands live in `~/.claude/commands/` and work across every repo. Source of truth is `workflow/commands/` — run `install.sh` to sync after updates.

`/readup` — start a session: registers it in DB, reads CLAUDE.md, shows recent git log

`/handoff` — end a session: logs commits, writes summary, updates CLAUDE.md Next Steps

`/review [N] [project] [-v]` — session review across projects for last N days (default: 7), optional verbose mode for non-technical audience

`/ask` — query the knowledge store with natural language

## Scheduled jobs

Three launchd jobs installed by `install.sh` (macOS only):

`com.promptlab.synthesizer` — runs `synthesizer.py --all` nightly at 2am, logs to `synthesizer.log`

`com.promptlab.review` — runs `send-review.py` daily at 2:30am (after synthesizer), logs to `send-review.log`. Includes both daily and weekly recaps; Saturday emails get deeper weekly analysis. Only runs if Resend is configured.

`com.promptlab.report` — runs `generate-report.py` bi-monthly (1st and 16th at 3am), logs to `generate-report.log`. Generates longer-form markdown reports saved to `reports/`.

Manage them:

```bash
launchctl list | grep promptlab       # verify all registered
launchctl start com.promptlab.review  # trigger manually
```

## Repository structure

```
prompt-lab/
├── store/
│   ├── base.py            # KnowledgeStore ABC (backend-agnostic)
│   ├── sqlite_store.py    # SQLite backend (local, default)
│   └── turso_store.py     # Turso HTTP backend (cloud)
├── web/
│   ├── index.html         # Cloud frontend (Preact + HTM)
│   ├── auth_helper.py     # Cookie-based auth
│   ├── turso_helper.py    # Turso HTTP client
│   ├── vercel.json        # Vercel config
│   └── api/               # Python serverless functions (9 endpoints)
├── mobile/
│   ├── index.html         # Legacy PWA (reads from Turso)
│   └── serve.py           # Local dev server
├── workflow/
│   ├── commands/          # Slash command source of truth
│   │   ├── readup.md
│   │   ├── handoff.md
│   │   ├── review.md
│   │   └── ask.md
│   ├── hooks/
│   │   ├── log-prompt.sh      # UserPromptSubmit hook
│   │   └── session-stop.sh    # Stop hook (final token count)
│   ├── com.promptlab.synthesizer.plist
│   ├── com.promptlab.review.plist
│   ├── com.promptlab.report.plist
│   ├── CLAUDE.md.template
│   └── install.sh
├── claude_api.py          # Shared Claude API utilities + env loading
├── synthesizer.py         # Nightly synthesis (summaries, rollups, snapshots)
├── send-review.py         # Daily review email (optional)
├── generate-report.py     # Bi-monthly report generator (optional)
├── sync_to_turso.py       # Push processed tables to Turso (no raw prompts)
├── todos.py               # Shared todo scanner (currently unwired)
├── .env.example           # Configuration template
└── README.md
```

## Database

SQLite at `~/.claude/prompt-history.db` — created automatically on first prompt.

Key tables: `prompts`, `sessions` (with `token_count`), `commits`, `daily_summaries`, `weekly_rollups`, `projects`, `project_snapshots`, `review_snapshots`, `synthesis_log`.

Not included in this repo (`.gitignore`). Back up or sync separately.

## License

[MIT](LICENSE)
