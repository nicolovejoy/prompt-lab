# Public refresh draft — prompt-lab

<!-- generated: 2026-07-30 -->
<!-- last published week_of: 2026-05-04 -->
<!-- unpublished weeks found: 14 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prompt-lab-2026-07-30.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-02-16

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> A pivotal week for prompt-lab's direction. The project shifted from being a prompt management tool to an intention tracking system with autonomous summarization. The core decision was to use Claude API calls via cron jobs to automatically summarize daily and weekly work across all repositories and identify cross-project themes. This set the architectural direction that would later evolve into the knowledge store abstraction.

### PUBLIC

A pivotal week for direction. The project stopped being a prompt-management tool and became something closer to a work journal that writes itself: automatic summarization of daily and weekly activity across every repository, with recurring themes surfaced rather than hand-tagged.

The core decision was that scheduled jobs would do that summarizing unprompted, rather than the whole thing depending on someone sitting down to write it. That choice set the architectural direction the project still follows, and led directly to the storage abstraction that arrived later.

## WEEK 2026-04-20

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> A quiet week for prompt-lab itself — no code changes. The single tracked day was a planning session for a new sibling project: pianohouseproject.org, a public portfolio that will live in its own repo and surface the projects Nico has been building (often with Claude). Scope, domain choice, project list, and the editorial tone of the about page were settled.

### PUBLIC

No code this week. The one tracked day went to planning a sibling project: a public portfolio site to surface the work these tools had been quietly recording all along.

Scope, domain, the list of projects worth showing, and the editorial voice of the about page were all settled before a line was written — which is the right order for something whose entire purpose is how it reads.

## WEEK 2026-04-27

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> This was a short but pivotal week that shifted focus from prompt-lab itself to building a public-facing portfolio site for Nico's collaborative projects. The first day was entirely planning — scoping the site concept, choosing the pianohouseproject.org domain, curating the project list, and working out the tone for the about page. Day two moved fast into execution: a full Next.js 16 App Router + Tailwind scaffold landed at ~/src/pianohouse with four core pages, a server-action contact form (backend wiring deferred), and five placeholder projects seeded including prompt-lab itself. The week closed with a handoff prompt written for a fresh agent to continue work in the new repo.

### PUBLIC

A short but pivotal week that shifted attention from the tool to the public portfolio it feeds. The first day was pure planning — scoping the site, choosing the domain, curating which projects belong on it, working out the tone of the about page.

The second day moved fast into execution: a full scaffold with four core pages, a contact form with the backend deliberately deferred, and five placeholder projects seeded, including this one. The week ended by writing a handoff for a fresh agent to pick the work up in the new repository, which doubles as a test of whether the thinking was legible enough to hand over at all.

## WEEK 2026-05-11

sessions: 2
commits: 2

### PRIVATE — source material, do not publish

> A light two-day week focused on infrastructure reliability and cross-machine workflow improvements. The major issue was a completely broken synthesizer pipeline caused by an invalid API key — after tracing through logs, updating secret references, and raising spending caps, the pipeline is back online with a newly dedicated API key to isolate prompt-lab costs. The other day was spent polishing the multi-machine developer experience on the mini, syncing new slash commands and scripts, enhancing /readup to surface stale branches across machines, and injecting machine identity into the session context so agents are always location-aware.

### PUBLIC

A light two-day week on reliability and cross-machine workflow. The real problem was a summarization pipeline that had stopped working entirely, traced through logs to an invalid credential. It came back online with a dedicated key, so this project's costs are isolated rather than pooled with everything else's.

The other day went to the two-computer experience: syncing commands and scripts between machines, surfacing branches that are stale on one but not the other, and injecting machine identity into the session context so an agent always knows which computer it is actually sitting on.

## WEEK 2026-05-18

sessions: 0
commits: 8

### PRIVATE — source material, do not publish

> The week on prompt-lab was defined by two major threads: fixing a silent but critical data integrity bug and building out a full API cost tracking system. The week opened with the discovery that a base class abstract-method drift in SqliteKnowledgeStore had been silently skipping daily summaries and weekly rollups on every /handoff — a subtle bug with broad impact that was diagnosed, reproduced cleanly, and resolved. From there, the focus shifted to Anthropic API cost visibility: a full end-to-end pipeline was designed and shipped that pulls nightly from three Admin API endpoints, populates dedicated tables, syncs to Turso, and renders per-project cost charts. A notable mid-build discovery — that Admin API amounts are denominated in cents, not dollars — briefly suggested one workspace was burning nearly $1,000/day before the misread was corrected to a far more reasonable $9.40. The week closed with iterative UX refinement across project pages, reducing information overload, improving chart legibility, and tightening the timeline display into a cleaner, more scannable interface.

### PUBLIC

Two threads. The first was a silent data-integrity bug: a drift between a base class and its implementation had been quietly skipping daily summaries and weekly rollups on every run — no error, no warning, simply nothing written. Diagnosed, reproduced cleanly, fixed.

The second was cost visibility, built end to end: a nightly pull from three reporting endpoints into dedicated tables, synced to the cloud database and rendered as per-project charts. A memorable mid-build discovery — the reported amounts are denominated in cents, not dollars — briefly made one workspace appear to be burning roughly a hundred times what it actually was. The week closed on interface work, cutting information overload on project pages and tightening the timeline into something scannable.

## WEEK 2026-05-25

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light but purposeful week on prompt-lab, with activity focused on infrastructure setup and early product planning. The developer secured the domain prompt-labs.org through Cloudflare, marking a concrete step toward a public-facing presence for the project. On the product side, work continued on UI refinements — specifically around session duration display and a status toggle — though this appears to have been largely exploratory and conversational rather than code-committed. A rename of the "ground control" component was also initiated alongside a database update request, signaling that some structural decisions are being made. The week wrapped with a numbered TODO list generated as a planning artifact, suggesting the project is transitioning into a more organized execution phase.

### PUBLIC

A light but purposeful week. The domain was secured — a concrete step toward a public presence rather than a private tool. Interface work continued around session duration and a status toggle, though largely as conversation rather than committed code.

A rename of the original working title was set in motion alongside the corresponding data change. The week ended with a numbered plan written down, a small signal of the project moving from exploration into execution.

## WEEK 2026-06-01

sessions: 1
commits: 8

### PRIVATE — source material, do not publish

> This was a focused two-day security and infrastructure hardening week for prompt-lab. The primary effort centered on closing out issue #5: the Turso database was fully isolated into its own access group, with all 13 tables migrated, both machines and the web client repointed, and the old shared DB destroyed to neutralize the legacy token. Alongside that, the Claude Code secret-blocking hook received multiple rounds of hardening — adding template allowlists, symlink resolution, exact basename anchoring, and case-insensitive matching — then was version-controlled into the repo with an install script for consistent deployment across machines. Environment configuration was also cleaned up by retiring the legacy synth.env fallback and standardizing on the 1Password/.env.tpl pattern. On the side, a public vibe-coding-lessons page was shipped to PianoHouseProject.org, though it required a post-ship correction to fix AI-authorship overclaiming and a 60% content cut.

### PUBLIC

A security and infrastructure hardening week. The main effort isolated the database into its own access group: thirteen tables migrated, both machines and the web client repointed, and the old shared database destroyed so the legacy credential became inert rather than merely rotated. Destroying it is the part that mattered — a rotated key whose target still exists is a key that still works for someone.

The hook that stops agents reading secrets got several rounds of hardening: template allowlists, symlink resolution so an innocuous name pointing at a real secret is still refused, exact name anchoring, case-insensitive matching. It was then version-controlled with an install script so both machines run the same thing. A public lessons page also shipped to the portfolio site, then needed a correction for overclaiming human authorship of machine-written prose, plus a sixty percent trim.

## WEEK 2026-06-08

sessions: 1
commits: 5

### PRIVATE — source material, do not publish

> Two threads dominated. First, a shared-conventions sync mechanism: a single canonical source file compiled into each repo's CLAUDE.md between sentinel markers (chosen over @import after verifying @import is Claude-Code-harness-only and wouldn't reach cloud/third-party readers), with a /readup drift-check and rollout to 30 repos. Second, a full resolution of the long-flagged /handoff-vs-public-data invariant: removed /handoff's public-write steps so the reviewed backfill scripts are the sole writer, reconciled the public tables to the consumer's 7-key historyKey manifest (purging a re-leaked client project plus a dozen strays from both local and Turso), documented the whole storage/access model in docs/data-and-access.md, and built a report-only drift guard that immediately caught more Turso-only strays a manual purge had missed.

### PUBLIC

Two threads. A shared-conventions mechanism: one canonical source file compiled into each repository's instructions between sentinel markers, with a drift check at session start and a rollout across thirty repositories. Compiling to committed text was chosen over an import directive after verifying that imports resolve only inside one particular tool — anywhere else, a reader sees the literal path and nothing else.

The second thread closed a long-flagged invariant about public data. Automatic writes were removed, leaving reviewed scripts as the sole writer; the public tables were reconciled against the consuming site's manifest; the whole storage and access model was documented in one place; and a report-only drift guard was built, which immediately caught strays a manual purge had missed. That last detail is the entire argument for having the guard.

## WEEK 2026-06-22

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light, single-day week on prompt-lab focused on a meaningful architectural decision. The developer evaluated feedback from a repo agent suggesting that intention tracking may be unnecessary overhead in the system, and ultimately decided to proceed with its removal. Following that decision, they took a coordination step to broadcast the change to other agents via the shared communication channel, ensuring the broader system is aligned with the new direction.

### PUBLIC

A single-day week containing one real architectural decision. Feedback from an agent working inside the repository suggested the intention-tracking feature had become overhead rather than value. After evaluating it, the call was to remove it entirely rather than keep maintaining something nobody read.

The change was then broadcast to other agents through the shared coordination channel — deleting a feature is only half the work while other parts of the system still expect it to be there.

## WEEK 2026-06-29

sessions: 1
commits: 4

### PRIVATE — source material, do not publish

> This week on prompt-lab, the primary focus was shipping and hardening the cross-machine agent coordination system. The big milestone was closing issue #7: migrating handoff state from unversioned local files into a dedicated private git repo (`nicolovejoy/handoff`), giving the workflow a proper versioned backbone. A hardened `handoff.sh` wrapper was built and installed, covering append/sync/pull operations with mutex locking, portable timeouts, and clean exit codes. The SessionStart hook was wired to inject the relevant channel's Active section after a time-boxed pull, and both `/handoff` and `/readup` commands were updated to reflect the new flow. The second day shifted to integration work — connecting `handoff.sh` into the `readup` command and verifying Claude's `settings.json` permissions — where a BSD awk compatibility bug in multi-line `-v` args was caught and fixed, keeping the wrapper truly portable across both machines.

### PUBLIC

The cross-machine coordination system shipped and hardened. Handoff notes migrated out of unversioned local files into a dedicated private repository, giving them a versioned backbone and letting them survive any single machine.

A wrapper covering append, sync, and pull was built with mutex locking, portable timeouts, and meaningful exit codes, so a conflict or an offline machine surfaces loudly instead of silently swallowing a note. The session-start hook now injects the relevant channel automatically after a time-boxed pull. Integration work caught a portability bug in multi-line arguments that appeared on only one of the two environments — precisely the kind of defect that stays invisible until the day you happen to be on the other machine.

## WEEK 2026-07-06

sessions: 0
commits: 4

### PRIVATE — source material, do not publish

> This was a short but productive two-day week for prompt-lab, with a strong build day followed by a more exploratory one. The week opened with a significant push on the home dashboard — KPI tiles with pulse animations, a cross-project activity chart, and a Todos by-type view powered by batched, cached LLM classification were all shipped. A notable architectural decision was replacing third-party Vercel analytics with a first-party visitor beacon backed by Turso, giving the project full ownership of its usage data. The second day shifted toward research and reflection, with the developer investigating merging safety concerns for working agents in the repo and looking at Freevite as an open-source reference point for prompt-lab's direction.

### PUBLIC

A strong build day followed by an exploratory one. The home dashboard gained metric tiles, a cross-project activity chart, and a by-type view of open work powered by batched, cached classification — cached specifically so the steady-state cost of that classification rounds to nothing.

The notable architectural decision was replacing third-party analytics with a first-party visitor beacon writing to our own database. That came after checking the alternative properly rather than assuming: the hosted option had no read interface at all on the relevant plan, so it could never have fed a unified cross-site view no matter how convenient it looked from the outside.

## WEEK 2026-07-13

sessions: 4
commits: 12

### PRIVATE — source material, do not publish

> The week opened with a mobile UI pass shipping chart fixes for the visitors and costs pages, phone-verified on production, before attention shifted to a broader infrastructure investigation. A cross-repo authz survey across seven projects produced a clear decision: ibuild4you will own the initial Garm build-out, with a full v1 plan already written by week's end using Next.js, Neon, and Drizzle — retiring passcodes in favor of existing Google/password login. Mid-week, a phased roadmap with explicit pass/fail criteria was written and immediately acted on: a code survey corrected the premise of issue #23 (the feared clobbering bug couldn't exist since metadata was never being written to Turso at all), and a project metadata layer covering category, private, and status shipped via PR #26. A production 500 on Ask was resolved without any new key minting — the live key had been sitting in 1Password for 109 days while Vercel held a stale copy. The week closed by cracking a long-standing recountly deployment mystery: the project had never been Git-linked and had simply never had the deploy command run; one CLI invocation confirmed end-to-end with a real browser hit and a Turso row, and two faulty diagnostic techniques were officially retired and replaced with documented correct ones.

### PUBLIC

A dense week. It opened with a mobile pass on the charts, verified on an actual phone rather than a narrowed browser window. A survey of access control across seven projects then produced a clear decision about who builds what, with a full plan written by week's end and shared passcodes slated for retirement in favour of real sign-in.

A phased roadmap with explicit pass and fail criteria was written and immediately acted on — and promptly corrected the premise of one of its own items: the bug everyone feared could not exist, because the data in question was never being written to the cloud at all. The real gap was the opposite one. A production failure in the question-answering feature was resolved without minting any new credential; the working one had been sitting in the password manager for months while the deployment held a stale copy. The week closed by cracking a long-standing deployment mystery — a project that had simply never been linked to version control — and retiring two diagnostic techniques that had been producing confident wrong answers.

## WEEK 2026-07-20

sessions: 2
commits: 0

### PRIVATE — source material, do not publish

> Week opened with a short, reboot-truncated session settling the selected-projects public-data question. Their proposal to auto-publish weekly counts while gating prose was accepted in goal but redesigned in transport: counts will be projected at read time from the private weekly_rollups already in Turso, rather than by a new nightly writer into the public tables — preserving the no-automated-writer invariant and avoiding a second drifting copy. A cross-repo reply was drafted for review but not yet sent.

### PUBLIC

A short week spent settling one design question well. A sibling project proposed automatically publishing weekly activity counts while keeping written summaries gated. The goal was accepted; the mechanism was not.

Rather than a nightly job writing into the public tables, the counts are now projected at read time from data already held privately. That preserves the strongest guarantee in the system — that nothing automated ever writes to the public tables — and avoids creating a second copy that can drift from the first. Taking someone's goal seriously while declining their proposed transport is usually the more useful answer.

## WEEK 2026-07-27

sessions: 0
commits: 1

### PRIVATE — source material, do not publish

> The week's centerpiece was ecosystem health: garm's handoff proposal was accepted and shipped same-day as issue #34's first slice (PR #35) — a daily Vercel-cron email that polls garm's deep health endpoint and reports via Resend, carrying an HMAC pause-for-a-week link, a copy-pasteable tune-up prompt, and a per-send Haiku joke. UptimeRobot went live as the deliberately-external pager (8 monitors, garm deep health plus 7 homepages). CI had gone red from unpinned-ruff version drift; pinning to 0.15.22 fixed every push and unstarved deploy. Phase A's PR #33 was rebased onto the pin and is green awaiting merge.

### PUBLIC

The centrepiece was ecosystem health. A proposal arrived and shipped the same day: a daily scheduled email that polls a deep health endpoint across services and reports back, carrying a signed pause-for-a-week link, a copy-pasteable prompt for acting on whatever it finds, and a small joke per send — on the theory that a report people enjoy opening is a report people actually open.

External uptime monitoring went live alongside it, deliberately on separate infrastructure, because a watcher sharing a stack with the thing it watches goes down at exactly the wrong moment. Continuous integration had gone red from an unpinned linter picking up a new release; pinning it fixed every push and un-starved a deploy step that had been silently skipped rather than visibly failing.
