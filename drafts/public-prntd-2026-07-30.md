# Public refresh draft — prntd

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-06-08 -->
<!-- unpublished weeks found: 8 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prntd-2026-07-30.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-04-20

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> Pre-collaboration setup week. Single working day produced a hardening pass that made it possible for someone other than Nico to safely ship code: PRINTFUL_DRY_RUN env flag (with tests) so local Stripe test-mode orders skip real fulfillment, docs/e2e-testing.md as a runbook, ADMIN_EMAIL moved out of source. Validated dry-run end-to-end with a $19.43 Stripe test order. Made the repo public and filed Max's first PR target (issue #1, email subject lines). Also produced docs/current-state.md confirming that group-store, marketplace, and cause-routing surfaces are intent-only — no code yet — which informed the next-phase planning.

### PUBLIC

Groundwork for letting someone other than the author ship code safely. A dry-run mode was added so local test orders exercise the entire purchase path without ever reaching the fulfillment partner, backed by tests and a written runbook, and the last hard-coded administrative address moved out of the source.

The repository was opened up, with a first well-scoped issue prepared for a new contributor to land. A survey of the codebase also confirmed something useful and slightly deflating: several planned surfaces existed only as intent, with no code behind them — exactly the sort of thing worth establishing before planning a phase around them.

## WEEK 2026-06-15

sessions: 1
commits: 6

### PRIVATE — source material, do not publish

> This week on prntd, work centered on the organizer pivot branch, delivering meaningful progress across two distinct feature areas despite only two active days. The mobile chat UX bug — where a numbered list looked like buttons but required typing — was fully resolved by replacing it with tappable QuickReply chips (≥44px) that submit directly as the user's turn, with the composer relaid out phone-first and verified on both desktop and Pixel-7. In parallel, the foundation of an organizer back office took shape as a /dashboard route with shop creation, link copying, and a publish toggle, all gated behind a STORES_ENABLED flag and backed by a DB-injected store service with 13 integration tests against a real database. The week was punctuated by an accidental .env.local wipe via a misused op CLI command, requiring manual secret recovery mid-session, and a handful of open questions were deliberately parked and documented for the next session rather than rushed.

### PUBLIC

Two threads. A mobile chat defect — a numbered list that looked tappable but actually required typing the number — was replaced with real chips, sized for thumbs, submitting directly as the person's turn. The composer was relaid out phone-first and checked on both a desktop and an actual handset.

In parallel, the beginnings of an organizer back office: a dashboard with shop creation, link copying, and a publish toggle, kept behind a feature flag and backed by a service layer whose integration tests run against a real database rather than a mock. A handful of open questions were deliberately parked and written down rather than answered in a hurry.

## WEEK 2026-06-22

sessions: 2
commits: 15

### PRIVATE — source material, do not publish

> This was a focused 3-day week centered on the organizer pivot, with a side of infrastructure hardening. The week kicked off by shipping AI-scraper avoidance — a deliberate policy decision to stay SEO-indexable while blocking LLM training crawlers — verified live on prntd.org. The bulk of effort went into Phase 2, slice 2 of the organizer pivot on the docs/organizer-pivot branch: the product-compose flow was designed and built end-to-end, starting with settling the core economics (organizer-set pricing, a fixed $1 PRNTD ops fee, and a guaranteed $5 org floor). That foundation was implemented TDD with pure proceeds helpers, a COGS proxy, a validity adapter, service layer updates, server actions, and a live client-side UI. The week closed with debugging and resync work — tracking down a misconfigured local environment (preview Turso branch instead of dev) that caused greyed-out dashboard buttons — and producing a clean, prioritized next-work sequence to carry into the following week.

### PUBLIC

The week opened with a deliberate policy choice: stay indexable by search engines while blocking crawlers that harvest text to train models. Those are two different things that often get conflated, and the site now treats them differently on purpose.

The bulk of the week went into the product-compose flow, designed and built end to end. The economics were settled first — who sets the price, what the platform takes, and a guaranteed floor for the organizing group — because building the interface before answering that would have meant building it twice. Implementation followed test-first, with the proceeds arithmetic isolated as pure functions. The week closed by chasing down a local environment pointed at the wrong database, which had been quietly greying out dashboard controls.

## WEEK 2026-06-29

sessions: 1
commits: 4

### PRIVATE — source material, do not publish

> One working day this week, focused on paying down fulfillment-path debt. A four-agent code review (idempotency, architecture, test coverage, test quality) found live bugs in the admin Printful retry and Stripe-session mapping and filed the #37-#41 backlog. WP1 shipped as PR #42: a single submitOrderFulfillment tail shared by the Stripe webhook and admin retry, a shared toStripeSessionData translation, and emails plus admin order detail reading resolveOrderLines. The drifted mocked-db webhook test suite was retired for the real-DB harness, and STORES_ENABLED was rescoped to all Preview branches after its branch-scoping broke PR e2e.

### PUBLIC

A day spent paying down debt on the fulfillment path. A four-way code review — idempotency, architecture, test coverage, test quality — turned up live bugs in both the administrative retry and the mapping between payment sessions and orders, and produced a concrete backlog rather than a vague sense of unease.

The fix consolidated order submission into a single shared tail used by both the automatic path and the manual retry, so the two can no longer quietly drift apart. Emails and the order detail view moved onto one shared resolver. A drifted suite of mocked-database tests was retired in favour of a harness that runs against the real thing, on the theory that a test agreeing with a mock proves very little.

## WEEK 2026-07-06

sessions: 1
commits: 2

### PRIVATE — source material, do not publish

> This week on prntd, the team focused entirely on hardening the order fulfillment pipeline against external service failures. The centerpiece was the addition of a daily cron job that automatically retries paid-but-unsubmitted orders — a direct fix for the scenario where a Printful outage during a Stripe webhook would silently strand an order. Alongside this, the fulfillment flow was restructured so that AI-generated order naming no longer blocks the webhook path, with an 8-second timeout guard ensuring a hung LLM call can't push processing past Stripe's deadline. By end of week, the cron was merged and manually triggered, though an absence of logs raised an open question about observability that will need follow-up.

### PUBLIC

A week entirely about hardening order fulfillment against someone else's outage. The centrepiece is a daily job that automatically retries orders that were paid for but never submitted — precisely the scenario where the fulfillment partner is unreachable at the moment payment completes and an order strands with nobody noticing.

The flow was also restructured so that generating a readable order name no longer sits in the critical path, with a timeout guard ensuring a hung language-model call can't push processing past the payment provider's deadline. The job merged and ran, though the absence of any logs raised a fair question: how would we know if it stopped working?

## WEEK 2026-07-13

sessions: 2
commits: 5

### PRIVATE — source material, do not publish

> Quiet week until Saturday. Mid-week housekeeping: light resync (no drift), deleted three fully-merged remote branches, and confirmed the #39 retry-fulfillment cron fires cleanly (the empty Vercel dashboard was a 12h time-window artifact). Saturday was the big push: a three-agent audit of the money path, generation loop, and roadmap surfaced that canceled orders were never refunded on the card, the COGS reversal type was never emitted, and concurrent Generates could permanently overwrite each other's R2 image. Four subagent-authored PRs (#51-#54) shipped and merged the same day: test-debt batch (#41 closed), atomic generation-number reservation (#40 closed), admin-clicked refunds with stranded-submission recovery, and Phase 1b (every checkout writes order_item, removing #38's caveat). An adversarial review agent caught that WP1's headline COGS-reversal fix was inert before it merged.

### PUBLIC

Quiet until Saturday, then a three-way audit of the money path, the generation loop, and the roadmap. It surfaced three real defects: cancelled orders were never actually refunded to the card, a cost reversal was never emitted, and two simultaneous generations could permanently overwrite each other's image.

Four changes shipped and merged the same day — a test-debt batch, atomic reservation of generation numbers, administrator-triggered refunds with recovery for stranded submissions, and a data change so every checkout writes its line items. The most valuable moment was an adversarial review catching that an earlier headline fix had been inert the entire time: correct-looking code that never actually ran.

## WEEK 2026-07-20

sessions: 1
commits: 11

### PRIVATE — source material, do not publish

> Week opened with the post-incident batch (PRs #97-#100: back-design discoverability, cancellable generation, the Stripe test-mode e2e, WP5 route coverage) and the Model B migration plan. The e2e then ran live for the first time and went green after adapting to Stripe's new hosted-checkout layout. Issue #102 — back-flow previews always showing the wrong design — was reproduced locally and traced to R2 mockup keys omitting the parts the cache key distinguishes; fixed with a shared key builder and versioned cache. Opus sub-agents delivered the warm design-thread cache (#87) and per-PR ephemeral Turso e2e databases (#31), targeting the shared-DB e2e flake.

### PUBLIC

The post-incident batch landed — back-design discoverability, cancellable generation, an end-to-end purchase test running in the payment provider's test mode, and route coverage — alongside a migration plan for the new data model. That end-to-end test then ran live for the first time and passed, once adapted to a checkout page the provider had quietly redesigned.

A reported bug where back-side previews always showed the wrong design was reproduced locally and traced to storage keys that omitted the very distinction the cache key relied on — fixed with one shared key builder and a versioned cache. Separately, a warm cache for design threads and per-change disposable test databases landed, both aimed at test flakiness caused by everything sharing a single database.

## WEEK 2026-07-27

sessions: 0
commits: 4

### PRIVATE — source material, do not publish

> The week opened with an urgent incident: migration 0006 had silently no-op'ed on production, leaving checkout broken for roughly 20 hours before being caught, re-applied, and verified across prod and preview. Despite the rocky start, the team closed out a major merge session — landing PRs #118 and #119 and running the first live Printful contract check, which passed end-to-end with a real order. Mid-week shifted to a recovery and observability effort after an accidental design deletion was traced and found to be fully recoverable, while a masked Server Components error on prod exposed a gap in error visibility — prompting a proposal (#121) for an onRequestError hook and a minimal error logging table. The week closed with a focused multi-agent session on mobile UX polish, surfacing and addressing several user-reported issues including deletion failures on phone, slow page loads, missing account email in the menu, and inconsistent t-shirt color rendering behind transparent images.

### PUBLIC

The week opened badly. A database migration had silently done nothing on production, leaving checkout broken for roughly twenty hours before anyone noticed. It was re-applied and verified across both production and preview — and the failure mode deserves naming, because a migration that fails loudly is a nuisance, while one that succeeds at nothing is a twenty-hour outage.

Despite that start, a large merge session closed out, including the first live contract check against the fulfillment partner, which passed end to end with a real order. An accidental design deletion turned out to be fully recoverable. A masked server error on production exposed a genuine gap in error visibility and produced a concrete proposal to close it. The week ended on mobile polish: deletion failures on phones, slow pages, a missing account address in the menu, and shirt colours rendering inconsistently behind transparent images.
