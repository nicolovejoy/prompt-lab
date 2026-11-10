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
`~/.claude/state` no longer protects its row for good. Verified 2026-10-30:
`nightly-pipeline.log` shows `Closed 58` on the stage's first run, and
`--- stage scrub: ok` every night since.

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
env var, not the code default, so check `vercel env ls` before trusting this line. The
August viewer seeds (Pierre → `prompt-lab.prntd`, the brother → a dashboard label) are
withdrawn (2026-10-30): they mattered only with gating on, and garm has dropped them.
**Sunset cancelled 2026-10-29 (#94 closed).** Set 2026-10-17; its trigger was met
when two real per-app admins appeared (Nico's brother on tideline, Eric on
musicforge). ibuild4you's Loop apps design makes Garm the one record of app admins,
and prompt-lab relays it. Done 2026-10-29: inventory ask posted to garm (what exists
vs. new, admin key location, Loop-key trust, `prompt-lab.prntd` vs. bare `prntd`
naming). Neon is settled: `neon-bole-tree` sits in the paid Launch org. Garm
replied the same day: shape approved by Nico, build starting. Relayed to ibuild4you;
notes sent to tideline (correcting our 10-17 "Not Garm" advice), musicforge and
photomirande (new channel). Garm's registry and delegated admins went live 10-29
(garm PR #10), the `loop` key was minted, and Nico created the seven Loop apps; all
relayed, and ibuild4you started Phase B the same day. 2026-10-30: Elijah Lovejoy
(Nico's brother) holds owner on tideline, confirmed by garm; no other owners on
photomirande, byside, prntd or bakerylouise for now. Widget `projectId` notes sent to
prntd and l6-music only (Nico skipped byside and bakerylouise; old ids stay aliased).
Tideline will still need a `tideline`-scoped consumer key. Next: ibuild4you posts when
Phase B reaches preview.

**`docs/nightly-pipeline-plan.md`: steps 1, 2, 3 and 5 are DONE (2026-08-29).** Step 4 is
mostly absorbed (report catch-up done, reader catch-up optional) and unbuilt beyond that.

**Sleeping-host nights: decided and shipped (#97, 2026-10-27).** launchd fires the
nightly inside a ~10s maintenance dark wake with no DNS, and the old 180s gate budget
ran out across a dozen of those (nights 10-23, -25, -26 produced nothing). The gate now
waits until 11:00 local (`NETWORK_DEADLINE_HOUR`) and never gives up in under 180s
awake, so the run happens when the lid opens; a laptop shut past 11:00 is a missed
night that the next night catches up. #100 (2026-10-28) added a retry for a stream
dropped mid-response, which killed the 10-28 review stage.

**Confirmed in the log 2026-10-30:** the nights of 10-29 and 10-30 both show
`--- network: resolved immediately ---` and `stage review: ok` (122s, 133s). Nico
confirmed 2026-11-02 that the review emails are arriving again.

Also unverified until it happens: the health-email changes are Vercel-side code reading Turso,
so the first real morning email carrying a `nightly_runs` row is their acceptance test — **and
it does not run until the merge is pushed and deployed.**

**mini-rescue curation — walked 2026-11-03; four folders stay.** `~/src/mini-rescue/` now
holds freevite (= invitekit under its old name), roll-your-own and skitrack-ntzb-poc
(deliberately unpushed, settled 2026-08-17; Nico 2026-11-03: keep them as folders), plus
ntz-conveyor, waiting on person-tracking (handoff 2026-11-03): its gitignored `db.sqlite3`
holds real run/turn/gaze data, so it is kept until they confirm it lives elsewhere. Removed
to the Trash 2026-11-03: study-scheduler (mothballed), bookstore, eli-example,
lilypond-lead-sheets, spread-eagle, musicforge, notemaxxing (RLS stash dropped),
robot-orchestra (stash dropped), rock-art-fab. rock-art-fab's gitignored `drawings/` and
`sculptures/` (~55 MB, the only copy) were first copied into `~/src/rock-art-fab` and
checked file by file. Lesson: a clean `git status` is not "nothing unique" — check
`git status --ignored` before deleting any rescued checkout.

**Neon autosuspend fixes: confirmed, closed 2026-11-03.** September is unrecoverable
(console monitoring keeps about a week), but October (#91, ~15 CU-h for garm by the 17th) and
Nov 1–3 (`neonctl projects get`: garm 2.69 CU-h, ~29/month pace; byside 0.00, last active
24 days ago) are far below the ~180/month a never-suspending database burns. Per-project
numbers for the current month: `neonctl projects get <id> --org-id org-spring-cherry-36158724`.

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
Batch 2 closed 2026-11-02 (#104): C1, C3, C4 and C5 edited as proposed, C2 kept
lowercase. Batch 3 closed 2026-11-03: items 12–25 all answered (proposals
accepted; 13, 20, 22, 24 kept as-is; item 25's classifier chrome was already
gone, only the "tracked" wording remained). Batch 4 closed 2026-11-03 too:
items 26–40 answered (27, 32, 35, 39 kept; 28/30 shortened on review;
"suppressed" dropped because the API sets it on the same condition as
"paused"). About stays behind More; that open question is closed. #49 is
complete and can be closed.

**Project-name follow-ups from the 2026-08-05 cleanup: closed 2026-11-02.** Nico
confirmed `freevite` became `invitekit` and `koma_art` became `koma-launch`; both are
now aliases (`scripts/alias.py`) and synced to Turso, where the old-name rows still
live (the local DB no longer has them). `spike` (4 prompts) is left alone.

Open, from the 2026-08-02 uptime/health thread and the issue backlog:
- **`#/health` works on desktop (Nico, 2026-10-09) and on a phone.** The phone layout
  was covered by #76 (`health`, `health-cards` in `scripts/phone/checks.mjs`); the full
  phone run on 2026-11-04 passed 404/404 and the screenshot was checked by eye.
- **Beacon interface (2026-11-04, #110 merged, deployed).** `/api/beacon` is a documented contract (`docs/beacon.md`): new `nav` event for in-app views (stored with no visitor hash, day-level date, random id), ID-like path segments become `:id`, sites can no longer post `login`, frozen `beacon-v1.js` with SRI (headers verified live). prntd's #363 tag is live; their own call with `nav` is in progress and they post the ship date, then check #/visitors. The first `--apply` backfill is done (no unscrubbed old-rule paths remain). Widened ID rule (emails, key:value such as `name%3A<person>`, dashed IDs, IDs inside slugs) merged as #111 2026-11-04 and its `--apply` backfill ran the same day (5 paths / 8 rows, including 3 person-name paths); a dry run afterwards shows 0 paths to change. #109 closed 2026-11-04: sites report `nav` themselves.
- **Design review of prompt-labs.org and its emails: all merged 2026-11-05.** #112 font-size
  scale, #113 pass 1 (colour roles, chart/spacing/radius tokens, one 640px breakpoint, a11y),
  #114 pass 2 (`.chip`, `.btn`, `.page-title`, role-aware admin tab bar) plus `recap`, #115
  recap v2 (checked live in a new tab 2026-11-05), #116 emails R10-R12 (model returns content,
  `send-review.py` renders it), #117 review subject built in code (`Work recap · Thu 5 Nov`).
  Facts: `docs/design-review/facts.md`; rulings: `docs/design-review/review.md`; screenshots
  outside the repo in `~/.claude/state/prompt-lab/design-review/`. Roving tabindex on chart bars
  is #119 (each chart one tab stop, arrows move between bars). Parked follow-ups: iOS standalone status bar is
  `black-translucent` so `theme-color` may not show, optional dark `--chart-1` → `#5558e6`.
  Next check: read the first few review emails built from #116/#117. #118 checked
  2026-11-09: the `review_snapshots` rows for 11-06 to 11-09 all carry a `sent_id`.
- **Public rollups:** only ibuild4you `2026-05-18` is unpublished — a deliberate skip that
  reappears in every future draft by design.
- **#48 residual, settled (Nico, 2026-11-04): leave it.** The "8am" cron is `0 15 * * *`,
  8am Pacific in summer and 7am in winter; Vercel crons are UTC-only. Not a bug.
- Open issues (checked 2026-11-09): **#43** sign-ins panel (gated on a second
  reader), **#9** beacon fan-out (prntd asked via handoff 2026-11-03), **#85** localize
  second language. Closed: #49 2026-11-03 (all four batches), #51 by the unmapped-costs PR,
  #91 Neon fees and #109 beacon navigations 2026-11-04, #14 design tokens 2026-11-05.
- **WindowServer crash on the laptop, 2026-11-09 15:55 PST: cause still open.** WindowServer
  held 64,414 of about 65,500 IOSurfaces (the kernel's own tally, ten seconds before the
  abort) and died on a 390x844 window capture requested by Playwright's WebKit build.
  Headless WebKit and Edge runs did not reproduce any growth on the fresh WindowServer with
  the display on. The system log shows about 226,000 failed IOSurface lookups from
  WindowServer that day, only while the display was on and before any Playwright run. Two
  suspects remain: a WindowServer fault unrelated to tests, or WebKit window captures made
  while the display is off (unattended suites ran from 13:31 to the crash with the display
  off). Interim guidance sent to the other sessions: Edge and Chromium unrestricted, no
  unattended WebKit suites. Gauge: `ioclasscount IOSurface` (a few hundred is normal).
  Evidence: `~/.claude/state/prompt-lab/windowserver-crash-2026-11-09/`. Not yet done: a
  display-off repeat of the measurement, a Feedback Assistant report, a recurring logger.
- **Playwright 1.60.0 cannot install on GitHub's ubuntu-26.04 runners (2026-11-09).**
  `ubuntu-latest` moved; 1.62.1 and later install fine. Red: split-recording, musicforge,
  prntd; bakerylouise-v1 fails on its next run. Each was told via handoff to bump Playwright
  (stopgap: `runs-on: ubuntu-24.04`). prompt-lab's CI runs no Playwright.
- **Unmapped API spend (#51, 2026-11-03).** The Admin API workspace list is the source of
  workspace names: the August "assumed prompt-lab" workspace is recountly (→ raconte), the
  one unmapped workspace was byside, and elusion was mapped ahead of its first spend. A new
  workspace still lands `__unmapped__`, but now the health email says so (30-day window)
  and Costs shows it as "Unmapped". Fix path: add it to `scripts/seed_project_workspaces.py`,
  run it with `--remap`, then a FULL `sync_to_turso.py` — the nightly `--days 7` sync never
  carries older remapped rows to Turso.
- Deferred deliberately: UptimeRobot paid plan / real `HEARTBEAT` monitors.


Status snapshot: 2026-09-14. Historical issue claims need verification before action.
