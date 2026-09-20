# National Math Stars application: portfolio evidence

Assessment date: September 20, 2026 (America/Los_Angeles).
Purpose: evidence for preparing for the Founding Head of Technology role. This is
an assessment of the work, not application copy or a cover letter.

## Main conclusion

Nico repeatedly uses AI coding agents to turn product and systems judgment into
substantial, integrated software, then operates and revises it. The strongest
evidence is implementation spanning interfaces, APIs, permissions, data models,
migrations, external services and deployment, followed by corrections prompted
by real use, failures and review.

“Experienced AI-native engineer” is supported when it means directing agents
through substantial development and taking responsibility for outcomes. It is
only partly supported if it implies independent mastery of every implementation
detail or consistently mature operations. The inspected work does not establish
large-scale reliability, broad commercial adoption, institutional security
assurance, or management of a staffed engineering organization.

The portfolio supports this capability at small-system scale. The open question
is how consistently verification, security and operating discipline will hold as
stakes, user count and organizational complexity grow.

## Five strongest end-to-end ownership examples

1. **MusicForge:** community use and substantial integration across React, Flask,
   Firebase, Google Drive, notation/PDF rendering and separate deployments.
   Codex PR #506 implements OAuth, browser account state, storage decisions,
   callback UX, tests and rollout sequencing. A two-account Drive experiment
   disproved an assumed sharing capability and changed the launch design. After
   deployment ordering failed twice, Nico reprioritized an executable backend
   readiness gate. The decision record reports roughly 35 camp signups, not a
   verified active-user/retention figure. The ownership/setlist redesign remains
   in progress.

https://github.com/nicolovejoy/musicforge/pull/506

https://github.com/nicolovejoy/musicforge/issues/551#issuecomment-5719057907

https://github.com/nicolovejoy/musicforge/issues/513

https://github.com/nicolovejoy/musicforge/blob/main/docs/decisions.md

2. **Prompt Lab:** an operating developer platform: machine-local SQLite,
   synthesis, selected Turso synchronization, authenticated dashboard, reports,
   public publishing and health checks. Raw prompts have no cloud sync leg;
   public prose receives leakage checks and human review. Per-machine summary
   parts and deterministic merging prevent cross-machine clobbering. Failures
   led to artifact-freshness checks and ordered nightly execution. The agent
   workflow is itself engineered: shared command sources, Claude/Codex adapters,
   context management, cross-repo handoffs and concurrency tests. The newest
   Codex bookkeeping pilot is not established as complete.

Sources: [store interface](../store/base.py),
[sync](../sync_to_turso.py), [data/access boundaries](data-and-access.md),
[dual-agent design](superpowers/specs/2026-09-12-dual-agent-commands-design.md),
[handoff test harness](../workflow/handoff-sim/README.md).

https://github.com/nicolovejoy/prompt-lab/issues/45

3. **split-recording:** complete rehearsal workflow from long audio through
   silence detection, editing, transcription, repertoire matching, SQLite
   records, export and catalog publication. Deliberately local/single-user, with
   a separately published catalog. PR #138 documents 12 implemented/reviewed
   subagent tasks and whole-branch review. JSON-to-SQLite migration preserves the
   frontend contract; corpus refresh validates before atomic replacement and
   retains a usable cache. PR #134 isolates end-to-end tests using synthetic
   audio, scratch databases and separate ports.

https://github.com/nicolovejoy/split-recording/pull/138

https://github.com/nicolovejoy/split-recording/pull/134

https://github.com/nicolovejoy/split-recording/blob/main/backend/db.py

https://github.com/nicolovejoy/split-recording/blob/main/backend/corpus_pull.py

4. **PRNTD:** design generation through checkout, Printful fulfillment, email and
   tracking. Concrete reliability work includes signed Stripe webhooks,
   external-ID recovery after ambiguous fulfillment requests, unique ledger
   constraints and payment-redelivery/race tests. A missing-migration launch
   failure led to migration-drift checks; browser tests moved to per-run
   ephemeral Turso branches. Owner testing simplified ordering; later decisions
   retired organizer storefronts. The README reports paid fulfilled orders, but
   merchant records were not audited. E2E is not yet a required gate.

https://github.com/nicolovejoy/prntd/blob/main/src/lib/order-fulfillment.ts

https://github.com/nicolovejoy/prntd/blob/main/src/lib/__tests__/money-path.integration.test.ts

https://github.com/nicolovejoy/prntd/blob/main/.github/workflows/ci.yml

5. **Recountly → Raconte:** browser recording failures prompted durable-save
   fixes, adversarial review, and then a native architectural reversal. The
   Recountly save-loss issue was fixed and closed before the rewrite; the web
   repository is now archived. Raconte makes audio authoritative, machine
   transcripts replaceable and human revisions separate, with atomic files,
   Swift actors, on-device transcription and private CloudKit sync. TestFlight
   and Mac build records establish distribution/owner use. Current storage is
   **files plus CloudKit, not SQLite**; GRDB is planned. Full fresh-container
   iCloud recovery acceptance remains unrun.

https://github.com/nicolovejoy/recountly/pull/44

https://github.com/nicolovejoy/recountly/issues/23#issuecomment-5017955017

https://github.com/nicolovejoy/raconte/blob/main/docs/overview.md

https://github.com/nicolovejoy/raconte/blob/main/docs/builds.md

## Additional evidence to retain

- **BySide:** unusually clear external-feedback chain. Broker input changed the
  conception from consumer brokerage to software for brokerage teams; a
  walkthrough led to insurance and pre-acceptance buyer features. Tenant scopes,
  audited private documents and data-preserving schema renames are implemented.
  PR #150 explicitly records Codex implementation followed by Claude integration
  and the first real-database verification.
- **Garm:** reusable authorization with scoped keys, prevention of unrelated
  identity disclosure, alias/grant transaction locks and explicit consumer
  contracts. A production driver mismatch led to testing against real
  PostgreSQL/postgres.js as well as PGlite. A client-package evaluation rejected
  unnecessary packaging overhead for mixed Python/TypeScript consumers.
- **stars-demo:** scaffold September 17 to recorded production invitations
  September 19. Default-deny roles, consent before admin answer access, audited
  reads, transactional deletion and an OTP concurrency repair are implemented.
  This is a small deployed listening pilot; completed research and uptake were
  not established. The sign-in PR merged before requested review returned.
- **iBuild4you:** versioned briefs, discovery-agent conversations shaped by builder
  annotations, membership checks, cost observability, and reusable feedback
  capture through Loop. Evidence of mechanisms for organizational leverage, not
  quantified time savings or broad adoption.
- **person-tracking:** substantial collaborative scientific data engineering:
  sensor alignment, relational analysis models, Celery workflows and encrypted
  participant fields. Do not attribute the entire system or every control to
  Nico; significant components and history belong to collaborators.
- **NoteMaxxing:** negative product evidence worth preserving. The daily-learning
  system and subsequent gamification did not produce target-user engagement;
  scheduled delivery was deliberately stopped. Shipping is not proof of value.
- **Songpath:** teacher feedback narrowed scope and changed the authoritative
  workflow; production login remained unconfirmed in the inspected record.

https://github.com/nicolovejoy/byside/pull/150

https://github.com/nicolovejoy/garm/commit/9e7d441

https://github.com/nicolovejoy/stars-demo/pull/15#issuecomment-5744994613

https://github.com/nicolovejoy/ibuild4you/blob/main/lib/feedback/README.md

https://github.com/nicolovejoy/notemaxxing/blob/main/CLAUDE.md

## Quantitative evidence and its limits

- **59 accessible canonical repositories:** 58 on GitHub (29 public, 29 private)
  plus private GitLab person-tracking. This is visibility, not 59 built products.
- **41 local checkouts deduplicate to 37 repositories.** The remaining 22 had
  metadata coverage, not deep source review. Smaller local repositories also
  received uneven depth of inspection.
- Local default-branch histories contain **6,730 nonmerge commits**, including
  **6,341 in 2026** and **4,008 during June 22–September 20**. Activity spans
  **32 repositories and 240 Pacific calendar days in 2026**.
- **5,438 commits carry explicit Claude coauthor trailers.** Codex trailer counts
  sharply undercount its independently documented work; do not compare agent
  contributions using trailers.
- **30/37** local repositories have tracked agent instructions, **22/37** have
  test-like filenames and **16/37** have GitHub workflow files. Presence does not
  prove execution or quality.
- **At least 16 repositories contain meaningful implemented security/privacy
  controls:** MusicForge, Prompt Lab, split-recording, PRNTD, Recountly, Raconte,
  BySide, Garm, iBuild4you, stars-demo, person-tracking, InviteKit, NoteMaxxing,
  Nudge, DADU and Songpath. This is not a count of independently secure products.

These are potentially stale local history snapshots, including documentation,
generated work and collaborators' commits. Agents often use Nico's Git identity.
Counts show sustained practice, not sole authorship, correctness, productivity,
adoption or return on investment. No application tests or production probes were
rerun for this assessment; test outcomes quoted in the full report are dated
PR/CI records.

## Qualifications and interview preparation

1. **Verification can trail change volume.** MusicForge had 22 authorization tests
   passing against permissive emulator defaults before the real-rules harness;
   BySide needed integration-stage database validation; stars review found a
   blocking race after merge. Explain how these changed the release process.
2. **Operations are real but incompletely proven.** Raconte restore acceptance is
   unrun; BySide's inspected documentation allows previews to write production;
   Prompt Lab acknowledges a monitoring path unable to detect its own scheduler
   dying. Do not present old caveats as freshly confirmed live state.
3. **Security sophistication is uneven.** InviteKit's checked-in rules allow
   public event/invitation reads despite its UUID-secrecy narrative. This needs
   audit; no live disclosure was established. No independent security audit or
   institutional child-data assurance was demonstrated by this research.
4. **Adoption and scale are limited evidence.** Personal/community use, reported
   orders and pilot invitations do not prove retention, revenue scale or
   organizational impact. NoteMaxxing is a useful counterexample.
5. **Attribution and independent depth require direct assessment.** Agent-written
   plans are not proof Nico originated every design. Be ready to explain an
   actual cross-service failure, defend data/permission boundaries, and describe
   or demonstrate recovery. Staff-management experience is not established by
   repository artifacts.

https://github.com/nicolovejoy/musicforge/pull/590

https://github.com/nicolovejoy/invitekit/blob/main/firestore.rules

## Research artifacts and continuation

The full assessment includes a project/dimension matrix, further implementation
citations, and the complete inventory:

- [Full assessment](../reports/Agentic%20software%20portfolio%20evidence.md)
- [Inventory and secondary-project evidence](../research_notes/Agentic%20software%20portfolio%20evidence/inventory.md)
- [MusicForge, recording tools and stars evidence](../research_notes/Agentic%20software%20portfolio%20evidence/product_systems.md)
- [Workflow, authorization and data evidence](../research_notes/Agentic%20software%20portfolio%20evidence/workflow_data_security.md)
- [Default-branch metrics](../research_notes/Agentic%20software%20portfolio%20evidence/default-branch-metrics.json)

These supporting artifacts exist locally; the report directory is ignored and
the research notes were untracked when this summary was saved. This document
preserves the substantive conclusions independently of those local artifacts.

Useful next step for application/interview preparation: choose two or three of
the concrete cases above and explain the initial need, Nico's decisions, the
agents' contribution, what failed, how it was verified, and what remains unknown.
Do not turn the assessment into unsupported claims about scale or security.
