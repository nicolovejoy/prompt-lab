# Public refresh draft — selected-projects

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-06-01 -->
<!-- unpublished weeks found: 4 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-selected-projects-2026-07-30.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-06-08

sessions: 3
commits: 10

### PRIVATE — source material, do not publish

> The week centered on shipping a detail-page redesign and then hardening the infrastructure around it. On Monday, the core work landed: a new `lib/og.ts` scraper pulls live Open Graph tags for each project, feeding a clickable preview card that sits in a two-column above-the-fold header alongside the title, status, and CTAs — collapsing gracefully on mobile. Native `<details>` elements replaced always-visible sections for About, Evolution, and Notes, and a copy pass tightened the last project writeup. Tuesday was a cleanup and verification pass — all six project sites were audited for `og:image` coverage, with musicforge and lojong confirmed shipping theirs, and ibuild4you flagged as the remaining gap. CI infrastructure also got a meaningful upgrade: a GitHub Actions workflow now runs content checks on every push and PR, and the pre-push hook was trimmed to check-only since CI and Vercel both handle builds. By Wednesday, ibuild4you's OG image was confirmed live, closing out the last open follow-up and bringing all six project preview cards to full health. A stray diagnosis surfaced around musicforge's missing calendar data — traced to a private repo and public-only token — but was deliberately deferred. Branch hygiene and handoff entries were also squared away.

### PUBLIC

Project detail pages were rebuilt around a live preview card. Each project's own site is read for the preview image and title it already publishes, and that becomes a clickable card in a two-column header beside the status and links, collapsing to a single column on a phone. Long sections — background, evolution, notes — became collapsible instead of always open, so a page now opens at a length someone will actually read.

A pass across every project site confirmed each one genuinely serves a preview image, which is the thing that makes the cards work at all. Content checks also began running automatically on every change, so a broken page is caught before it ships rather than after someone notices.

## WEEK 2026-06-29

sessions: 2
commits: 2

### PRIVATE — source material, do not publish

> This was a focused, high-impact week centered entirely on production hardening and environment isolation for the Piano House Project. The primary effort was closing out auth coverage — verifying magic-link sign-in end-to-end on production for both owner and non-owner flows using Playwright, with test users cleaned up after each run. With auth validated, attention shifted to cleanly separating the three environment tiers: local dev now runs against a gitignored file-based SQLite DB, preview deployments got their own dedicated Turso database, and production Turso credentials were re-scoped and re-tokened in isolation. A latent bug was also caught and fixed in the process — preview magic links had been silently broken due to AUTH_FROM_EMAIL being pinned to a deleted branch. The week closed with a formal environments hardening roadmap committed to docs/environments.md and a verified live deploy.

### PUBLIC

A hardening week with nothing new to show for it. Sign-in was verified end to end against the live site for both the owner's path and an ordinary visitor's, with test accounts cleaned up afterward. With that confirmed, the three environments were properly separated: local development moved to its own throwaway database, preview deployments got a dedicated one, and the production credentials were re-scoped so they exist in exactly one place.

The separation paid for itself immediately by surfacing a bug nobody had noticed — sign-in links on preview deployments had been quietly broken, pointing at an address that no longer existed. The week ended with the environment model written down rather than remembered.

## WEEK 2026-07-13

sessions: 1
commits: 3

### PRIVATE — source material, do not publish

> A single dense session reframed the site and gave it its first safety net. The week opened by shipping split-recording's design-family alignment — a shared token layer, dark mode over a hueless neutral ramp, focus states, and a mono micro-label utility — so pianohouseproject.org and the recordings catalog read as siblings. Two dark-mode leaks slipped into production behind that work and were caught, fixed, and then pinned by tests. The larger move was structural: the site stopped being a flat feed of eight repos and became a multidisciplinary body of work grouped into Music, Art, Products, and Tools, with the home page rebuilt as a four-quadrant grid. Underneath, weekly rollups were demoted from precondition to optional enrichment, which surfaced two projects that had been silently invisible since they shipped.

### PUBLIC

Two changes, one visible and one structural. The recordings catalog and the main site were brought onto a shared design foundation — common tokens, a dark mode built over a neutral grey ramp, consistent focus states — so the two read as siblings rather than as neighbours who happen to share a street. Two dark-mode defects slipped out behind that work; both were fixed and then pinned with tests so they cannot quietly return.

The structural change mattered more. The site stopped being a flat feed of repositories and became a body of work grouped into music, art, products, and tools, with the home page rebuilt around those four. Loosening one requirement along the way revealed two projects that had been invisible since the day they shipped.

## WEEK 2026-07-20

sessions: 1
commits: 7

### PRIVATE — source material, do not publish

> The visual-refresh arc closed: issue #7 shipped end-to-end through live mockup iteration (variants A through E), landing the recordings-catalog editorial system — ledger feed rows, linear detail headers, mono micro-labels, site-wide 2px radii remapped once at the token layer. The same day, the split-pane live preview (issue #12) went from idea to merged: opted-in project pages embed their live site at two-thirds width beside the detail content. Supporting work: #5 groundwork (curated cardImage beats the OG scrape, asset conventions and a shot list), a docs tidy that archived the roadmap's history, a dead-code sweep confirming the repo lean, and direct deep-links from home quadrant names. Issue #19 filed with a precise diagnosis of nav latency: pages are cookie-dynamic and the client router caches them for zero seconds, while all data layers are already cached server-side.

### PUBLIC

The visual refresh closed out, iterated against live mockups rather than static comps: an editorial system for the recordings catalog with ledger-style feed rows, linear detail headers, and small monospaced labels, plus one change at the token layer that softened every corner on the site at once.

The same day brought a split-pane live preview — a project page can now embed the running site itself alongside the writeup, at two-thirds width, so a reader sees the thing rather than a description of it. Supporting work moved preview images from automatic scraping to curated art, archived the older roadmap, and confirmed the codebase carries no dead weight. Navigation slowness was diagnosed precisely enough to fix later: the pages vary per visitor, so the browser never caches them, even though everything underneath already is.
