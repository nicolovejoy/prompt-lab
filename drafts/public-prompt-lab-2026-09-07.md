# Public refresh draft — prompt-lab

<!-- generated: 2026-09-07 -->
<!-- last published week_of: 2026-08-17 -->
<!-- unpublished weeks found: 2 -->

Rewrite each **PUBLIC** block below into text safe for an unauthenticated,
permanently-public endpoint, then commit this file and run:

    .venv/bin/python scripts/publish_public_draft.py drafts/public-prompt-lab-2026-09-07.md --apply

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

sessions: 10
commits: 23

### PRIVATE — source material, do not publish

> The week opened with infrastructure and coordination concerns — GitHub Actions minutes at 90% capacity, Mac mini sleep/DHCP issues affecting shared overnight jobs, and the establishment of an async agent-to-agent handoff channel for cross-repo communication. A security-focused commit review mid-week surfaced a ranked vulnerability list that prompted a significant architectural decision: rather than unwinding Garm, the team chose to harden-then-freeze it, deferring grants and filing issue #55 for the top vulnerability (a plaintext tunnel token). On the content side, the public-refresh backlog was fully cleared, bringing every allowlisted project to zero unpublished weeks, and the narrative style guide was tightened with a context-sensitive redundancy rule. The week closed with two substantial nightly-pipeline improvements: a proper nightly_runs record written to Turso as an independent post-publish step, and a guard against upserts silently destroying prose — a bug that had already wiped 207 rollups before being caught. A whole-branch review on Friday caught a critical ordering defect that per-task reviews had missed, where pipeline stage setup ran unguarded and a local DB failure could have silently skipped an entire night's run.

### PUBLIC

Stood up a cross-repo handoff channel: a private git repo of append-only notes that each repo's session-start hook pulls and injects, so agents in sibling repos coordinate without pull requests across the boundary. Cleared the public-refresh backlog for every allowlisted project and tightened the narrative style guide. A security review of the Garm access-control layer produced a ranked vulnerability list; decided to harden Garm and freeze its rollout rather than unwind it, with the plaintext tunnel token as the top fix. The nightly pipeline now writes a run record to Turso as its own step after publishing, and daily-summary and weekly-rollup upserts archive the replaced row first, after a bug silently wiped 207 rollups. A whole-branch review caught an ordering defect where pipeline stage setup ran unguarded and a local SQLite failure could have skipped a whole night silently.

## WEEK 2026-08-31

sessions: 2
commits: 11

### PRIVATE — source material, do not publish

> This was a single-day but high-impact week on prompt-lab, focused on diagnosing and fixing two compounding reliability problems with the nightly review pipeline. The system prompt for the review email was rewritten after a real-world edit revealed a buried instruction — targeting non-engineer readers — that was silently generating all the verbose, jargon-heavy prose being cut in review. Separately, a DNS timing bug was uncovered: launchd was firing the 2:30 AM job before the network was ready, causing four of seven nights to fail silently — and critically, the synthesizer, pipeline, and health email were all independently masking those failures by reporting dead nights as quiet ones. All three were patched via subagent-driven development and deployed. The week closed with a check on an unmerged cloud-session plan for a Resend paid-to-free consolidation, where three of its core premises turned out to be incorrect — leaving that work to be re-scoped.

### PUBLIC

Fixed two compounding problems in the nightly review email. A buried instruction in the Claude system prompt targeted non-engineer readers and had been generating the verbose prose cut in every review; rewrote the prompt. Separately, launchd fired the 2:30 AM job before DNS was up after the laptop woke, so four of seven nights failed, and the synthesizer, the pipeline and the health email each reported those dead nights as quiet ones. Added a network gate ahead of the pipeline and changed the health check to grade a window of runs, not the newest row. Checked an unmerged plan to drop Resend from the paid to the free tier and found three of its premises wrong; that work is re-scoped. Next: confirm the wake fix on a real sleeping-host night.