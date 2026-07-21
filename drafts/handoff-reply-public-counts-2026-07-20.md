# DRAFT — reply to selected-projects re: counts/prose split

Status: NOT SENT. Review, then post with:

```
~/.claude/bin/handoff.sh append selected-projects-prompt-lab.md "<entry below>"
```

Decision context (for Nico, next session): three options were weighed 2026-07-20 —
(1) read-time counts projection from private `weekly_rollups` already in Turso (chosen, drafted below);
(2) their literal proposal — a nightly writer inserting counts rows into `public_weekly_rollups` (rejected: weakens the no-automated-writer invariant, second copy can drift, and a mini-side cron reads one machine's local DB → undercounts cross-machine weeks, same blind spot that killed the triage band);
(3) keep the human gate, add a counts-only fast path to `publish_public_draft.py` (rejected as primary: freshness still depends on someone sitting down — the reported failure mode).
Option 1 wins on correctness: zero new writers to public tables, no second copy, always fresh, reads Turso's merged rollups, and it is literally Tier 1 of the agreed `/api/private_history` design — one implementation serves both.

---

### 2026-07-20 prompt-lab → selected-projects: counts split — yes to the goal, different transport

The split is right: counts are structurally leak-proof, prose isn't, and the review gate should sit only where the risk is. We think we can get you the same result with a stronger mechanism than a nightly writer.

Instead of publishing counts rows into `public_weekly_rollups`, `/api/public_history` would compute them at read time: the private `weekly_rollups` table is already in our cloud DB, so for each opted-in project the endpoint emits one row per week with `session_count` / `commit_count` and `public_summary: null`, overlaying the human-published prose rows where they exist. Same envelope you read today — your NULL-summary rendering path covers it, so afaik no change on your side.

Why not the nightly writer: our public tables currently have **no** automated writer, and that property is the strongest guarantee in the system — prose can't leak from a job that doesn't exist. A counts-only cron keeps that true only until someone edits it. Read-time projection keeps the invariant intact, has no second copy to go stale, and is always current (no waiting for tonight's run). Prose-safety is enforced structurally: the query selects numeric columns only, pinned by a test.

Opt-in per project via a flag we administer, seeded from the current allowlist. On your specific asks:

- `split-recording`: we'll opt it in for counts once this lands. Prose publication stays a separate manifest decision.
- `am-i-an-ai`: agreed, we'll drop it from the allowlist.
- Bakery key: `bakerylouise` as the public key works for us (rows fold through our alias layer); we'll confirm when we add it.
- Prose backlog: agreed, no hand-scrubbing 36 weeks. Counts all-time + narrative on recent weeks, as you suggested.

One accuracy caveat to carry into the sparkline: weekly counts are synthesized per-machine and merged last-writer-wins, so cross-machine weeks can undercount. Treat them as cadence, not exact totals.

Does the read-time version give you everything the split was after?
