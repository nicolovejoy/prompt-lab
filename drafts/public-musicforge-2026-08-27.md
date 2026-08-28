# Public refresh draft — musicforge

<!-- generated: 2026-08-27 -->
<!-- last published week_of: 2026-06-01 -->
<!-- unpublished weeks found: 5 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-musicforge-2026-08-27.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-03-09

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> A very light week on musicforge with only one active day. The developer spent time exploring the codebase and documentation, focusing on preparing setlist data formatted for input — likely groundwork for an upcoming import or data ingestion feature. No code was committed, suggesting this was purely a research and preparation phase.

### PUBLIC

A groundwork week: explored the codebase and prepared setlist data in the format an upcoming import feature will consume. Research and preparation only — no code shipped.

## WEEK 2026-03-23

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> A light week on musicforge with only one active day. The developer spent time documenting the existing build timestamp display pattern in the nav bar, creating a reference guide for replicating this approach in another Vercel project. No code changes were made — the focus was purely on knowledge sharing and cross-project documentation.

### PUBLIC

A knowledge-sharing week: documented the app's build-timestamp display pattern as a reusable reference for sibling projects, so the convention can be replicated instead of reinvented. No code changes.

## WEEK 2026-08-03

sessions: 1
commits: 2

### PRIVATE — source material, do not publish

> Work this week was limited to a single airport session on a non-dev laptop, keeping iOS work fully blocked. The session's impact was outsized despite the constraints: a subtle but far-reaching bug in the LilyPond-to-barstock chord parser was tracked down and fixed. The chord-quality table's silent prefix-scan fallback had been misclassifying major seventh chords as minor, and a full corpus sweep revealed the damage ran much deeper than originally reported — 828 chords across 216 song files. Beyond the fix itself, the week included a documentation restructure after stakeholder feedback and routine branch hygiene.

### PUBLIC

One constrained travel session produced an outsized fix: a silent fallback in the chord parser had been misclassifying major-seventh chords as minor, and a sweep of the full corpus showed the damage ran far deeper than first reported — 828 chords across 216 songs, all corrected. The week also included a documentation restructure and branch cleanup.

## WEEK 2026-08-10

sessions: 16
commits: 83

### PRIVATE — source material, do not publish

> Three arcs this week. Early week: the note-writing stack was hardened (silent write-drop fix, transactional setlist mutations via a shared mutateItems chokepoint, held-failure warning tints) and Build 71 became the first fully-CLI TestFlight upload. Mid-week: chart ingestion fidelity jumped from 15% to 98% exact alignment via real font metrics and character-resolution anchoring, a live prod crash on 97 songs was root-caused to a wire type lying about payload completeness, and Eric's review found a bar-line anchoring bug whose fix plus syllable snapping dropped mid-word carets to 10%; the whole 339-document corpus was then converted and handed to Eric as a PR on his own repo. Late week: Build 71 smoke day surfaced that Groove Sync scroll-follow was structurally broken at chart ends, leading to a live design session and a full SDD-fleet rebuild on source rows with center-anchor mapping and geometric boundaries, which cleared review and its fix wave by Sunday night. A deep resync also corrected the recorded backlog (88 open, not 63) and Eric's answers retired two whole workstreams (other three books dead, .docx format being abandoned).

### PUBLIC

A very high-output week in three arcs. The note-writing stack was hardened — silent write drops fixed, setlist edits made transactional — and the first fully command-line TestFlight upload shipped. Chart ingestion fidelity jumped from 15% to 98% exact alignment by using real font metrics and character-level anchoring, a production crash affecting 97 songs was root-caused to a payload-completeness bug, and the full 339-chart corpus was converted and delivered for collaborator review. Synchronized scroll-follow was found structurally broken at chart ends and rebuilt on a sounder geometric model by week's end.

## WEEK 2026-08-17

sessions: 16
commits: 44

### PRIVATE — source material, do not publish

> Camp-week-minus-one, and the week Groove Sync scroll-follow finally worked on real devices: the iOS leader's silent broadcast was root-caused and fixed under an ultra review (PR #321, Build 74), then the iOS follower's inert geometry was root-caused and fixed (PR #326, Build 75) and re-smoked clean with Eric by phone. Camp readiness was re-planned web-first against verified code, the /camp page gained a signed-in variant, the camp book pivoted to the Standards Book, and a red-CI e2e was corrected. Eric and Nico distilled explicit camp priorities (offline hardening and easy sharing over DOCX import) plus a barstock-readability spec; Country Book ingestion and the BarStock adjacency format change were parked post-camp. The week closed with a live parser correctness bug fixed in barstock-core v0.1.1, Eric's Listen-button ask shipped on web, and book-bound band notes built on a branch after finding the projector already preserves them.

### PUBLIC

The week synchronized scroll-follow finally worked on real devices: a silent-broadcast bug on the leader side and inert follower geometry were each root-caused and fixed across two successive builds, then verified in live smoke tests. With a real-world deployment approaching, priorities were re-planned against verified code — offline hardening and easy sharing ahead of new format imports — and a parser correctness bug was fixed in the core library. A listen-from-the-chart feature also shipped on web.
