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

> A week focused on closing out the public-data surface migration and its security tail. Mid-week, mined the prompt-history store to extract a 14-lesson 'how to work with Claude' guide and simplified the public-data exposure model — removing the public_history read-time allowlist in favor of the selected-projects MDX manifest as the single source of truth, adding an alias-aware unpublish_public.py, and unpublishing byside. End of week, executed the remaining manual cleanup: deleted the stale HISTORY_TURSO_* copy of the database token from the downstream Vercel project, verified the public musicforge Evolution feed live via Playwright, and rotated the ground-control Turso token across web's Vercel targets. Surfaced that token invalidation is per-group (shared with pianohouse + prntd), deferring the full 3-DB rotation to issue #5.

### PUBLIC

Closed out the migration of the public data surface. A read-time allowlist was replaced with a single published manifest as the source of truth for which projects appear publicly, tooling was added to cleanly unpublish a project, and the security tail was finished: stale credential copies removed from deployment configuration and database tokens rotated. Also distilled a fourteen-lesson guide on working effectively with AI coding agents, mined from the project's own prompt history.

## WEEK 2026-06-15

sessions: 0
commits: 0

### PRIVATE — source material, do not publish

> This was a light, exploratory week for the prompt-lab project, with only a single active day recorded. The developer's focus was investigatory in nature — specifically looking into whether a "work" script exists or is recognized within the project context. No commits or sessions were logged, indicating the week was spent getting oriented rather than making concrete changes. The lack of output suggests this may have been groundwork for identifying gaps or next steps in the project's tooling or workflow setup.

### PUBLIC

TODO

## WEEK 2026-06-22

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> A single working day in this week, spent closing out the cross-repo handoff migration (issue #7). The coordination log had moved from unversioned machine-local files into the standalone private handoff repo, and this session verified that migration against actual state on the laptop rather than trusting the write-up — the 26/26 pressure-test harness passed. Two gaps remained and both were closed: the wrapper needed an allow rule so it would run without a permission prompt, and nothing was flushing entries that had been appended while offline or blocked by a push conflict. Wiring that flush into /readup means a stranded entry surfaces at the next session start instead of sitting unpushed indefinitely.

### PUBLIC

Verified the migration of the cross-project coordination log into its own versioned repository — checked against real machine state rather than trusting the write-up, with the full pressure-test harness passing. Closed the two gaps the audit found, so entries written while offline or blocked by a conflict now surface automatically at the next session start instead of sitting stranded.

## WEEK 2026-06-29

sessions: 1
commits: 1

### PRIVATE — source material, do not publish

> This was a focused, single-day week on prompt-lab dedicated entirely to closing out issue #7 (cross-repo handoff migration). The day was spent auditing the build checklist against actual laptop state, confirming that all major components — handoff repo, clone, wrapper, hook, and CLAUDE.md stanzas — were in place and passing the full 26/26 harness. With the audit complete, two remaining laptop-side gaps were identified and closed: an allow rule for handoff.sh was added to settings.json, and the /readup flow was wired to trigger a sync so local-only and offline entries don't get stranded. The issue is now on the verge of closure, with only one external dependency remaining — confirming that mini ran install.sh.

### PUBLIC

The final audit pass on the coordination-log migration: every component of the build checklist was confirmed against actual machine state rather than documentation, and the last local gaps were closed — permissions tightened and session-start tooling wired to sync any stranded entries — bringing the migration to the edge of closure.

## WEEK 2026-07-13

sessions: 1
commits: 0

### PRIVATE — source material, do not publish

> This was a light, single-day week focused on housekeeping and architectural clarity rather than feature work. The session began with a first-time /readup and /resync --light on the laptop, which came back clean — confirming the local harness (bin scripts, shell config, settings.json hooks) is fully in sync with the repo without needing a fresh install.sh run. The most substantive discussion centered on why prompt-lab isn't yet integrating Garm: the blocker is the absence of per-user identity, making the OAuth migration a prerequisite before any meaningful Garm work can begin. That effort has been scoped at ~3-4 hours of Sonnet-appropriate work, with the design already settled and tracked in docs/garm-needs-assessment.md. The week closed with a cleanup pass that removed 7 stale-but-merged remote branches from origin.

### PUBLIC

A light maintenance week: confirmed local tooling was fully in sync with the repository without a reinstall, scoped the prerequisite work for per-user access control on the dashboard (identity has to exist before authorization can mean anything), and pruned a set of stale merged branches.

## WEEK 2026-08-03

sessions: 1
commits: 7

### PRIVATE — source material, do not publish

> This was a focused, high-output single-day week on prompt-lab, driven entirely by the dashboard copy review (#49). The More panel failed its initial review and was substantially redesigned — restructured into logical groups, with the build stamp promoted and labeled, the theme control elevated to the primary row as an icon, and Log out anchored to the end, along with a new close-on-outside-click behavior. After the rebuild, all smoke test items passed in both themes on production, including two that had regressed in an earlier pass. The session then shifted to a long-standing data quality issue: an 80-entry project list had ballooned because the prompt-log hook was deriving project names from the working directory basename, minting a new project for every directory ever used. The fix roots project identity in the git repo, with 8 aliases collapsing duplicates and 23 directory artifacts hidden. The day closed out with housekeeping — four stale CLAUDE.md claims corrected and two previously unsummarized days backfilled.

### PUBLIC

A copy-review pass on the dashboard drove a redesign of its overflow menu — controls regrouped by purpose, the theme toggle promoted to the primary row, sign-out anchored last — verified in both themes on production. The bigger fix was data quality: project identity is now derived from the git repository rather than the working directory's name, which had been minting a phantom project for every folder ever worked in. An eighty-entry project list collapsed to the real set.

## WEEK 2026-08-10

sessions: 6
commits: 25

### PRIVATE — source material, do not publish

> The week was defined by fixing a cascade of subtle data-integrity and observability bugs that had been quietly distorting the picture of the lab's own activity. Early in the week, a TDD pass corrected the review email's 2:30am window bug — "today" now reliably means the completed Pacific lab-day — and a delivery conflict was resolved by designating the mini as the sole sender. Mid-week brought a closet networking audit that corrected a second-hand inventory, surfaced Home Assistant's dual-homed setup, and converted a pending service deletion into a token rotation. Thursday's work was the most sweeping: the write-time length filter in log-prompt.sh was removed after it was identified as the cause of shaped data loss — approvals were being systematically discarded, making active steering days read as idle — and replaced with a read-time classifier that backfilled all 1,353 existing rows; the trajectory heatmap's broken month labels were also corrected. The week closed with a full end-to-end execution of the Turso-readers plan, moving send-review.py and generate-report.py off machine-local raw data onto merged Turso reads, adding a per-machine parts table with deterministic merge to eliminate clobber races, and catching and fixing a critical type bug in generate-report.py before the branch was pushed.

### PUBLIC

A week of data-integrity archaeology on the dashboard's own pipeline. The nightly review email's day-window bug was fixed so "today" reliably means the completed calendar day. A write-time filter was discovered silently discarding short prompts — making days spent actively steering agents read as idle — and replaced with store-everything-label-at-read plus a full backfill. The activity heatmap's misaligned month labels were corrected, and the nightly report generators moved onto merged cloud data so both machines' work appears in a single report.

## WEEK 2026-08-17

sessions: 13
commits: 53

### PRIVATE — source material, do not publish

> The week opened with a high-output execution day driven by parallel agents — merging the turso-readers refactor, restoring all four nightly jobs on the mini, and shipping two PRs (#50 and #52) to production. From there, the week pivoted almost entirely to diagnosing and hardening the nightly pipeline, which turned out to be far more fragile than it appeared: a genuine 6-hour socket hang, an uncaught API timeout, and a wall-clock vs. monotonic clock confusion that would have killed healthy runs every night. Each failure mode was isolated and patched with retries, explicit timeout ceilings, and caffeinate-based infrastructure. Midweek surfaced a key architectural insight — a scheduler is not a dependency mechanism — which drove the decision to collapse racing nightly agents into a single ordered pipeline, documented in docs/nightly-pipeline-plan.md. The Garm-consumer integration ran in parallel throughout the week: the team chased the grants-list endpoint live, fixed 5 real lint failures blocking CI, and navigated a Vercel permission wall by handing off exact deploy commands to Nico. The week closed cleanly on Sunday with PR #54 squash-merged, GARM_KEY/GARM_GATING configured, and the feature verified live in production.

### PUBLIC

Hardened the nightly pipeline after a puzzling overnight job that appeared to run for hours: the machine had simply been asleep, and the tooling now records wall-clock and awake time separately so that failure mode diagnoses itself. API calls gained retries and bounded timeouts, the dashboard shipped day-page caching and automated-traffic labeling, and integration with the ecosystem's central access-control service was completed and verified live — deliberately deployed behind a kill switch.
