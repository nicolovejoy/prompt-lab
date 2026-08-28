# Public refresh draft — prntd

<!-- generated: 2026-08-27 -->
<!-- last published week_of: 2026-06-01 -->
<!-- unpublished weeks found: 5 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prntd-2026-08-27.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-03-23

sessions: 3
commits: 0

### PRIVATE — source material, do not publish

> PRNTD went from idea to functional MVP in three days. The week started with a full spec and tech stack decision (Next.js 16, Turso, Stripe, Printful, Replicate, R2), moved into scaffolding and wiring up all service integrations on day two, and by day three the core design-to-checkout flow was working in production. A significant mid-week pivot swapped Flux for Ideogram v3 Turbo after Flux proved unreliable for text rendering on t-shirt designs, which also drove a UI simplification to a single full-width chat with inline images. Most debugging time went to production auth (a CORS issue from www→non-www redirects and a client-side redirect bug) and integration plumbing across six services.

### PUBLIC

Idea to functional MVP in three days: a full spec and stack decision on day one, all six service integrations wired on day two, and the core design-to-checkout flow live in production on day three. A mid-week pivot swapped the image-generation model after the first choice proved unreliable at rendering text on shirt designs — which also drove a simpler interface built around a single full-width chat with inline images.

## WEEK 2026-05-11

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> Despite only one active day, the week was highly productive for prntd. Two significant features shipped to production: multi-generator support and a Generate-readiness gate backed by a fast `assessReadiness` thin-check, marking meaningful progress on the generation pipeline. A Recraft API bug causing 422 errors on unsupported vector illustration types was identified and resolved. Beyond shipping, the day extended into design and strategy territory — a redesigned `/design` empty state was specced out around a centered composer with delayed suggestions, and early ideation began on a cross-domain user tracking and project expense monitoring system that may warrant its own standalone repository.

### PUBLIC

Two features shipped to production from a single working day: support for multiple image-generation backends, and a readiness gate that fast-checks whether a design is actually ready before generation runs. An upstream API bug producing errors on unsupported illustration types was also identified and resolved, and a redesigned empty state for the design page was specced.

## WEEK 2026-07-13

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light maintenance week for the prntd project, with only two active days focused on synchronization and verification rather than new development. The developer's primary concern was ensuring consistency across machines — a fix applied on the mini machine was verified, and the local repository was brought up to date via git fetch --prune to remove stale remote-tracking branches. The week also included an exploratory review of pull request statuses through a resync operation, suggesting the developer was taking stock of the project's current state before moving forward. No new commits were produced, indicating the week served more as a housekeeping and orientation effort than a productive coding sprint.

### PUBLIC

A housekeeping week: synchronized repository state across development machines, verified an earlier fix had landed everywhere, pruned stale branches, and took stock of open work before the next push of feature development.

## WEEK 2026-08-03

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light week for prntd, with a single active day dedicated entirely to architectural thinking rather than implementation. The focus was on resolving foundational data model questions — specifically how designs, products (e.g., T-shirts), and placements (front, back, etc.) relate to one another across both shop and product contexts. No code was committed, reflecting a deliberate step back to get the core structure right before building on top of it. Progress was cut short by a system interruption, leaving the design discussion unfinished and likely to carry into next week.

### PUBLIC

A deliberate step back from implementation to get the data model right: how designs, physical products, and print placements (front, back, and so on) relate to one another across shop and product contexts. No code — the point was to settle the foundations before building on top of them.

## WEEK 2026-08-17

sessions: 2
commits: 3

### PRIVATE — source material, do not publish

> Despite only a single active day, the week was dense with momentum on the prntd project. Direction B was formally locked in — the composition-first-class plan was written, reviewed, and fully approved by Nico the same day, giving the team a clear architectural path forward. Two agent PRs shipped to production in parallel: #164 addressed the front picker and swap flow while quietly resolving three latent cache and lookup bugs, and #165 landed the first slice of the composition migration with an additive schema, dual-write publishing, and 15 backfilled listings on prod. Alongside the forward progress, two environment risks were caught and contained — a stray .env.local pointing at prod (tracked in #166) and a smoke test failure that was root-caused as the known /d gap rather than a regression, leading to the decision to tackle both-sides-at-once preview in #167.

### PUBLIC

The composition-first data model was formally locked in, and two changes shipped to production in parallel: a reworked product picker and swap flow that also quietly resolved three latent caching bugs, and the first slice of the composition migration — an additive schema, dual-write publishing, and existing listings backfilled on production. Two environment-configuration risks were caught and contained the same day.
