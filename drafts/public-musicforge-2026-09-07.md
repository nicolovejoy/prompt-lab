# Public refresh draft — musicforge

<!-- generated: 2026-09-07 -->
<!-- last published week_of: 2026-08-17 -->
<!-- unpublished weeks found: 2 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-musicforge-2026-09-07.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-08-24

sessions: 22
commits: 83

### PRIVATE — source material, do not publish

> Camp week: everything funneled toward SAM Camp on Sunday. Early week shipped the last pre-freeze features (follower song title, Web Share, setlist filter bar, duplex join cards) and root-caused a prod outage as a compile storm rather than a code bug, spawning the mini-based prewarm rig. Mid-week closed both landscape bugs via SDD (web follower two-page spread, iOS barstock edge-to-edge) and shipped Builds 77-80 with the new flame icon. Late week closed the iPad app's telemetry blindness (#354 Phase 1, Build 81, verified with a real lead/follow pair in prod) and fixed the CLAUDE.md bloat by rotating months of session log to an archive. Camp eve held the freeze deliberately: a code-verified resync, a camp-day runbook, and a ship-nothing ruling on #352.

### PUBLIC

Shipped the last features before a code freeze for SAM Camp: the follower view shows the song title, a setlist filter bar, Web Share for sessions, and duplex join cards. Root-caused a production outage to a Cloud Build compile storm rather than app code and stood up a pre-warm rig on the Mac mini to prevent it. Closed both landscape bugs, the web follower two-page spread and the iOS barstock edge-to-edge layout, and shipped iOS Builds 77 through 80 with the new flame icon. Build 81 fixed the iPad app's missing telemetry, verified with a real lead-and-follow pair in production. Rotated months of session log out of the project notes into an archive. Held the freeze on camp eve with a code-verified resync and a camp-day runbook.

## WEEK 2026-08-31

sessions: 14
commits: 172

### PRIVATE — source material, do not publish

> The week opened mid-camp with cloud agents shipping multi-leader Groove Sync on both platforms (Build 82) while Nico played, then the follower-latency and dashboard-error work moved between laptop, mini, and cloud as connectivity allowed. Once camp ended the structural freeze lifted: the join badge replaced the blocking modal (Builds 84-85), the key picker shipped on both platforms (Build 86), the key-canonicalization arc began, Loop feedback landed on web, and Settings was regrouped into six rows (Builds 87-88). A resync closed 30 stale issues and the first automated firestore.rules tests appeared alongside the discovery of #428/#429. The week closed with an unattended overnight SDD run that shipped the entire band-ownership plan across five PRs, deployed rules and backend, and uploaded Build 89.

### PUBLIC

Multi-leader Groove Sync shipped on iOS and web during camp itself as Build 82. After camp the freeze lifted: a join badge replaced the blocking modal in Builds 84 and 85, the key picker shipped on both platforms in Build 86, Loop feedback landed on web, and Settings was regrouped into six rows in Builds 87 and 88. A resync closed 30 stale issues and the first automated Firestore security-rules tests appeared. An unattended overnight run shipped band ownership across five pull requests, deployed the Firestore rules and backend, and uploaded Build 89. Next: finish canonicalising song keys across both platforms.