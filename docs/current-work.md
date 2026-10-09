# Current work and deferred decisions

**Next session, start here (2026-10-08):**
1. **Codex permission tuning — applied 2026-09-25, see the status block at the top of
   `docs/codex-permission-tuning-plan.md`.** Reviewed rules installed 2026-09-25 after
   Nico's rulings (gh writes prompt, xcodebuild build/test prompt). zprofile edited and Codex resolves node with no prefix (v20, its
   terminal's nvm default); a sandboxed Codex `handoff.sh append` pushed with exit 0.
   Left open: re-measure on ~2026-10-02: `default.rules` should have gained ≤ 3
   rules and no `zsh -lc` / `PATH=` escalations should remain (tally method in the plan).
   Tally run 2026-10-09: 21 escalation requests in 18 sessions since the fix, against
   118 in the five days before it. 20 were songpath-codex's first two days (09-26,
   09-27); none was wrapped in `zsh -lc` or `PATH=` (two used `env -u PGHOST -u PGPORT`),
   and none came from a worktree or scratch clone. **Not a verdict yet:** Codex ran in
   a repo on only four days (09-25 to 09-28) and musicforge-codex, the source of the
   118, had one session. Re-run after a real week of musicforge Codex use.
   `default.rules` fails its criterion on the letter: 5 rules, all new (the two prune
   survivors moved to `reviewed.rules`, so the earlier "+3" was a miscount), all from
   09-26/27. Three are one-off literals (`touch` of a resync marker, `ps -axo`, one
   `npm run e2e --grep`), one is the `gc-write.sh register-session` wrapper the
   bookkeeping hook replaced on 09-27, and one is `npx playwright test` in the user
   layer, which the 09-25 ruling allowed per repo only. Pruning them is Nico's call.
2. **Codex host bookkeeping is live in all five `~/src/*-codex` clones (2026-09-27).**
   PR #68 merged 2026-09-25 (`ec0385f`); the live pilot passed in prompt-lab-codex
   (session 885; details under "Live pilot" in `docs/codex-workflow-validation.md`);
   `~/.claude/codex-bookkeeping-step3` accepts all five clones and songpath-codex
   registered (session 889). A new clone must be added by restaging (new versioned dir)
   + repointing `~/.codex/hooks.json` — outside the list, every Codex turn gets a Stop
   block. Codex Desktop is unverified. Still untested: resume/fork, Claude-pair (Step 4).
3. **Codex permissions: installed globally 2026-09-18.** `~/.codex/config.toml` selects the
   `prompt-lab` profile from `workflow/codex-permissions.candidate.toml`, and
   `~/.codex/rules/reviewed.rules` (from `workflow/codex-rules/`) replaced 170 accumulated
   approvals. Backups: `~/.codex/backup-2026-09-18/`; any rollback now requires the
   policy-compatibility review in the roadmap. Watch which prompts remain in daily
   use; a fresh `default.rules`
   will collect new "don't ask again" clicks, so review it. **Acceptance reopened
   2026-09-19:** MusicForge reported registration blocked by DB permissions and
   handoff correctly stopped. Further rollout is on hold pending the reviewed
   bookkeeping interface and staged end-to-end gates. Details:
   `docs/codex-workflow-roadmap.md`. Branch `claude/codex-permissions` is unpushed.

**stars-demo is not being onboarded (Nico, 2026-10-09):** it was a one-off and is
mostly done, so it stays a grey "more" entry in the dashboard chart.

**Session-row housekeeping (2026-10-08).** The orphaned-`scratch` fix merged as #80
and its helper is installed under `~/.claude/bin`. 351 stale open rows were closed by
hand the same day (list: `~/.claude/state/closed-stale-sessions-2026-10-08.txt`).
#81 merged 2026-10-09 at 07:45 PDT, after that morning's 02:30 run: the nightly now
opens with a `scrub` stage that closes rows idle for a week, and a pointer file in
`~/.claude/state` no longer protects its row for good. **Still to verify:** the
2026-10-10 run is the first with the stage. `nightly-pipeline.log` should show
`--- stage scrub: ok` and `Closed 58` (a dry run on 2026-10-09 found 58 of 60 open
rows due). Until then those 58 rows stay open.

**Mini shut down 2026-09-25.** Idle for weeks: no jobs, no containers, no handoff clone; only the parked `disabled-promptlab-20260820` LaunchAgents. Clean shutdown over ssh. Nothing depends on it. Possible future role: an independent watcher for the "cron dead" heartbeat hole. Details in memory `user_two_machines.md`.

**Workflow status (2026-09-19):** `docs/codex-workflow-roadmap.md` is authoritative for current
implementation and remaining gates; `docs/codex-workflow-validation.md` holds
smoke tests/results. The paired Songpath test passed. After reinstalling, the
explicit `$source-command-readup` skill passed its live invocation and stable-ID
checks. The first `$source-command-handoff` correctly stopped on a read-only DB
error. After the narrow installed-helper rule and constrained temporary summary
path were installed, a fresh resume retained session `610`, saved its 604-character
audit, and closed it successfully. That zero-commit test preceded the global
permission-profile install; MusicForge's new registration failure reopens
bookkeeping acceptance. Direct SQLite commit capture also remains outside the
helper. Claude's fake-DB probe confirmed sandboxed registration failure and a
prompt-hook-created row; it did not execute escalation. The explicit deny policy
rules out that route. The roadmap now proposes host-injected identity and validated
hook-side handoff requests, with receipts after persistence. The real CLI lifecycle
fixture passed with a local model stub: identity arrived, Stop saved fake data and
continued once to deliver a receipt, and a wrong ID was rejected without saving.
Production-profile acceptance was not tested (nested macOS sandboxing failed).
Next: implement the protected request consumer and replay/receipt contract against
the existing identity resolver. This is not an installed fix.
Full handoff, fresh-launcher
fork, and nightly checks remain. The deprecated `/prompts:*` interface failed its
live check.

**Shared-conventions rollout:** the checker now hashes the actual body and separates
clean `behind` copies from `tampered` blocks, which apply refuses to overwrite. A
dry-run fleet inventory covers both `CLAUDE.md` and `AGENTS.md`; its explicit apply
mode updates only verified behind/missing blocks and never commits sibling repos.
The canonical preamble is now target-neutral. Install these guards before asking
individual repo owners to refresh their blocks.

**1Password preference:** when Nico requests a new item, create its secret field with the
literal placeholder `replace-this-value`; Nico pastes the real value into 1Password. `env.tpl`
files contain references and should remain readable. Do not infer that arbitrary
agent-selected commands can use secrets without being able to expose them. Start with
human-run secret operations; proposed first protected helper is read-only operational
status, deployment later.

**Garm: HARDEN-THEN-FREEZE — Nico's decision 2026-08-27, don't re-litigate the unwind
question.** `GARM_GATING` stays **off**, `READER_EMAILS` is the live gate — "off" is a Vercel
env var, not the code default, so check `vercel env ls` before trusting this line. Grant
seeding (Pierre → `prompt-lab.prntd`) is deferred and blocks nothing. Revisit trigger: a real
second user who needs actual access management, not "might someday."

**`docs/nightly-pipeline-plan.md`: steps 1, 2, 3 and 5 are DONE (2026-08-29).** Step 4 is
mostly absorbed (report catch-up done, reader catch-up optional) and unbuilt beyond that.

**Still outstanding: step 2's sleeping-host test**, and it needs a real overnight, not a
healthy awake host (an awake laptop passes either way — that is why it needs staging). With
the machine deliberately asleep across 02:30, confirm one wake produces one run in the correct
order and Turso's newest `review_snapshots` date equals the run date. The network gate sits in
front of it now, so the run should print `--- network: resolved after Ns ---` rather than dying
on `gaierror` — that line is itself the evidence the gate earns its place.
First attempt is the night of 2026-10-09. Idle sleep will not do it: `pmset -g log`
shows no sleep or wake event since 2026-10-07 (a `PreventUserIdleSystemSleep`
assertion from `Siri AI` has been held since then), which is why the 10-08 and 10-09
runs started at 02:30:04 sharp. The laptop has to be put to sleep by hand.

Also unverified until it happens: the health-email changes are Vercel-side code reading Turso,
so the first real morning email carrying a `nightly_runs` row is their acceptance test — **and
it does not run until the merge is pushed and deployed.**

**mini-rescue curation — open, unhurried.** `~/src/mini-rescue/` holds 13 rescued repos; walk
them at leisure, merge-or-discard, delete each folder as judged (the dir emptying is the
meter). Settled 2026-08-17, don't revisit: freevite (= invitekit under its old name),
roll-your-own and skitrack-ntzb-poc are deliberately unpushed.

**Check the September Neon CU numbers for garm (`neon-bole-tree`) and byside.** Both were
burned by prompt-lab's own 5-min deep health poll never letting Neon's free tier autosuspend;
fixed 2026-08-14 (byside) and 2026-08-18 (garm). Nothing alarms on the number.

**Per-Pi service inventory: `docs/pi-inventory.md`** — prompt-lab owns it; read it before
touching phrpi or homeassistant.local. Two leftovers from the 2026-08-13 closet move, neither
of them our code, both filed in `~/src/.handoff`: a laptop SSH key into HA's add-on (highest
leverage) and repointing hardcoded `192.168.5.34` → `homeassistant.local`. The third,
`cloudflared`'s token in argv, was fixed by SPAN 2026-09-19 and the token rotated the same
day (see the inventory).

**Copy review (#49) — batches 2–4 remain**, batch 1 closed 2026-08-05. **Track which items
were actually answered, not which batch was sent** — Nico answers by number and often stops
mid-batch; the first pass lost two items that way. Left: batch 2 (Activity + day page), batch
3 (Costs, Visitors, Todos), batch 4 (Health, About, project pages). Open question: a plain
`About` button in the primary row may beat the `More` panel.

**Project-name follow-ups from the 2026-08-05 cleanup, all unconfirmed** — they need Nico's
memory of which directory he was in; the names alone aren't evidence. `koma_art`/`koma-launch`
look like the underscore/dash pair fixed elsewhere; `freevite` (167 prompts) may be `invitekit`
under an older directory name; `spike` (4 prompts) has the shape of the hidden artifacts.

**`ACTIVE · N` counts hidden projects.** `activeCount` is `activeList.length` with no `private`
filter (`web/index.html:1308-1310`), and it feeds the KPI tile (`:1334`) and the `Active · N`
header (`:1421`) — the home screen read `37` with 16 shown. One filter fixes it, but the
semantics are a real choice: excluding private is wrong the day a genuine project is marked
private. Alternative is `37 · 16 shown`. Undecided.

Open, from the 2026-08-02 uptime/health thread and the issue backlog:
- **`#/health` was seen by Nico on desktop 2026-10-09** (dark theme; 11/11 targets up, all
  6 heartbeats fresh) and works. The nav below 640px has still not been looked at.
- **Beacon fan-out: `prntd`** never got the snippet; `page_views` has zero rows ever for it.
- **Public rollups:** only ibuild4you `2026-05-18` is unpublished — a deliberate skip that
  reappears in every future draft by design.
- **#48 residual:** the "8am" cron is `0 15 * * *` — 8am Pacific in summer, 7am in winter.
  Vercel crons are UTC-only, so this is a choice to make, not a bug to fix.
- Open issues (2026-10-08): **#14** design tokens, **#43** sign-ins panel (gated on a second
  reader), **#9** beacon fan-out, **#49** copy review (this file is the only record of batch
  progress), **#51** unmapped costs (the close rested on a guess). #53 (iOS chart-tap zoom)
  closed 2026-09-28 with #76.
- Deferred deliberately: UptimeRobot paid plan / real `HEARTBEAT` monitors.


Status snapshot: 2026-09-14. Historical issue claims need verification before action.
