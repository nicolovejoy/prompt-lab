"""One-shot: write public-safe session summaries + weekly rollups for prompt-lab.

Summaries authored by the running Claude Code session (Opus 4.7) based on
private session.summary text. Empty sessions (12, 14, 15, 40) skipped.
Internal-only domain (anomatom.com) generalized to "the cloud dashboard".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store  # noqa: E402

PROJECT = "prompt-lab"

SESSIONS = [
    (20, "2026-01-30 16:45:50",
     "Restructured the repo for easy installation with bootstrap scripts. "
     "Added session summaries to the handoff command with a dashboard view. "
     "UX improvements: auto-advance, undo toasts, and context-aware stats. "
     "Integrated a one-task-per-session approach into the readup command."),
    (28, "2026-01-31 15:18:32",
     "Dashboard UX improvements: clickable stat buttons that filter views, "
     "grid-based arrow-key navigation across stats, toggles, filters, and "
     "cards, and a thirty-percent size reduction on rating buttons. Fixed a "
     "focus bug where filter inputs trapped keyboard input."),
    (31, "2026-01-31 17:04:23",
     "Simplified workflow commands. Removed the devlog file from readup and "
     "handoff (summaries now live in the database only) and removed "
     "implementation-plan and spec checks from readup. Added an About link "
     "to the dashboard header."),
    (81, "2026-02-23 21:46:00",
     "Stripped the manual rating workflow from the dashboard and server. "
     "Removed rating buttons, bulk delete, undo toast, and rated filter, and "
     "deleted four server endpoints. Renamed the app to Prompt Analyst. "
     "Simplified stats to totals only. The synthesizer pipeline now provides "
     "the analytical layer ratings were meant to enable."),
    (91, "2026-02-25 04:07:47",
     "Ran the report command across one-, seven-, and thirty-day windows. "
     "Added a sqlite3 permission rule to the global Claude Code settings so "
     "report queries auto-approve without prompting."),
    (98, "2026-02-25 22:32:49",
     "Simplified the readup and handoff slash commands. Readup cut from "
     "thirty-nine to sixteen lines — removed doc cleanup, prompt query, task "
     "suggestion. Handoff cut from fifty-nine to thirty lines — merged "
     "session close into summary update."),
    (99, "2026-02-25 22:54:55",
     "Code-quality fixes: closed database connection leaks via context "
     "manager, replaced an N+1 sessions query with a batched IN(), caught a "
     "GROUP_CONCAT delimiter bug during testing, and fixed a stale "
     "virtualenv on the dashboard launcher."),
    (105, "2026-02-26 18:01:05",
     "Added a Todos dashboard view as a sixth tab. The backend scrapes "
     "CLAUDE.md and memory files for Next Steps and Backlog sections with a "
     "five-minute server cache and a force-refresh button. The frontend "
     "groups by project with section labels, muted backlog styling, and "
     "badges."),
    (110, "2026-02-26 21:49:05",
     "Fixed slash-command permission prompts. Added cd/ls to the readup "
     "allowed-tools list and restructured report queries to dodge an "
     "empty-quotes-before-dash security heuristic."),
    (111, "2026-02-26 22:09:47",
     "Fixed the report-command permission-prompt bug, moved slash commands "
     "from project-local symlinks to real files in the global Claude Code "
     "commands directory, and added a verbose flag to the report command "
     "for narrative output."),
    (119, "2026-02-27 23:44:38",
     "Project-centric redesign of the dashboard. Rewrote the front page with "
     "Preact + HTM, added a per-project overview API endpoint returning "
     "per-project cards, and added server-side project hiding via a config "
     "file."),
    (140, "2026-03-02 16:17:12",
     "Added a project detail page as the landing view for project clicks — "
     "shows the last session, intentions, next steps, and status control in "
     "one place. New per-project API endpoint backs it."),
    (146, "2026-03-03 17:03:57",
     "Implemented five planned improvements: token tracking on sessions, a "
     "session-stop hook that writes a final tally, a peak-context percentage "
     "on dashboard cards, a synthesizer last-run footer, inline "
     "session-summary editing, and a launchd job for nightly synthesis."),
    (150, "2026-03-03 21:43:09",
     "Replaced crontab with launchd for the todos email job (Mondays and "
     "Thursdays, 9 AM). Debugged why the email had silently stopped firing. "
     "Both launchd jobs verified registered."),
    (154, "2026-03-04 08:30:00",
     "Replaced the remaining crontabs with launchd for both the todos email "
     "and the synthesizer. Created a workflow installer for new-machine "
     "setup, added a workflow commands directory as the source of truth for "
     "slash commands, and made the launchd plists generic with placeholder "
     "substitution."),
    (155, "2026-03-04 19:14:47",
     "Synced the global Claude Code commands directory with the workflow "
     "source-of-truth, generalized examples in the review command, and ran "
     "the installer to push commands out. Removed a debug plugin from "
     "settings."),
    (163, "2026-03-05 15:43:00",
     "Fixed the todos email after the email-service API key had been "
     "rotated. Updated the secrets and verified delivery — fifty-six items "
     "in the digest. The launchd job is operational again."),
    (182, "2026-03-10 17:35:50",
     "Built a processed knowledge layer with a backend-agnostic store "
     "abstraction (SQLite and Turso backends), weekly rollups, project "
     "snapshots, and review snapshots. Created a mobile PWA with Turso "
     "sync, project filter, and an ask tab. Added the ask command and "
     "updated handoff for inline synthesis."),
    (193, "2026-03-15 17:06:23",
     "Upgraded the review-email script — switched to claude-sonnet-4-6, "
     "always sends both one-day and seven-day windows, added retry and "
     "fallback for JSON parsing errors, and bumped the max-tokens limit."),
    (194, "2026-03-15 18:56:01",
     "Switched the review-email and synthesizer scripts from JSON text "
     "parsing to structured-output tool use. Removed fence stripping, "
     "json.loads, and fallback handlers. Dry run confirmed clean output."),
    (202, "2026-03-16 16:09:13",
     "Built a bi-monthly report generator that runs via launchd on the "
     "first and sixteenth of each month. Switched all API calls to Opus. "
     "Enhanced the status line with model, token in/out, colored "
     "context-percentage, duration, and timestamp. Added no-praise and "
     "no-finality tone rules to reviews."),
    (208, "2026-03-19 16:28:26",
     "Updated the status line: removed the cost display, changed context "
     "wording, and added timezone to the timestamp."),
    (217, "2026-03-22 20:11:44",
     "Fixed the turn indicator to be session-aware, fixed config display, "
     "builder activity tracking, and name editing. Added inline wireframe "
     "mockups: a wireframe-preview component, a message-content parser, a "
     "mockup editor, system-prompt integration, and a prep-prompt schema."),
    (221, "2026-03-27 18:12:15",
     "Set up a multi-machine workflow with hostname tracking and the "
     "status-line script in the repo. Synced processed data to Turso, "
     "cleaned up the codebase for sharing, and built and deployed a cloud "
     "dashboard with cookie authentication and a Turso backend."),
    (227, "2026-03-29 01:39:42",
     "Added a global PreToolUse hook that blocks reads, writes, and grep "
     "against environment files and other secrets. Audited and found three "
     "repos using a shared API key. Updated the global CLAUDE.md security "
     "section."),
    (231, "2026-03-29 18:28:15",
     "Redesigned the cloud dashboard as a Project Hub. Added hash-based "
     "routing with deep-linking, a breadcrumb header showing deployment "
     "info, GitHub-style activity heat bars on project cards, a vertical "
     "timeline, and an ask modal. Added 1Password CLI safety rules to the "
     "PreToolUse hook."),
    (234, "2026-03-29 22:04:27",
     "Set up a 1Password dev-secrets vault for secret management with "
     ".env.tpl templates. Configured a transactional-email sending domain "
     "via Cloudflare. Propagated the 1Password practice across all projects "
     "via memory and CLAUDE.md updates."),
    (271, "2026-04-05 01:33:21",
     "Fixed the nightly review email after a 1Password migration broke it — "
     "the launchd plist still sourced a removed file. Updated the template "
     "to call Python directly and fixed a 1Password item reference."),
    (290, "2026-04-09 17:37:44",
     "Added a blanket robots.txt disallow and a rewrite to block all "
     "crawlers on the cloud dashboard after the CDN provider flagged AI-bot "
     "activity. Deployed to production. Queued a Google OAuth login "
     "migration as the next authentication work."),
    (301, "2026-04-12 19:53:19",
     "Improved readup with last-session context and handoff with an "
     "uncommitted-changes warning. Strengthened the global conciseness "
     "directives in CLAUDE.md. Evaluated an external terseness plugin — "
     "decided against it, achieved similar terseness via CLAUDE.md "
     "instructions instead."),
    (307, "2026-04-13 00:15:40",
     "Audited the codebase for references to the deprecated sonnet-4 model, "
     "upgraded the ask command's model, and tracked the migration across "
     "five projects to completion. Added a check-model-refs script."),
    (318, "2026-04-18 22:25:49",
     "Fixed a /tmp race in handoff by parameterizing the daily and weekly "
     "summary filenames with project and session ID. Added git pull "
     "--rebase to readup so remote changes are picked up at session start."),
    (351, "2026-05-06 17:22:48",
     "Reviewed the project backlog as a whole, then shipped two concrete "
     "improvements: the install script no longer overwrites user files "
     "silently (it backs them up first), and the dashboard now supports a "
     "separate read-only role for trusted browsers. Cleared two stale "
     "planning items along the way."),
]

WEEKLY = [
    ("2026-01-26", 6, 12,
     "Early dashboard work. Restructured the repo for easy installation, "
     "added session summaries to the handoff command with a dashboard view, "
     "and shipped UX improvements — clickable stat filters, grid-based "
     "arrow-key navigation, focus-trap fixes. Simplified the workflow "
     "commands by removing devlog and implementation-plan checks."),
    ("2026-02-23", 8, 12,
     "Major simplification week. Stripped the manual rating workflow from "
     "the dashboard and server, leaving the synthesizer pipeline to provide "
     "the analytical layer ratings were meant to enable. Slash commands "
     "were trimmed (readup from 39 to 16 lines, handoff from 59 to 30), "
     "code-quality fixes closed connection leaks and an N+1 query, and a "
     "Todos dashboard view was added that scrapes CLAUDE.md and memory "
     "files for Next Steps. A project-centric redesign with Preact + HTM "
     "and per-project cards capped the week."),
    ("2026-03-02", 6, 6,
     "Operational maturity week. Added a project detail page as the landing "
     "view, implemented token tracking and a session-stop hook with a "
     "peak-context indicator on dashboard cards, and replaced crontab with "
     "launchd for both the todos email and nightly synthesizer. Created a "
     "workflow installer for new-machine setup, made the launchd plists "
     "generic, and recovered the broken todos email after a rotated API "
     "key."),
    ("2026-03-09", 3, 9,
     "Built the processed knowledge layer — a backend-agnostic store "
     "abstraction with SQLite and Turso backends, weekly rollups, project "
     "snapshots, and review snapshots. Created a mobile PWA with Turso "
     "sync and an ask tab. Switched the review-email and synthesizer "
     "pipelines from JSON text parsing to structured-output tool use, "
     "eliminating fence-stripping fragility."),
    ("2026-03-16", 3, 4,
     "Built a bi-monthly report generator with a launchd schedule and "
     "switched all API calls to Opus. Enhanced the status line with token "
     "counts, colored context-percentage, duration, and timestamp. Added "
     "inline wireframe mockups with a parser, editor, and system-prompt "
     "integration."),
    ("2026-03-23", 4, 10,
     "Multi-machine and security week. Set up hostname tracking and the "
     "status-line script in the repo, deployed a cloud dashboard with "
     "cookie authentication and a Turso backend, and added a global "
     "PreToolUse hook that blocks access to environment files and other "
     "secrets. Audited and found three repos using a shared API key. Set "
     "up a 1Password dev-secrets vault with .env.tpl templates and "
     "propagated the practice across all projects."),
    ("2026-03-30", 1, 1,
     "Fixed the nightly review email after a 1Password migration broke it. "
     "The launchd plist still sourced a removed file; updated the template "
     "to call Python directly."),
    ("2026-04-06", 2, 2,
     "Added a blanket robots.txt disallow and a rewrite to block crawlers "
     "on the cloud dashboard after the CDN provider flagged AI-bot "
     "activity. Improved readup with last-session context and handoff with "
     "an uncommitted-changes warning. Evaluated an external terseness "
     "plugin and declined it in favor of CLAUDE.md instructions."),
    ("2026-04-13", 2, 3,
     "Audited the codebase for references to the deprecated sonnet-4 "
     "model, upgraded the ask command, and tracked the migration across "
     "five projects to completion. Fixed a /tmp race in handoff by "
     "parameterizing summary filenames with project and session ID, and "
     "added git pull --rebase to readup so remote changes land at session "
     "start."),
    ("2026-05-04", 1, 4,
     "Reviewed the project backlog as a whole, then shipped two concrete "
     "improvements: the install script no longer overwrites user files "
     "silently (it backs them up first), and the dashboard now supports a "
     "separate read-only role for trusted browsers. Cleared two stale "
     "planning items along the way."),
]


def main():
    store = get_store()
    for sid, started_at, summary in SESSIONS:
        store.upsert_public_session_summary(
            project=PROJECT, session_id=sid,
            started_at=started_at, public_summary=summary,
        )
    print(f"  public_session_summaries: {len(SESSIONS)} rows")

    for week_of, sessions, commits, summary in WEEKLY:
        store.upsert_public_weekly_rollup(
            project=PROJECT, week_of=week_of,
            public_summary=summary,
            session_count=sessions, commit_count=commits,
        )
    print(f"  public_weekly_rollups: {len(WEEKLY)} rows")


if __name__ == "__main__":
    main()
