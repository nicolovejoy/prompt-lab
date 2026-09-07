# Public refresh draft — prntd

<!-- generated: 2026-09-07 -->
<!-- last published week_of: 2026-08-17 -->
<!-- unpublished weeks found: 2 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prntd-2026-09-07.md --apply

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

sessions: 1
commits: 19

### PRIVATE — source material, do not publish

> This was a focused one-day sprint that closed out two tracks of work cleanly. The week opened by formally verifying the #168/#170 smoke against production data — confirming zero app errors, correct per-operation cost routing, and full alpha integrity on both the v4 generate and /v1/edit paths, putting the #153 alpha-loss bug definitively to rest. With that validation in hand, attention shifted entirely to slice 3, where four open architectural questions were answered before any code was written. From there, the entire durable-generation-job slice was built in a single subagent-driven session: 7 tasks, 18 commits, landing as PR #171. Generation is now a first-class durable workflow — persisted as an image_generation job row, resolved in an after() continuation, guarded by a concurrency cap of 3, and supported by a lazy stale sweep on reads, a cron-driven R2 reclaim, and a polling UI.

### PUBLIC

Verified against production data that the alpha-channel loss in generated images is fixed on both the v4 generate and edit paths, with zero app errors and per-operation costs routed correctly. Then rebuilt generation as a durable job in one session of 7 tasks and 18 commits: each request persists as an image_generation row, resolves in a Next.js after() continuation, is capped at 3 concurrent runs, is swept when stale on read, and has its Cloudflare R2 storage reclaimed by a cron, with the UI polling for completion.

## WEEK 2026-08-31

sessions: 4
commits: 32

### PRIVATE — source material, do not publish

> The week turned the Studio and composition work into shipped product, then reset the product's look. Early in the week the autonomous SDD batch closed out the Studio plan and composition slices 2-4 (#180-#186), followed by a design pass in which Nico chose the Paper look (PaperB, light only) and nav model A, retired organizer storefronts, and pushed bulk delete into the UI (#192) rather than scripts. Mid-week a cloud/local SDD batch shipped the optimistic pending cell (#196), the house confirm sheet (#200), the image-page lightbox (#199), and both-sides preview (#198) after a high-effort review with an SDD fix run; five prod smokes produced five new issues. The week closed with an unattended SDD night that merged four of those smoke-round fixes (#205, #203, #197, #204) and the whole Paper slice 1 (#213), every one prod-smoke green, with the Opus whole-branch reviews repeatedly catching cross-file defects the per-task reviews structurally could not see.

### PUBLIC

Studio and composition slices 2 through 4 shipped. Chose the Paper look, light only, and a single-nav model; retired organizer storefronts; and moved bulk delete from scripts into the UI. Mid-week shipped an optimistic pending cell for in-flight generations, the house confirm sheet, a lightbox on the image page, and a both-sides print preview. Five production smoke tests produced five new issues; an unattended overnight run merged four of the fixes and the whole first Paper slice, every one smoke-tested green in production. Next: the remaining smoke fix and the rest of the Paper redesign.