# Current work and deferred decisions

**Next session, start here (2026-09-18):**
1. **#56: review email says "no activity" since Sep 17.** Hypothesis with evidence in the
   issue: since the lean handoff (f8916c0) only the nightly synthesizer writes yesterday's
   `daily_summaries`, and the review stage reads Turso before the publish stage syncs them.
2. **#57: `commits` duplicates on every `/handoff` re-run.** No unique key on `hash`; 393
   extra rows. Back up the DB before the dedup, and pick an attribution rule first.
3. **Codex permissions: installed globally 2026-09-18.** `~/.codex/config.toml` selects the
   `prompt-lab` profile from `workflow/codex-permissions.candidate.toml`, and
   `~/.codex/rules/reviewed.rules` (from `workflow/codex-rules/`) replaced 170 accumulated
   approvals. Backups: `~/.codex/backup-2026-09-18/`. Undo = copy both back and delete
   `reviewed.rules`. Now watch which prompts remain in daily use; a fresh `default.rules`
   will collect new "don't ask again" clicks, so review it. Details:
   `docs/codex-workflow-roadmap.md`. Branch `claude/codex-permissions` is unpushed.
4. **Onboard stars-demo.** It shows up only as a grey "+15 more" entry in the dashboard
   chart (24 prompts on Sep 17). Find out what's missing from the dashboard for it, e.g.
   project metadata or colour, and add it. Also create `stars-demo-prompt-lab.md` in
   `~/src/.handoff` (front-matter `repos: [stars-demo, prompt-lab]`) so its agent can use
   `handoff.sh append`; today that refuses. Stars-demo's Sep 17 entries about orphaned
   `scratch` sessions and ibuild4you DNS currently sit in the ibuild4you channel.

**Workflow status:** `docs/codex-workflow-roadmap.md` is authoritative for current
implementation and remaining gates; `docs/codex-workflow-validation.md` holds
smoke tests/results. The paired Songpath test passed. After reinstalling, the
explicit `$source-command-readup` skill passed its live invocation and stable-ID
checks. The first `$source-command-handoff` correctly stopped on a read-only DB
error. After the narrow installed-helper rule and constrained temporary summary
path were installed, a fresh resume retained session `610`, saved its 604-character
audit, and closed it successfully. Full handoff, fresh-launcher fork, and nightly
checks remain. The deprecated `/prompts:*` interface failed its live check. Broad
permission-profile rollout is separate.

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
touching phrpi or homeassistant.local. Three leftovers from the 2026-08-13 closet move, none
of them our code, all filed in `~/src/.handoff`: a laptop SSH key into HA's add-on (highest
leverage), repointing hardcoded `192.168.5.34` → `homeassistant.local`, and getting
`cloudflared`'s token out of argv on phrpi.

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
- **`#/health` has never been visually verified** (contrast computed, not seen), nor has the
  nav below 640px. https://prompt-labs.org/#/health needs your eyes, not a green test.
- **Beacon fan-out: `prntd`** never got the snippet; `page_views` has zero rows ever for it.
- **Public rollups:** only ibuild4you `2026-05-18` is unpublished — a deliberate skip that
  reappears in every future draft by design.
- **#48 residual:** the "8am" cron is `0 15 * * *` — 8am Pacific in summer, 7am in winter.
  Vercel crons are UTC-only, so this is a choice to make, not a bug to fix.
- Open issues (2026-09-07): **#14** design tokens, **#43** sign-ins panel (gated on a second
  reader), **#9** beacon fan-out, **#49** copy review (this file is the only record of batch
  progress), **#53** iOS chart-tap zoom, **#55** cloudflared token (owner SPAN), **#51**
  unmapped costs (the close rested on a guess).
- Deferred deliberately: UptimeRobot paid plan / real `HEARTBEAT` monitors.


Status snapshot: 2026-09-14. Historical issue claims need verification before action.
