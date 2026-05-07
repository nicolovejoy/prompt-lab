"""One-shot: write public-safe session summaries + weekly rollups for ibuild4you.

Summaries authored by the running Claude Code session (Opus 4.7), based on the
private session.summary text in prompt-history.db. No API calls — text below is
hand-curated, not generated at runtime.

Run once:
    .venv/bin/python scripts/backfill_public_ibuild4you.py
Then sync:
    .venv/bin/python sync_to_turso.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store  # noqa: E402

PROJECT = "ibuild4you"

SESSIONS = [
    (206, "2026-03-18 23:28:13",
     "Built the end-to-end conversation flow — landing page with interest form, "
     "invitation gate, project CRUD, and a chat with Claude streamed via SSE. Added "
     "agent pacing, brief generation, and a share flow with ownership transfer. "
     "First full deploy to production."),
    (210, "2026-03-20 02:00:00",
     "Redesigned the project page as a single hub: brief summary at the top, inline "
     "chat below in newest-first order. Added timestamps, sender labels, and improved "
     "placeholder copy."),
    (214, "2026-03-20 19:38:38",
     "Reframed the builder prep workflow into a more conversational flow with "
     "structured multi-field output (brief, opener, directives, mode). Removed the "
     "style-guide layer and renamed the welcome message into a 'session opener.'"),
    (219, "2026-03-22 21:22:17",
     "Extracted a reusable mockup editor, added JSON import for project creation, "
     "and fixed several share/approval bugs. Doubled the test count from 66 to 130. "
     "Added URL slugs with editable titles, fixed the multi-user turn indicator, and "
     "laid the groundwork for real-time sync."),
    (220, "2026-03-23 01:11:41",
     "Fixed mobile authentication by proxying Firebase auth through the app domain. "
     "Added a default welcome message and an About page reachable from login, landing, "
     "and the maker view. Surfaced the layout mockups panel inside the maker view."),
    (222, "2026-03-27 21:47:18",
     "Replaced the hard-coded admin email list with a flexible system-roles model on "
     "the user document. Updated all API routes and client pages, added a "
     "/api/users/me endpoint, and wired auto-backfill on sign-in. Validated in "
     "production."),
    (235, "2026-03-29 23:44:42",
     "Fixed several JSON-driven project-creation bugs and tightened invite and nudge "
     "copy. Built a role-aware turn indicator. Completed the names-cleanup phase: "
     "names live on the user record, makers can self-edit, and a first-visit prompt "
     "collects them. Added a re-nudge card for non-responders."),
    (250, "2026-04-01 18:00:16",
     "Added five-second message polling for multi-user sync. Wrote 28 new tests "
     "covering the system-prompt builder and chat route."),
    (253, "2026-04-02 01:54:46",
     "Extracted a shared SSE-streaming hook, expanded JSON import to cover brief and "
     "opener fields, and upgraded message polling to a true real-time Firestore "
     "subscription. Brought the test suite to 188 tests. Added a first-conversation "
     "setup banner."),
    (264, "2026-04-03 17:26:26",
     "Shipped a conversational posture model with six distinct postures, signal "
     "mapping, and quality gates. Made the agent identity configurable, surfaced "
     "open risks on briefs, exposed the turn indicator in the maker view, and "
     "replaced generic outbound templates with AI-generated messages. Two PRs merged."),
    (308, "2026-04-14 23:12:43",
     "Shipped a new interest-submissions admin page with its own admin menu entry. "
     "Separated notification recipients from the admin list. Debounced maker chat "
     "notifications via a five-minute inactivity cron job. Upgraded the agent and "
     "brief models to claude-sonnet-4-6 ahead of model deprecation."),
    (326, "2026-04-29 22:58:07",
     "Overhauled file uploads in three phases: better diagnostics on the upload "
     "endpoint, then presigned-URL direct-to-S3 to bypass the platform's 4.5 MB body "
     "limit (raising the cap to 25 MB), and finally routing PDFs and images directly "
     "to Claude as document and image content blocks with prompt caching. Discovered "
     "that production deploys had been silently rejected since mid-April due to a "
     "hosting-tier cron limit and upgraded the plan to fix it."),
]

WEEKLY = [
    ("2026-03-16", 4, 24,
     "Brought the platform to first end-to-end completeness — landing page, "
     "invitations, project CRUD, streamed Claude chat, brief generation, and a share "
     "flow with ownership transfer. Reframed the builder prep workflow into a more "
     "conversational format, then redesigned the project page as a single hub. "
     "Doubled the test count from 66 to 130 alongside several bug fixes."),
    ("2026-03-23", 3, 17,
     "Hardened the foundations. Fixed mobile authentication via a domain-proxied "
     "Firebase flow, added an About page across entry points, and replaced the "
     "hard-coded admin email list with a flexible system-roles model on the user "
     "document. Cleaned up names so they live on the user record with a first-visit "
     "prompt, and added a re-nudge card for non-responders."),
    ("2026-03-30", 3, 8,
     "Made the agent feel real-time and more sophisticated. Five-second polling "
     "matured into a Firestore subscription, the test suite grew to 188 tests, and a "
     "shared SSE-streaming hook came out as reusable infrastructure. Shipped a "
     "six-posture conversational model with quality gates, configurable agent "
     "identity, and AI-generated outbound messages replacing generic templates."),
    ("2026-04-13", 1, 4,
     "Added an interest-submissions admin page with its own menu entry, separated "
     "notification recipients from the admin list, and debounced maker chat "
     "notifications via a five-minute inactivity cron. Upgraded the agent and brief "
     "models to claude-sonnet-4-6 ahead of model deprecation."),
    ("2026-04-27", 1, 3,
     "Overhauled file uploads in three phases — better diagnostics, presigned-URL "
     "direct-to-S3 to bypass the 4.5 MB body cap (raising the limit to 25 MB), and "
     "routing PDFs and images directly to Claude as document and image content blocks "
     "with prompt caching. Discovered a silent deploy outage caused by a hosting-tier "
     "cron limit and resolved it by upgrading the plan."),
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
