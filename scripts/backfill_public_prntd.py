"""One-shot: write public-safe session summaries + weekly rollups for prntd.

Summaries authored by the running Claude Code session (Opus 4.7), based on
private session.summary text. Two empty sessions (341, 343) skipped.
A collaborator's first name has been generalized.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store import get_store  # noqa: E402

PROJECT = "prntd"

SESSIONS = [
    (223, "2026-03-27 21:51:52",
     "Wired up the live shipping flow via Stripe Checkout, built an admin "
     "dashboard, and launched real payments end-to-end with Printful "
     "auto-confirming print orders. Added a background-removal pipeline so "
     "designs render cleanly on shirts, and backfilled transparent backgrounds "
     "across the existing catalog."),
    (225, "2026-03-28 03:48:48",
     "Major UX overhaul. Split the design chat from the generation surface "
     "with a side-panel gallery and a lightbox view, added a five-component "
     "design system with twenty tests, image-reference uploads, an archive "
     "for ordered designs, and markdown-rendered chat. Auto-detection of "
     "generation intent and a checkerboard background for transparency."),
    (236, "2026-03-30 01:28:15",
     "Migrated every page to the new design system components. Built a "
     "mobile-friendly gallery drawer for design pages, improved the lightbox "
     "with zoom and an order CTA, and tightened mobile checkout with sticky "
     "positioning and larger touch targets."),
    (239, "2026-03-30 18:59:01",
     "Shipped phase one of order tracking — schema columns, a Printful "
     "webhook handler, a customer-facing orders page, and an admin retry "
     "mechanism for stuck orders. Cleaned up navigation and the order-confirm "
     "page."),
    (241, "2026-03-30 19:34:15",
     "Extracted pricing, the order state machine, and webhook handlers into "
     "testable modules with twenty-eight tests. Added transactional email "
     "for order confirmation and shipping updates, plus a password-reset "
     "flow."),
    (252, "2026-04-01 18:00:00",
     "Switched email to the prntd.org domain, registered Printful's webhook "
     "via API, and added drag-and-drop image upload to the design chat backed "
     "by R2 storage. Fixed a body-size limit and a chat crash."),
    (254, "2026-04-01 23:30:00",
     "Built an accounting foundation: an append-only ledger table, order "
     "classification tags, Printful cost tracking, soft-delete archive, and "
     "an admin financial summary. Reconciled all orders against Printful "
     "billing — identified four 'ghost' orders that were never charged. "
     "Wired in cancellation handling via webhook."),
    (256, "2026-04-02 14:31:32",
     "Built an order classification system — customer, sample, test, "
     "owner-use — with a composable filter and sort architecture. Added a "
     "per-order detail page in the admin. Eighty-two tests in the suite."),
    (276, "2026-04-05 23:29:47",
     "Integrated Printful's mockup-generator API for photorealistic product "
     "previews. Built a config-driven product catalog so the site could "
     "support multiple products, and added a heavyweight box tee as the "
     "second product."),
    (279, "2026-04-06 02:40:08",
     "Fixed the production build, added customer order-status filters "
     "(active, canceled, all) to the customer orders page, and wrote a "
     "Stripe-fee backfill script for the ledger."),
    (281, "2026-04-06 05:40:00",
     "Added an iPhone case as a product and threaded productId through the "
     "preview and order pages so colors, sizes, and labels come from the "
     "product config rather than hardcoded constants."),
    (283, "2026-04-07 18:29:45",
     "Added a product-selector UI to the preview page with background mockup "
     "preloading — all product-and-color combinations preload in parallel, "
     "throttled to three at a time. Fixed a Printful timeout and a "
     "duplicate-request issue."),
    (285, "2026-04-07 20:28:45",
     "Added Stripe promotion-code support — schema fields, checkout "
     "configuration, and webhook handling that adjusts totals and ledger "
     "entries when discounts apply."),
    (294, "2026-04-09 18:15:00",
     "Added an admin Recover action that replays the Stripe webhook for stuck "
     "pending orders, with fourteen new tests. Extracted a post-order email "
     "helper, dropped generation cost from the customer-facing price so the "
     "order breakdown math reconciles, and surfaced Recover error reasons in "
     "the admin UI."),
    (313, "2026-04-15 01:15:51",
     "Upgraded the design AI to claude-sonnet-4-6 ahead of the older model's "
     "retirement. Started splitting the project onto its own Anthropic API "
     "key with secrets stored in 1Password."),
    (314, "2026-04-17 00:31:35",
     "Pushed the model upgrade to production. Reviewed the product catalog "
     "and chose a Bella Canvas 6400 women's tee as the next addition."),
    (315, "2026-04-18 00:44:30",
     "Fixed sonnet-4-6 compatibility issues — an assistant-prefill guard and "
     "a useEffect infinite-loop. Added the women's relaxed tee to the catalog "
     "with twenty-two colors. Fixed a Printful API key and corrected a "
     "misconfigured product ID."),
    (322, "2026-04-27 21:03:09",
     "Wrote a strategic snapshot mapping three product surfaces against "
     "ground truth, then shipped a PRINTFUL_DRY_RUN flag with tests and an "
     "end-to-end runbook so the build pipeline can be exercised without "
     "spending real Printful budget. Validated the dry-run flow with a "
     "Stripe test card. Made the repository public."),
    (334, "2026-05-01 20:01:14",
     "Set up branch protection, CI, and contribution guidelines, then "
     "onboarded a first external collaborator who landed their first pull "
     "request. Adopted a workflow split — solo work pushes directly to main, "
     "pull requests are reserved for collaborator changes. Auto-naming and "
     "improved email subjects shipped via that flow."),
    (336, "2026-05-02 03:55:16",
     "Worked through several background-removal approaches — switched the "
     "provider, added retries on rate limiting, then a heuristic to skip "
     "processing when text would be lost. Validated Ideogram's native "
     "transparent generation as a viable replacement. Shipped phase two of "
     "the print-targets data model with a backfill, dual-read, and an "
     "auto-mockup on order placement."),
    (342, "2026-05-04 22:13:11",
     "Shipped the swap to Ideogram's native-transparent generation — "
     "confirmed working in production. Shipped phase one of negation-rewriting "
     "in the chat advisor, with partial improvement on a known failure mode. "
     "Wrote up the phase-two plan."),
    (344, "2026-05-06 01:51:47",
     "Began the data-model rework for design assets — added a primary "
     "image-id column with dual-write and backfill (fifty-seven designs "
     "migrated). Rewrote the preview page as a pure function of design and "
     "product, introduced a placement-render server action, and fixed a "
     "foreign-key cascade on design deletion."),
    (347, "2026-05-06 15:18:16",
     "Continued the data-model rework — retired the legacy currentImageUrl "
     "field after a column drop, added bulk Printful pre-fetching on order "
     "accept and on revisit, rewrote the gallery with a product-versions "
     "section, and added order-pin protection on design deletion. Expanded "
     "the box tee from thirteen to twenty-five colors."),
    (353, "2026-05-06 22:53:24",
     "Replaced the JSON chat-history column with an append-only chat-message "
     "table. Append-only writes eliminated a read-modify-write race, readers "
     "now source from the message table and design-image table, and "
     "image-URL duplication is gone. The backfill migration ran clean — four "
     "hundred and eight messages across forty-six designs migrated and the "
     "legacy column dropped."),
]

WEEKLY = [
    ("2026-03-23", 2, 28,
     "Crossed from beta into a real, transactable storefront. Stripe payments "
     "live end-to-end with Printful auto-confirming print orders, and a major "
     "UX overhaul split the design chat from generation with a side-panel "
     "gallery, lightbox, image-reference uploads, and a five-component design "
     "system. Background removal so designs render cleanly on shirts."),
    ("2026-03-30", 7, 22,
     "Built out the operational backbone. Migrated every page onto the new "
     "design system, shipped order tracking with a Printful webhook handler, "
     "and extracted pricing, the order state machine, and webhook logic into "
     "testable modules. Added transactional email, password reset, "
     "drag-and-drop uploads backed by R2, and an append-only accounting "
     "ledger. Reconciled against Printful billing and identified four ghost "
     "orders never charged. Capped the week with a Printful mockup-generator "
     "integration and a multi-product catalog."),
    ("2026-04-06", 5, 12,
     "Multi-product expansion. iPhone cases joined the catalog, productId "
     "threaded through preview and order pages so colors and sizes flow from "
     "configuration. Added a product-selector UI with parallel mockup "
     "preloading, Stripe promotion-code support, and an admin Recover action "
     "that replays Stripe webhooks for stuck orders."),
    ("2026-04-13", 3, 5,
     "Model upgrade work. Moved the design AI to claude-sonnet-4-6 ahead of "
     "older-model retirement, fixed compatibility issues, and added a women's "
     "relaxed tee with twenty-two colors. Began splitting the project onto "
     "its own Anthropic API key with 1Password-backed secrets."),
    ("2026-04-27", 3, 11,
     "Opened the codebase up. Made the repository public, added branch "
     "protection, CI, and contribution guidelines, and onboarded a first "
     "external collaborator who landed their first pull request. Shipped a "
     "PRINTFUL_DRY_RUN flag with tests and an end-to-end runbook so the "
     "build pipeline can be exercised without spending real Printful budget. "
     "Worked through several background-removal approaches and validated "
     "Ideogram's native transparent generation as a viable replacement."),
    ("2026-05-04", 6, 21,
     "Major data-model rework alongside the move to native-transparent image "
     "generation. Ideogram's transparent output went live, retiring most of "
     "the background-removal pipeline. The design-asset model migrated to a "
     "dedicated primary-image column with dual-write and backfill (fifty-seven "
     "designs), the preview page was rewritten as a pure function of design "
     "and product, and bulk Printful pre-fetching landed on order accept. The "
     "JSON chat-history column was replaced with an append-only chat-message "
     "table, with four hundred and eight messages migrated cleanly."),
]


def main():
    store = get_store()
    for sid, started_at, summary in SESSIONS:
        store.upsert_public_session_summary(
            project=PROJECT, session_id=sid,
            started_at=started_at, public_summary=summary,
        )
    print(f"  public_session_summaries: {len(SESSIONS)} rows")

    for week_of, sessions, commits, summary in WEEKLY:
        store.upsert_public_weekly_rollup(
            project=PROJECT, week_of=week_of,
            public_summary=summary,
            session_count=sessions, commit_count=commits,
        )
    print(f"  public_weekly_rollups: {len(WEEKLY)} rows")


if __name__ == "__main__":
    main()
