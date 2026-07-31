# Public refresh draft — showcase

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-02-23 -->
<!-- unpublished weeks found: 1 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-showcase-2026-07-30.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-05-18

sessions: 2
commits: 6

### PRIVATE — source material, do not publish

> After returning to the showcase codebase after a break, the week was spent on two high-impact fronts: deepening the lightbox experience and laying the groundwork for multi-tenant deployments. The lightbox received a full polish pass — fade-in placeholders, neighbor preloading, swipe support, captions, an X/Y counter, and disabled boundaries all came together to make photo browsing feel significantly more refined. In parallel, the codebase was parameterized via VITE_COLLECTION_ID, enabling sibling Vercel deployments from a single repo — a clean architectural decision that avoids forking and makes onboarding new showcases (like Max's) straightforward. The week closed with an owner-only photo-hiding feature, complete with a POST /api/hide endpoint, Firestore-backed hiddenAssetIds, live onSnapshot subscriptions, and editor-only UI — giving curators real control without touching the codebase. A static-manifest → Firestore-read migration was identified and deliberately deferred.

### PUBLIC

A polish pass on the photo lightbox: fade-in placeholders while images load, preloading of the neighbouring photos so navigation feels instant, swipe support, captions, a position counter, and proper handling of the first and last image. Browsing went from functional to considered.

The codebase was also parameterized so one repository can serve several independent showcases, each with its own collection of work. Standing up a new showcase became a configuration step rather than a fork — the difference between a project that scales to more people and one that quietly accumulates copies.

The week closed with curator-controlled photo hiding, letting whoever owns a collection pull an image from public view without editing code or waiting on a deploy.
