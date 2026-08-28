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

> Explored the codebase and documentation, and prepared setlist data formatted for input — groundwork for an upcoming import feature. Committed no code.

### PUBLIC

Explored the codebase and prepared setlist data in the format an upcoming import feature will consume. Research and preparation only — no code shipped.

## WEEK 2026-03-23

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> Documented the existing build-timestamp display pattern in the nav bar as a reference guide for replicating it in another project. No code changes.

### PUBLIC

Documented the app's build-timestamp display pattern as a reusable reference for sibling projects, so they can replicate the convention instead of reinventing it. No code changes.

## WEEK 2026-08-03

sessions: 1
commits: 2

### PRIVATE — source material, do not publish

> Fixed a subtle but far-reaching bug in the LilyPond-to-barstock chord parser: the chord-quality table's silent prefix-scan fallback had been misclassifying major-seventh chords as minor, and a full corpus sweep found the damage ran deeper than first reported — 828 chords across 216 song files. The week also included a documentation restructure and routine branch hygiene.

### PUBLIC

Fixed a silent fallback in the chord parser that had been misclassifying major-seventh chords as minor. The week also included a documentation restructure and branch cleanup.

## WEEK 2026-08-10

sessions: 16
commits: 83

### PRIVATE — source material, do not publish

> Three arcs. Hardened the note-writing stack — fixed a silent write-drop, made setlist edits transactional, gave held-failure states warning tints — and the release pipeline saw its first fully command-line upload. Chart ingestion fidelity jumped from 15% to 98% exact alignment via real font metrics and character-level anchoring; root-caused a production crash affecting 97 songs to a payload-completeness bug; fixed a bar-line anchoring bug, and syllable snapping cut mid-word caret errors to 10%. Converted the full corpus and delivered it for review. Found scroll-follow structurally broken at chart ends and rebuilt it on a sounder geometric model by week's end.

### PUBLIC

Hardened the note-writing stack — fixed silent write drops, made setlist edits transactional — and the release pipeline saw its first command-line upload. Chart ingestion fidelity jumped from 15% to 98% exact alignment using real font metrics and character-level anchoring. Root-caused a production issue affecting 97 songs to a payload-completeness bug, converted the full 339-chart corpus, and delivered it for collaborator review. Found scroll-follow structurally broken at chart ends and rebuilt it on a sounder geometric model by week's end.

## WEEK 2026-08-17

sessions: 16
commits: 44

### PRIVATE — source material, do not publish

> The week scroll-follow finally worked on real devices: root-caused and fixed a silent-broadcast bug on the leader side under review, then root-caused and fixed the follower's inert geometry and re-smoked it clean. Re-planned readiness for an upcoming in-person deployment web-first against verified code, and distilled priorities: offline hardening and easy sharing ahead of new format imports, plus a readability spec; parked a couple of lower-priority items for after. The week closed by fixing a parser correctness bug in the core library and shipping a requested feature on web.

### PUBLIC

Scroll-follow finally worked on real devices, verified in live smoke tests. Re-planned priorities around offline hardening and easy sharing ahead of new format imports, and fixed a parser correctness bug in the core library. A listen-from-the-chart feature also shipped on web.
