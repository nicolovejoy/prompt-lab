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

> PRNTD went from idea to functional MVP in three days. The week started with a full spec and stack decision (Next.js 16, Turso, Stripe, Printful, Replicate, R2), moved into scaffolding and wiring up all service integrations on day two, and by day three the core design-to-checkout flow was working in production. A mid-week pivot swapped Flux for Ideogram v3 Turbo after Flux proved unreliable at rendering text on t-shirt designs, which also drove a UI simplification to a single full-width chat with inline images.

### PUBLIC

Idea to functional MVP in three days: nailed down a full spec and stack decision on day one, wired six service integrations on day two, and got the core design-to-checkout flow live in production on day three. A mid-week pivot swapped the image-generation model after the first choice proved unreliable at rendering text on shirt designs, which also led to building a simpler interface around a single full-width chat with inline images.

## WEEK 2026-05-11

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> Shipped two features to production: multi-generator support and a Generate-readiness gate backed by a fast readiness check. Identified and resolved an upstream API bug causing errors on unsupported vector illustration types. Also specced a redesigned empty state for the design page, built around a centered composer with delayed suggestions.

### PUBLIC

Shipped two features to production: support for multiple image-generation backends, and a readiness gate that fast-checks whether a design is actually ready before generation runs. Also identified and resolved an upstream API bug producing errors on unsupported illustration types, and specced a redesigned empty state for the design page.

## WEEK 2026-07-13

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> A maintenance week focused on synchronization and verification rather than new development: verified a fix across machines, brought the local repository up to date and pruned stale remote-tracking branches, and reviewed pull-request statuses to take stock of the project's current state. No new commits.

### PUBLIC

Synchronized repository state across development machines, verified an earlier fix had landed everywhere, pruned stale branches, and took stock of open work before the next push of feature development.

## WEEK 2026-08-03

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> A day of architectural thinking rather than implementation, resolving foundational data-model questions — how designs, products (e.g., T-shirts), and placements (front, back, etc.) relate to one another across both shop and product contexts. No code committed; the goal was getting the core structure right before building on top of it.

### PUBLIC

Data model development: how designs, physical products, and print placements (front, back, and so on) relate to one another across shop and product contexts. No code — the point was to settle the foundations before building on top of them.

## WEEK 2026-08-17

sessions: 2
commits: 3

### PRIVATE — source material, do not publish

> Formally locked in the composition-first data model — wrote, reviewed, and approved the plan the same day, giving a clear architectural path forward. Shipped two changes to production in parallel: a reworked front picker and swap flow that also quietly resolved three latent cache and lookup bugs, and the first slice of the composition migration — an additive schema, dual-write publishing, and 15 backfilled listings on production. Caught and contained two environment-configuration risks the same day.

### PUBLIC

Selected a composition-first data model. Shipped two changes to production in parallel: a reworked product picker and swap flow that also quietly resolved three latent caching bugs, and the first slice of the composition migration — an additive schema, dual-write publishing, and backfilled existing listings on production.
