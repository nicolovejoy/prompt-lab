# Public refresh draft — prompt-lab

<!-- generated: 2026-08-27 -->
<!-- last published week_of: 2026-05-25 -->
<!-- unpublished weeks found: 8 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prompt-lab-2026-08-27.md --apply

The PRIVATE block under each week is unreviewed synthesizer output over raw
prompts. It is source material, not a starting draft — it routinely contains
client and collaborator names, absolute paths, unreleased plans, and vendor
detail. Do not lightly edit it; write the public version from scratch.

Leave a PUBLIC block as `TODO` to skip that week entirely. Skipped weeks stay
unpublished and will reappear in the next draft.

Aim for what a stranger reading a portfolio should see: what was built and why
it mattered. No issue numbers, no people, no infrastructure specifics.

---

## WEEK 2026-06-01

sessions: 2
commits: 5

### PRIVATE — source material, do not publish

> A week focused on closing out the public-data surface migration and its security tail. Mined the prompt-history store to extract a 14-lesson guide on working with Claude, and simplified the public-data exposure model — replacing the read-time allowlist with the published manifest as the single source of truth, adding alias-aware unpublishing, and unpublishing a project no longer meant to be public. Closed out remaining cleanup: removed a stale credential copy from a downstream deployment, verified the public feed live, and rotated the shared database token.

### PUBLIC

Closed out the migration of the public data surface. Replaced a read-time allowlist with a single published manifest as the source of truth for which projects appear publicly. Built new tooling to cleanly unpublish a project. Removed stale credential copies from deployment configuration and rotated database tokens. Also distilled a fourteen-lesson guide on working effectively with AI coding agents, mining the project's own prompt history, to share with a friend.

## WEEK 2026-06-15

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> Spent a single day investigating whether a "work" script exists and whether the project recognizes it. No commits or sessions logged.

### PUBLIC

Spent a brief session investigating the project's own tooling setup — checking what scripts exist and whether the project recognizes them. No code changes.

## WEEK 2026-06-22

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> Closed out the cross-repo handoff migration. The coordination log had moved from unversioned machine-local files into a standalone private repo, and this session verified that migration against actual machine state rather than trusting the write-up — the full pressure-test harness passed. Closed two remaining gaps: added an allow rule so the wrapper runs without a permission prompt, and added a flush for entries appended while offline or blocked by a push conflict, so a stranded entry now surfaces at the next session start instead of sitting unpushed indefinitely.

### PUBLIC

Verified the migration of the cross-project coordination log into its own versioned repository — checked against real machine state rather than trusting the write-up, with the full pressure-test harness passing. Closed the two gaps the audit found, so entries written while offline or blocked by a conflict now surface automatically at the next session start instead of sitting stranded.

## WEEK 2026-06-29

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> Spent a day auditing the build checklist for the cross-repo handoff migration against actual machine state, confirming all major components — the handoff repo, clone, wrapper, hook, and documentation — were in place and passing the full harness. Identified and closed two remaining gaps: added a permission allow rule, and wired session-start tooling to sync any stranded entries. The migration is now on the verge of closure, with one external dependency remaining.

### PUBLIC

The final audit pass on the coordination-log migration: confirmed every component of the build checklist against actual machine state rather than documentation, and closed the last local gaps — tightened permissions and wired session-start tooling to sync any stranded entries — bringing the migration to the edge of closure.

## WEEK 2026-07-13

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> A day focused on housekeeping and architectural clarity rather than feature work. A first-time session-start check confirmed the local tooling was fully in sync with the repository without needing a fresh install. The most substantive discussion centered on why the project isn't yet integrating with the ecosystem's central access-control service: the blocker is the absence of per-user identity, making an authentication migration a prerequisite before any meaningful integration work can begin, with the design already settled. The week closed with a cleanup pass removing 7 stale-but-merged remote branches.

### PUBLIC

Confirmed local tooling was fully in sync with the repository without a reinstall, scoped the prerequisite work for per-user access control on the dashboard (identity has to exist before authorization can mean anything).

## WEEK 2026-08-03

sessions: 1
commits: 7

### PRIVATE — source material, do not publish

> The dashboard copy review drove the day. The overflow menu failed its initial review, prompting a substantial redesign: restructured it into logical groups, promoted and labeled the build stamp, elevated the theme control to the primary row as an icon, and anchored sign-out to the end, plus added a new close-on-outside-click behavior. After the rebuild, all smoke test items passed in both themes on production, including two that had regressed in an earlier pass. The session then shifted to a long-standing data-quality issue: an 80-entry project list had ballooned because project names came from the working directory, minting a new project for every directory ever used. The fix roots project identity in the git repository, collapsing duplicates via aliases and hiding stale directory artifacts.

### PUBLIC

A copy-review pass on the dashboard drove a redesign of its overflow menu — regrouped controls by purpose, promoted the theme toggle to the primary row, anchored sign-out last — and verified it in both themes on production. The bigger fix was data quality: project identity now comes from the git repository rather than the working directory's name, which had been minting a phantom project for every folder ever worked in. An eighty-entry project list collapsed to the real set.

## WEEK 2026-08-10

sessions: 6
commits: 25

### PRIVATE — source material, do not publish

> Fixed a cascade of subtle data-integrity and observability bugs that had been quietly distorting the picture of the lab's own activity. Fixed the review email's day-window bug — "today" now reliably means the completed calendar day — and resolved a delivery conflict by designating a single sender. Found a write-time length filter silently discarding short prompts, making active steering days read as idle, and replaced it with a read-time classifier plus a full backfill of existing rows. Corrected the activity heatmap's broken month labels. Closed the week by moving the nightly report generators off machine-local data onto merged cloud reads, adding a per-machine merge to eliminate clobber races, and catching and fixing a type bug before pushing the branch.

### PUBLIC

Did data-integrity archaeology on the dashboard's own pipeline. Fixed the nightly review email's day-window bug so "today" reliably means the completed calendar day. Discovered a write-time filter silently discarding short prompts — making days spent actively steering agents read as idle — and replaced it with a store-everything-label-at-read approach plus a full backfill. Corrected the activity heatmap's misaligned month labels, and moved the nightly report generators onto merged cloud data so both machines' work appears in a single report.

## WEEK 2026-08-17

sessions: 13
commits: 53

### PRIVATE — source material, do not publish

> The week opened by restoring all four nightly jobs and shipping two changes to production. From there, the week pivoted almost entirely to diagnosing and hardening the nightly pipeline, which turned out to be far more fragile than it appeared: a genuine 6-hour socket hang, an uncaught API timeout, and a wall-clock vs. monotonic clock confusion that would have killed healthy runs every night. Isolated and patched each failure mode with retries, explicit timeout ceilings, and keep-awake infrastructure. A key architectural insight surfaced — a scheduler is not a dependency mechanism — driving the decision to collapse racing nightly agents into a single ordered pipeline. Integration with the ecosystem's central access-control service ran in parallel throughout the week, closed cleanly, and went live in production behind a kill switch.

### PUBLIC

Hardened the nightly pipeline after a puzzling overnight job that appeared to run for hours: the machine had simply been asleep, and the tooling now records wall-clock and awake time separately so that failure mode diagnoses itself. API calls gained retries and bounded timeouts, the dashboard shipped day-page caching and automated-traffic labeling, and completed integration with the ecosystem's central access-control service, verified live in production behind a deliberate kill switch.
