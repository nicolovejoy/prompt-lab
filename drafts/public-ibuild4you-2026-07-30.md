# Public refresh draft — ibuild4you

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-06-08 -->
<!-- unpublished weeks found: 7 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-ibuild4you-2026-07-30.md --apply

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

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light week for ibuild4you, with only two active days and the bulk of meaningful work concentrated on May 21st. The week's standout effort was a cost investigation that traced roughly $49.70 of a ~$50 total API spend back to a single route: `brief.generate`. The developer dug into the root cause, added a missing Firestore composite index to enable proper per-route/project querying, and identified the top-spending projects. A `touch-stuck-briefs` script was built and safely deployed — first in dry-run mode, then applied to three projects — to unstick briefs that had stalled and were likely driving repeated regeneration cycles. Toward the end of the day, a new issue emerged: outbound nudge messages were leaking into a maker's active conversation thread, which prompted a review of the message-crafting logic and early discussion around routing these messages through email as a safer delivery channel.

### PUBLIC

TODO

## WEEK 2026-06-15

sessions: 3
commits: 6

### PRIVATE — source material, do not publish

> The week was a focused two-day ship sprint on ibuild4you, delivering a high volume of fixes and features across both product polish and infrastructure stability. Monday kicked off with a triage of real user feedback from Matt/BySide that drove five discrete fixes — including agent self-awareness, a /members 500 error, welcome replay, and a builder-to-maker email flow — alongside a critical diagnosis and circuit-breaker fix for a ~$8/day cost runaway caused by brief regeneration loops. The Phase 0 sweep (PR #77) consolidated reminder status on the Setup screen and tolerant JSON import handling into a single clean merge to production. Tuesday extended that momentum by shipping multi-person invite support (PR #79), resolving a meaningful product gap that previously clobbered the original inviter's identity when a second person was added to a shared brief. The week closed with the codebase in a healthier, more defensively architected state — cost-controlled, user-feedback-driven, and with collaborative brief-sharing now properly supported.

### PUBLIC

A two-day sprint driven almost entirely by real user feedback. One round of comments from a collaborating team produced five distinct fixes: the assistant now understands what it is and what it can do, a broken members page was repaired, the welcome sequence can be replayed, and there is a clean path for a builder to reach a maker by email.

Underneath that, a runaway loop that had been quietly regenerating the same document over and over was diagnosed and stopped with a circuit breaker — the kind of defect that costs real money while looking like nothing at all. The week also shipped support for inviting more than one person to a shared brief, closing a gap where adding a second participant overwrote the first.

## WEEK 2026-06-22

sessions: 1
commits: 8

### PRIVATE — source material, do not publish

> This was a focused two-day sprint that completed the UX-scrub initiative for ibuild4you, shipping all phases of the Brief/Setup overhaul to production. The week centered on three meaningful product changes: collapsing the builder nav into a cleaner Brief·Conversations·People structure (with Files folded into Brief), introducing a brief-as-document editor with both structured and raw-JSON modes, and correcting the established-maker share modal to reflect access-sharing semantics rather than a first-time invite flow. Across three PRs and a deep project resync, the team also paid down documentation debt — archiving shipped plans, correcting stale CLAUDE.md entries, and re-scoping lingering issues. The result is a tighter, more coherent brief-management experience backed by a cleaner project baseline.

### PUBLIC

The interface scrub finished and shipped. Builder navigation collapsed into three clear areas — brief, conversations, people — with files folded into the brief rather than living off on their own. The brief itself became an editable document, offering a structured view alongside a raw one for anyone who would rather work directly in the underlying data.

The sharing dialog for an established maker was corrected to describe what it actually does: granting access to work that already exists, not sending a first-time invitation. Documentation debt was paid down beside the code — finished plans archived, stale notes corrected — so the written record matches what is actually running.

## WEEK 2026-06-29

sessions: 2
commits: 6

### PRIVATE — source material, do not publish

> This week on ibuild4you, the team focused on expanding the brief creation system to support multiple participants in a single flow. Work began with a design session to understand current limitations and architect a flexible participants[] payload structure, and by the following day that design was fully implemented and shipped to production. Multi-participant brief creation was verified end-to-end using Playwright against a prod headless test-login, giving strong confidence in the rollout. Alongside the feature work, two important reliability improvements were made: decoupling "invite to this conversation" from "start a new conversation" to eliminate an accidental-session bug, and fixing a badge display issue on the brief page that was ignoring existing conversations (#103). The week closed on a high note with a non-destructive script to fix and reopen conversations, which was used to successfully recover from a real production incident.

### PUBLIC

Brief creation grew to handle several participants in a single flow. A design session established the shape of it, and the implementation shipped the following day, verified end to end against the live site rather than a staging copy.

Two reliability fixes landed with it. Inviting someone to an existing conversation was separated from starting a new one, which had been quietly creating sessions nobody asked for, and a badge on the brief page stopped ignoring conversations that already existed. The week closed with a repair script — non-destructive by design — that was written and then immediately used to recover from a real incident, rather than sitting unused as insurance.

## WEEK 2026-07-06

sessions: 1
commits: 2

### PRIVATE — source material, do not publish

> This was a short two-day week on ibuild4you split between infrastructure rollout and architecture planning. The week opened with a cross-portfolio effort to instrument all six Vercel projects with analytics, shipping unmerged PRs for each — including an additional Prompt Lab visitor beacon on ibuild4you itself. A recurring peer-dependency conflict between vite 8 and legacy packages emerged as a blocker across those changes, flagging a dependency alignment decision that needs resolution. The second day shifted gears entirely into design mode, focused on how to bridge ibuild4you's web-captured project data into Claude Code and Cowork on the Mac Mini. After evaluating options, the team committed to building an authenticated export endpoint on ibuild4you.com as the primary solution, with a local export script as an intermediate stepping stone — setting up a focused build sprint ahead.

### PUBLIC

A short week split between rollout and design. Analytics instrumentation went out across the whole portfolio of sites in one pass, which surfaced a dependency conflict that will need deciding before it blocks something more urgent.

The second half turned to a design question worth getting right: how work captured in the web product reaches the local tools where the deeper work actually happens. After weighing the options, the answer settled on a properly authenticated export built into the product itself, with a small local script as an interim step — choosing the durable path while still having something usable in the meantime.

## WEEK 2026-07-13

sessions: 1
commits: 6

### PRIVATE — source material, do not publish

> Week opened with the maker-feedback build plan landing: #141 reminder digest and #142 sibling locked-decision sharing merged to prod, #143's spec fleshed out for a later session. The Garm initiative then went from assignment to running code in a day — strategy comparison plus an OSS authz survey settled on a bespoke v1 with an OpenFGA-compatible check contract, the service repo was scaffolded and built through phase 3 by its own agent, and ibuild4you got a phased consumer plan (passcode retirement, legacy authz fallback removal, gnip consumption). A prod UX bug (#146, transcript pane read as lost messages) was fixed twice in one evening, ending on a persistent visible scrollbar after builder feedback.

### PUBLIC

Two tracks in one week. The maker-feedback work landed a reminder digest and the ability to share a locked decision across sibling projects.

Alongside it, per-repository access control went from an assignment to running code in a single day. A survey of existing open-source authorization engines settled the question in favour of a small purpose-built service with a standard-compatible check interface, and a phased plan was written for adopting it here: retire shared passcodes, remove the legacy fallback, then consume the new service directly. A user-facing bug where a transcript pane read as though messages had been lost was fixed twice in one evening — the first fix was correct and still looked wrong, which is its own kind of bug.

## WEEK 2026-07-27

sessions: 1
commits: 2

### PRIVATE — source material, do not publish

> The Garm consumption track came off an 11-day pause and closed three gates in one overnight session. PR #164 shipped the off-boarding revoke primitive and the live clean-revoke test was confirmed end-to-end by the garm service. The overdue shadow-mismatch log read came back clean, and PR #165's identity-relay e2e went all-pass after a notification kill switch stopped e2e runs from emailing real inboxes. The cutover (PR G) is now gated only on PR E and one fail-mode decision.

### PUBLIC

The access-control adoption came off an eleven-day pause and cleared three gates in a single overnight session. Off-boarding gained a revoke primitive, and a live test confirmed end to end that removing someone actually removes their access — the half of access control that usually goes untested until the day it matters.

An overdue audit comparing the old and new authorization decisions came back clean, meaning the two agreed everywhere it counted. The identity-relay tests went fully green once a kill switch stopped test runs from sending mail to real inboxes, a small fix that had been quietly undermining confidence in every result before it.
