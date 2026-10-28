# Current work and deferred decisions

**Next session, start here (2026-10-08):**
1. **Codex removal, stage 2 done 2026-10-16.** Stage 1 (PR #89) and the docs
   sweep are merged; `docs/remove-codex-plan.md` has the record. The `*-codex`
   clones are gone and the fleet sync manages CLAUDE.md only (2026-10-28). Left:
   `AGENTS.md` still committed in musicforge, person-tracking and split-recording
   (each repo's own call, asked via handoff). The Codex desktop app (installed as
   `ChatGPT.app`, bundle id `com.openai.codex`) and `~/.codex` went to the Trash
   2026-10-28.

**Health email leads with problems (2026-10-27, #98).** The daily email now opens
with "What needs attention": one line per problem, prefixed NEW today, Day N or
Ongoing, or the single line "nothing needs attention" on a clean run. Everything
working sits below a separator; the subject is the top block in one line. The
Turso `health_email_state` key `reported_problems` stores {problem key: first lab
day reported} for the problems in the last email sent; a failure of the newest
run is also stored under its night, so tomorrow's "bad night" line for that same
run is not NEW again. Day N is the Nth lab day the problem has existed, the
first day counting as Day 1: a stale artifact counts from the day after it last
landed, a bad night from the night itself, anything else from the day it was
first seen. Dry runs and paused runs neither read nor write it. A failed read
still sends, marks nothing NEW and skips the write; the write happens only after
a successful send. The memory starts empty, so the first email after deploy
marks every current problem NEW.

**stars-demo is not being onboarded (Nico, 2026-10-09):** it was a one-off and is
mostly done, so it stays a grey "more" entry in the dashboard chart.

**Dashboard active count (2026-10-09).** #82 merged and was checked live: the tile
reads 14, was 40, because a stored default no longer counts a project as active.
#83 merged and deployed the same day: the per-project status menu is gone (active is
simply worked on in the last 7 days; `project_metadata.status` stays in Turso, unused).
Checked in a browser 2026-10-10: the project page shows no status menu. Done.

**Localization (2026-10-10).** The `localize-kit` branch (`/localize` command, French
glossary, shared copy-location rule) is merged to main. Not yet done: run
`workflow/install.sh` and re-sync the shared block fleet-wide (every repo reads
`behind` until then). Second-language plan, incl. the glossary path fix and the
route-groups-to-`[lang]` threshold, is #85. No repo needs Spanish today.

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
**Sunset set 2026-10-17: retire garm in January 2027 unless a second reader has
asked by then (#94 lists what it touches).** The use case (a client or collaborator
seeing some projects but not all) is rated very unlikely.

**`docs/nightly-pipeline-plan.md`: steps 1, 2, 3 and 5 are DONE (2026-08-29).** Step 4 is
mostly absorbed (report catch-up done, reader catch-up optional) and unbuilt beyond that.

**Sleeping-host test: the result is in, and it fails (found 2026-10-27).** Since 10-23 the
laptop has slept across 02:30 on its own. launchd fires the nightly inside a ~10s maintenance
DarkWake with no DNS yet; the gate's 180s budget is monotonic so it ticks only while awake,
accumulates across a dozen dark wakes over 3-13 hours, then gives up and the night exits 1.
Nights 10-23, 10-25 and 10-26 produced nothing; 10-24 resolved after 71s and ran. The
`--- network: resolved after Ns ---` line did appear, so the gate earned its place as
evidence. Decision for Nico, not a one-line fix: either the run holds a sleep assertion for
its duration (`caffeinate -ims -w <pid> -t …`, per the global caffeinate rule), or the gate
waits for a full wake instead of failing. Separate from this: the review email died
2026-10-21..26 on post-wake mornings with a silent-connection read timeout; fixed by
streaming the request (see the trap in CLAUDE.md).

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
Nico has the console steps (2026-10-09) and the numbers are not back yet. A database
that never suspends burns 6 CU-hours a day, about 180 a month; pass is far below that.

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
Batch 2 was sent 2026-10-09 as five items and **none is answered yet**:
- C1, Activity page note: suggested cutting "(aliases are folded into the canonical name)".
- C2, Activity controls, headline and states: fine; lowercase metric tabs against a
  capitalised nav is the only call.
- C3, by-project table footnote: "so the band always reconciles" and "zoom" are the weak words.
- C4, window totals footnote: suggested cutting "one fetch, so switching metric is instant".
- C5, day page: "12p · 3s · 4c" is cryptic, and its error is lowercase where Activity's is not.

**Project-name follow-ups from the 2026-08-05 cleanup, all unconfirmed** — they need Nico's
memory of which directory he was in; the names alone aren't evidence. `koma_art`/`koma-launch`
look like the underscore/dash pair fixed elsewhere; `freevite` (167 prompts) may be `invitekit`
under an older directory name; `spike` (4 prompts) has the shape of the hidden artifacts.

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
