"""One-shot: write public-safe session summaries + weekly rollups for the
small-history projects: am-i-an-ai, showcase, and selected-projects (which
includes the historical pianohouse rows under the canonical name).

Summaries authored by the running Claude Code session (Opus 4.7), based on
private session.summary text in prompt-history.db. No API calls.

Note: pianohouse-tagged sessions are written under project='selected-projects'
to match the post-rename canonical key. Consumer side should filter on
'selected-projects', not 'pianohouse'.

Run once:
    .venv/bin/python scripts/backfill_public_smallset.py
Then sync:
    .venv/bin/python sync_to_turso.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store  # noqa: E402

# (project, session_id, started_at, public_summary)
SESSIONS = [
    # am-i-an-ai (lojong on the site)
    ("am-i-an-ai", 213, "2026-03-20 16:46:54",
     "Built a batch content pipeline that turns slogans into poems — LLM query "
     "generation, web search, content extraction, and a resonance scoring step "
     "before final assembly. Generated 35 poem drafts from 59 slogans, then "
     "polished the site with a parser fix, an updated About page, keyboard "
     "navigation, and Open Graph preview cards."),

    # showcase (rocksculpture on the site)
    ("showcase", 107, "2026-02-26 20:33:49",
     "Migrated DNS to a new provider after a registrar change, restoring records "
     "for the showcase domain and its sibling subdomains. Verified end-to-end "
     "resolution against the hosting platform."),

    # selected-projects (formerly pianohouse — historical rows live under
    # project='pianohouse' in sessions table, written here under the canonical name)
    ("selected-projects", 327, "2026-04-28 19:05:53",
     "Bootstrapped the portfolio site from an initial scaffold to a live "
     "deployment. Wrote real project copy, migrated content into MDX, wired the "
     "connect form to a database and transactional email, and added typography, "
     "favicon, Open Graph metadata, status badges, and the hero photograph."),
    ("selected-projects", 330, "2026-04-30 08:18:00",
     "Consolidated all editable copy into a single content directory, swapped to "
     "a sunset hero image, and built a hero-tuning tool with fade sliders and a "
     "color eyedropper. Did a lowercase brand pass throughout, made typography "
     "bolder in the navigation and Open Graph cards, added a content validator "
     "with a pre-push gate, and tidied four of the five project pages. "
     "Configured a custom email domain on the DNS provider."),
    ("selected-projects", 350, "2026-05-06 15:19:41",
     "Added a sixth featured project. Shipped the consumer side of the Evolution "
     "section, which reads session-by-session and weekly progress from a shared "
     "knowledge database (with a graceful no-op until producer rows land, behind "
     "a 24-hour cache). Renamed the repository to better reflect what the site "
     "is — a curated set of selected projects."),
    ("selected-projects", 354, "2026-05-07 01:29:54",
     "Wired the Evolution section to its dedicated knowledge database via "
     "separate environment variables, isolating it from the connect-form "
     "database. Verified the connection live on production after a fresh build."),
]

# (project, week_of, session_count, commit_count, public_summary)
WEEKLY = [
    ("am-i-an-ai", "2026-03-16", 1, 5,
     "Built a batch content pipeline that turns slogans into poems through LLM "
     "query generation, web search, content extraction, and a resonance scoring "
     "step. Generated 35 poem drafts from 59 slogans, then polished the site "
     "with a parser fix, an updated About page, keyboard navigation, and Open "
     "Graph cards."),
    ("showcase", "2026-02-23", 1, 0,
     "Migrated DNS for the showcase domain after a registrar change and verified "
     "subdomain resolution end-to-end against the hosting platform."),
    ("selected-projects", "2026-04-27", 2, 20,
     "Bootstrapped the portfolio site from a fresh scaffold to a live deployment "
     "with project copy, MDX content, a connect form backed by a database and "
     "transactional email, custom typography, and a sunset hero with a tuning "
     "tool. Consolidated editable copy into a single content directory, added a "
     "content validator with a pre-push gate, and configured a custom email "
     "domain."),
    ("selected-projects", "2026-05-04", 2, 7,
     "Added a sixth featured project and shipped the consumer side of the "
     "Evolution section, which surfaces session-by-session and weekly progress "
     "for each project from a shared knowledge database. Renamed the repository "
     "to selected-projects to better describe what it is, and wired the "
     "Evolution section to a dedicated knowledge-database connection."),
]


def main():
    store = get_store()
    for project, sid, started_at, summary in SESSIONS:
        store.upsert_public_session_summary(
            project=project, session_id=sid,
            started_at=started_at, public_summary=summary,
        )
    print(f"  public_session_summaries: {len(SESSIONS)} rows")

    for project, week_of, sessions, commits, summary in WEEKLY:
        store.upsert_public_weekly_rollup(
            project=project, week_of=week_of,
            public_summary=summary,
            session_count=sessions, commit_count=commits,
        )
    print(f"  public_weekly_rollups: {len(WEEKLY)} rows")


if __name__ == "__main__":
    main()
