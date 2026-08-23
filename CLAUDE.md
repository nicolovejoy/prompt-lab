# prompt-lab

**Prompt Lab** — overview dashboard for tracking agent sessions, todos, and themes across projects. Data from `~/.claude/prompt-history.db`.

## Run

```bash
.venv/bin/python mobile/serve.py  # local mobile PWA → localhost:8080
```

The Flask local dashboard (`dashboard/`) was retired 2026-05-28 — it had gone ~3 months stale and none of the cost-tracking work landed there. The cloud dashboard (`web/`) is the single canonical UI. `todos.py` is kept as the shared scanner but is currently unwired (its only consumer was the local dashboard); rewire it into `web/` when todos return to the UI.

## Deploy (cloud dashboard)

```bash
cd web && vercel --prod
```

Env vars needed in Vercel: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `AUTH_SECRET`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` (read-only PAT for the Todos page; optional `GITHUB_USER`, defaults to `nicolovejoy`)

To self-host: fork the repo, create a Turso database, set the env vars above, deploy `web/` to Vercel.

## Architecture

- `store/` — backend-agnostic KnowledgeStore ABC + SQLite (default) and Turso implementations
- `claude_api.py` — shared Claude API utilities, centralized env loading (.env, .env.local)
- `synthesizer.py` — nightly: daily summaries, weekly rollups, project snapshots
- `send-review.py` — nightly email via Resend; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `generate-report.py` — bi-monthly markdown report; reads processed tables from Turso (`get_store("turso")`); snapshot writes stay local and sync as before
- `sync_to_turso.py` — pushes processed tables to Turso (no raw prompts)
- `web/` — cloud dashboard (Preact+HTM + Vercel Python serverless), auth-protected, reads from Turso
- `mobile/` — legacy local mobile PWA, reads from Turso directly
- `/handoff` generates daily summaries + weekly rollups inline (no API call)
- `/ask` queries the knowledge store with natural language
- `workflow/` — slash commands (`commands/`), hooks, and `statusline-command.sh` (copy to `~/.claude/`)
- **Data & access model: see `docs/data-and-access.md`** — the single coherent description of the three storage tiers (raw/private, processed/private, public), how public vs private is differentiated, the two-tier cloud auth, and how secrets grant access. Read it first when reasoning about what's stored where or who can see it.
- `web/api/public_history.py` — unauthenticated `GET /api/public_history?project=<name>` for portfolio About pages. No read-time allowlist: it serves whatever rows exist in `public_session_summaries` / `public_weekly_rollups`, which are safe-by-construction (written only by the reviewed, git-committed draft-to-artifact flow — `scripts/draft_public_refresh.py` → human review → `scripts/publish_public_draft.py`, plus the original `scripts/backfill_public_*.py` one-shots — never by `/handoff`, the synthesizer, or raw sync). The allowlist (`docs/public-allowlist.txt`) is an 8-key **write-time publish gate**, not a read gate — `publish_public_draft.py` refuses to publish an off-list project, and `check_public_allowlist.py` audits published rows against it. Current keys: `bakerylouise, ibuild4you, musicforge, prntd, prompt-lab, selected-projects, showcase, songscribe` (`am-i-an-ai` dropped 2026-07-21 when the site removed lojong and its rows were unpublished). The table `project` column is the consumer's historyKey, NOT the display slug. The invariant to preserve is "never write un-scrubbed text into the public_* tables." Curation of *which* projects appear publicly is the consumer's job — the `selected-projects` MDX manifest (`content/projects/*.mdx`) is the single source of truth for the public site. Unknown project → empty `200`. **Read-time counts projection (2026-07-21):** for a project with `project_metadata.public_counts=1`, the endpoint additionally overlays counts-only weekly rows projected from the private `weekly_rollups` (numeric columns only — no prose can leak) on weeks lacking a published prose row. Opt in via `scripts/seed_public_counts.py`.
- `project_aliases` table + `scripts/alias.py` CLI — project renames are non-destructive: aliases stay in the table, rows keep their original `project` value, and every read expands `WHERE project = ?` into `WHERE project IN (canonical, …aliases)` via `store.expand_project()` / `web.turso_helper.resolve_project_names()`. Run `python scripts/alias.py add <old> <new>` to alias; run `python sync_to_turso.py` to propagate to the cloud dashboard. Design rationale in `docs/alias-layer-plan.md`.

## Machine label

The SessionStart hook (`workflow/hooks/session-start.sh`) injects a `Machine:` line (`mini` / `laptop` / raw `hostname -s`) so any agent immediately knows which computer it's on. Useful because work is split across two machines and CLAUDE.md notes often distinguish them. To rename or add a host, edit the `case` in the hook.

## Cross-agent handoff

This repo coordinates with peer repos (selected-projects, prntd) via an append-only shared log living in the **standalone private git repo `nicolovejoy/handoff`**, cloned to `~/src/.handoff` (synced across mini + laptop). One file per pairing, each with a `repos: [a, b]` front-matter manifest. The SessionStart hook auto-injects the matching file's `## Active` section after a time-boxed best-effort pull, so you see pending notes without reading the file manually.

**Writing a cross-repo note** — never hand-edit + manually `git push`; use the wrapper so the pull-rebase/commit/push is atomic and conflicts surface loudly:

```
~/.claude/bin/handoff.sh append <file> "### YYYY-MM-DD <from> → <to>: <subject>

<body>"
```

It inserts the entry at the **top** of `## Active`. When an entry is acted on, move it under `## Archived` with a one-line outcome (a normal Edit), then `~/.claude/bin/handoff.sh sync`. Exit codes: 0 ok · 3 conflict (kept local, resolve in `~/src/.handoff`) · 4 offline (kept local, re-run `sync` later). Design + 26/26 pressure test: `docs/handoff-repo-plan.md`, `workflow/handoff-sim/`.

## Next Steps

Shipped work is in git and in the code. What follows is only what isn't:
open work, traps that cost real time, and decisions not worth re-litigating.
The full chronological log lives in `docs/history.md`.

### Open

**Garm consumer — MERGED + DEPLOYED 2026-08-23.** PR #54 squash-merged to
main, `GARM_URL`/`GARM_KEY`/`GARM_GATING` set in Vercel prod, deployed via
`vercel --prod`. Branch `garm-consumer` deleted. Plan: `docs/garm-consumer-plan.md`.

Still open from the plan: **Task 8 Step 4, grant seeding** — no non-admin
reader has a grant yet (e.g. Pierre → `viewer` on `prompt-lab.prntd`), so
with `GARM_GATING=on` every existing `READER_EMAILS` reader is currently cut
off until grants exist. **Task 9, the smoke test**, is unrun. Decisions, all
Nico's 2026-08-22: (1) Garm slugs NAMESPACED `prompt-lab.<canonical>` — dot,
not colon; (2) reader = anyone with ≥1 `prompt-lab.*` grant, Garm-only,
`READER_EMAILS` survives only as the `GARM_GATING=off` kill-switch allowlist;
(3) `#/health`, `#/visitors`, uptime go admin-only; (4) revocation latency 10
min. Admin-bypass rationale (a Garm outage can't lock Nico out of the tool
that diagnoses Garm) stands.

Also asked of Garm 2026-08-23 (see `~/src/.handoff/garm-prompt-lab.md`), not
yet built: a per-person access lookup dashboard panel against PR #54's own
grants-by-email client (pure UI work, nothing new needed from Garm), and a
usage/traffic-over-time panel against Garm's `GET /api/usage` (gated by
`GARM_REPORTING_KEY` — not yet minted/pulled into Vercel). The "reverse
lookup" (who has access to project X) was explicitly ruled out by Nico as
too much blast-radius.

**Not prompt-lab's bug, just diagnosed here 2026-08-23:** the `howl@` denial
digest is Garm's own email (not ours), and a burst of ~35 denials on
ibuild4you traced to ibuild4you's own liveness probe hammering
`/gnipahellir` with a synthetic `health-probe@example.com` credential. Garm
already asked ibuild4you to kill it (`~/src/.handoff/ibuild4you-prompt-lab.md`,
2026-08-23); nothing to do here unless it recurs.

**VERIFIED 2026-08-22: the first unattended laptop run of the nightly jobs
worked.** `send-review.log`: started 02:30:01, generated in 138.0s, sent,
finished 02:32:22, `LastExitStatus = 0`; `pmset -g log` shows the only sleep
that hour was 02:05–02:21, before the job. The caffeinate wrapper held through
the run. The sleep fix is no longer a claim.

**Next piece of work: `docs/nightly-pipeline-plan.md`** (written 2026-08-21,
not started). Collapses the racing nightly agents into one ordered pipeline,
because **a scheduler is not a dependency mechanism** — launchd coalesces
missed `StartCalendarInterval`s onto one wake, so two agents scheduled 45
minutes apart start simultaneously after a closed-lid night, and retiming
`api-costs` would look like a fix and not be one. Two measured defects it
addresses, neither of which alarms today: Turso's newest `review_snapshots`
row is permanently **one day behind** (inside its 2-day threshold), and
`review_snapshots` holds **10,938 rows in Turso against 69 locally**, because
`store/turso_store.py:549` is a plain `INSERT` and the sync re-pushes the
newest ~68 rows nightly. Step 1 (idempotent remote writes) is the prerequisite
and fixes the duplication on its own.

**SPAN outage 2026-08-21 — RESOLVED same day, not our fault, and the cause was
one toggle.** Cloudflare **Bot Fight Mode** was managed-challenging Vercel's
egress on `influx.pianohouseproject.org/api/v2/query`, so SPAN's health check
503'd and its monitor flapped ~25 times in a day. Nico disabled BFM; verified
green from both repos. Thread archived in `~/src/.handoff/span-prompt-lab.md`.
Two residuals, one already closed:
- ~~UptimeRobot's account display timezone was **UTC-10**, stamping every alert
  email ten hours behind Pacific~~ — **FIXED 2026-08-21 by Nico.** Kept because
  of what it cost: two rounds of cross-agent confusion over the incident time,
  with an authoritative-sounding wrong timestamp handed between repos. When two
  sources disagree about *when*, suspect a display timezone before suspecting
  either party's reading.
- **Load-shedding is not available on our side and never was.** The `deep` flag
  in `web/api/health_report.py` is *descriptive* — it mirrors `?db=1` in the URL
  — and `_check_target()` issues the request either way, so flipping it removes
  zero requests. byside and garm got their reduction by editing the **URL**. Do
  not offer "flip it to shallow" as a remedy again without checking whether the
  target's URL actually has a deep variant to drop.

**The nightly review's "3h19m API call" was never an API problem — the Mac
was asleep. SOLVED 2026-08-20; do not re-open the timeout theory.** The
earlier entry here diagnosed a read-timeout that kept resetting on trickled
data and prescribed a hard wall-clock deadline of ~10 minutes. **That fix
would have aborted a healthy run every single night.** It was never applied.
Keep the reasoning below, because the measurement trap it describes will
recur on any machine that idles.

The evidence, gathered by `pmset -g log` on the mini:
- The mini deep-sleeps every ~15 minutes with 45-second dark wakes, all
  night — **19 sleep cycles between 02:00 and 06:00**, 742 sleep/wakes since
  the Aug 13 boot, each logged `Entering Sleep state due to 'Maintenance
  Sleep':TCPKeepAlive=active`. `pmset sleep 0` is already set and does not
  prevent this on Apple silicon.
- launchd fires `StartCalendarInterval` on the next **wake**, not the
  scheduled minute. The 02:30 job actually started at **02:42:07**.
- 02:42 → the log's 06:01 mtime is **exactly the 11,942s** in the log.
  Summing the sleep intervals across that span: **~11,350s asleep, ~640s
  awake.** There was no 3h19m call. There was a normal generation (a healthy
  night is 136s) stretched across a machine powered down for 95% of the
  wall clock.
- `time.time()` counts sleep; the monotonic clock httpx uses for its read
  timeout does not. So the 300s ceiling **correctly** never fired and
  `duration_ms` **correctly** read 3h19m. Both numbers were right and they
  measure different things. `TCPKeepAlive=active` is what let the socket
  survive the sleeps, which is also the better explanation for the Night 2
  "6-hour silent hang" than a half-open socket.

Confirmed still true from the old entry: the two real bugs found 2026-08-19
(uncaught `APITimeoutError` with no retry; unbounded client timeout) did not
recur, so those fixes are genuine. And the `send-review.py` line-257
traceback **is** a fossil — it matches `86ed77d` (257 lines, Aug 14–19), not
the current 255-line file.

Fixed same day, all of it machine-agnostic and in git:
- `workflow/run-nightly.sh` — every nightly plist now runs its job through
  it. Holds `caffeinate -ims` for exactly the job's lifetime (with a utility
  argument, `-t`/`-w` are ignored and the assertion cannot orphan; no `-d`,
  so the display still sleeps), stamps start/finish times into the log, and
  rotates the log by **copy-truncate** at 256KB. Rotation must not be `mv`:
  launchd opens `StandardOutPath` before spawning, so renaming leaves the
  inherited fd on the renamed inode and the whole run lands in the archive.
- `claude_api.call_claude` logs each attempt's start timestamp and records
  both wall and monotonic elapsed; `describe_elapsed()` prints
  `"11942.4s wall / 638.0s awake — HOST SLEPT ~189min mid-call"` instead of a
  bare duration. `awake_ms` joins `duration_ms` in the returned dict. Five
  `clocks:` tests pin this, including a grep guard that both readers still
  call `describe_elapsed` — if one quietly reverts to printing bare
  `duration_ms`, the next such night is undiagnosable again.

**Do not add a wall-clock deadline.** If a deadline is ever wanted it must be
enforced on monotonic time, or it will abort healthy runs on any sleeping
host.

**Found while fixing the above: `com.promptlab.report` has been silently dead
on the mini since the 2026-08-13 rebuild.** Its plist ran
`source $REPO/.env && python generate-report.py 30`, and **the mini has no
`.env`** (only `.env.local`), so `source` failed, `&&` short-circuited, and
python never ran — no `generate-report.log` exists there at all. This is the
identical `&&` short-circuit that killed this same job for four months once
before. The `source` was always redundant: `generate-report.py:134` calls
`load_env()` itself, which loads `.env` *and* `.env.local` and tolerates
either being absent. The plist now invokes python directly through
`run-nightly.sh`. Next scheduled run is the 1st.

**Also found: the mini's raw prompt DB is frozen** — 11,240 prompts, last
`2026-08-12 00:35`, i.e. the restored pre-wipe snapshot, while the laptop
logs 46–198 prompts/day. Nothing is captured on the mini, so its synthesizer
runs nightly over a dead database and its sync re-pushes identical rows.
Harmless, but it means the mini's only real contribution was *being awake at
2:30am* — which it wasn't.

**Decided 2026-08-20 (Nico): the nightly jobs move to the laptop.** He leaves
it on and plugged in, and explicitly accepted the limitation that a closed
lid means a late or missing report. Two things make this better than it
sounds: launchd re-fires a missed `StartCalendarInterval` on wake, so a
closed-lid night gets a late email rather than none; and co-locating the
readers with the capture machine closes the old "laptop synthesizes at 2:00,
mini reads Turso at 2:30" “Today”-window gap for free. The laptop sleeps too,
so the caffeinate wrapper is what makes this viable — it is not a
mini-specific hack.

For the record, 2026-08-17 in one breath: turso-readers merged to main
(direct, per Nico); py3.9 `from __future__ import annotations` fixes in
`pull_api_costs.py` + `store/__init__.py` + 2 more (repo swept — and note
the sweep ran pre-merge and missed the file the branch was about to add;
sweep AFTER merging); mini's four jobs loaded, cost-pull kickstarted clean
end-to-end, review dry-run composed laptop work from the merged store; #50
(day-page cache/prefetch) and #52 (write-time `agent` label on
`page_views`) shipped via parallel worktree agents, deployed, eye-checked
by Nico; #51 closed (laptop's `project_workspaces` was never seeded —
seeded both machines, laptop rows UPDATEd, Turso backfilled by re-pull +
full sync); Turso `_pipeline` got a 60s timeout + one retry after a full
sync hung 1.5h on a dead connection (0.36s CPU / 89min wall — true
full-sync time is 2m35s, no perf issue); repo housekeeping: 14 archived,
`react-firebase-authentication` deleted, all 13 mini-staging repos rescued
to `~/src/mini-rescue/` with pushed `mini-rescue-20260817` branches.

Turso-readers production leftovers:
1. ~~Laptop's `.env.local` needs `GROUND_CONTROL_MACHINE=laptop`~~ — **DONE
   2026-08-20, Nico appended it.** Matters now the laptop is the only machine
   running jobs, since `daily_summaries_machine` keys on it.
2. ~~Nothing syncs laptop→Turso between the 2:00am synthesizer write and the
   mini's 2:30am review read~~ — **MOOT 2026-08-20.** Both now run on the
   laptop, in sequence, over the same local DB, so there is no cross-machine
   window to miss. This resolved by co-location rather than by the
   sync-before-review-vs-retiming decision it was waiting on.

**mini-rescue curation — open, unhurried.** `~/src/mini-rescue/` holds 13
rescued repos; walk them at leisure, merge-or-discard, delete each folder as
judged (the dir emptying is the progress meter). Settled 2026-08-17, don't
revisit: freevite IS invitekit under its old name, left to rest (its last
commit lives only in that local copy — remote is archived, deliberately not
pushed); roll-your-own (GitLab, no auth) and skitrack-ntzb-poc (third-party
remote) also deliberately unpushed. Two loose ends from the rescue: the
agent installed git-lfs globally (Homebrew) to get rock-art-fab pushed, and
musicforge's lilypond submodule edits went to the shared
`neonscribe/lilypond-lead-sheets` repo on a rescue branch. Also still to
delete: the dead-token copy in `~/mini-staging/home/zshrc.mini`.

**garm hit the same Neon-CU bug as byside — found 2026-08-18, fixed same day
by the garm side.** Neon alerted that `neon-bole-tree` (garm's DB, project
`steep-glitter-55844373`) used 100% of its 100 CU-hour monthly quota with
12+ days left before reset — confirmed by the math (0.25 CU × 1,453,008
active-seconds ÷ 3600 = 100.9 CU-hours, exact match). Same root cause as
byside below: `scripts/uptimerobot.py` deep-polled
`garm.prompt-labs.org/api/health?db=1` every 5 minutes, never letting Neon's
free-tier autosuspend kick in. Filed to `~/src/.handoff/garm-prompt-lab.md`;
commit `59ea622` ("garm's health check stops paying to keep Neon awake")
landed same day. Since consumers fail closed on a garm outage, this wasn't
just a cost problem — worth confirming next month's CU number actually drops
like byside's did, same as the open byside check below.

**Two small follow-ups from 2026-08-14, neither urgent.**

*byside's Neon bill.* The deep health poll was consuming 80 of byside's 100
monthly CU-hours (Neon free tier autosuspends after 5 min idle; we polled at
5 min, so it never slept). Monitor is shallow now and applied live — **check
the September CU number to confirm the drop**, since nothing alarms on it. The
transferable rule, filed in `scripts/uptimerobot.py`: deep coverage over an
autosuspending DB needs an interval **longer than the suspend window**, not a
deeper URL, because polling at the suspend interval makes the check circular —
it keeps the database warm and then reports that the warm database answers.
Notified byside; their route comment still calls the deep check "cheap enough
to poll every 5 minutes", which is true of the function and false of the
compute.

*Public data is stale again* — 9 unpublished weeks for prompt-lab, 4 prntd,
3 musicforge, 2 ibuild4you (`scripts/draft_public_refresh.py --list`). It goes
stale silently by design, and sat six weeks before a consumer noticed last
time. Drafting is cheap; the human review is the expensive part and the actual
privacy gate, so this waits for Nico to want it.

**Per-Pi service inventory — NEW 2026-08-13, prompt-lab owns it** (Nico's
request, relayed by the mini-decommission agent mid-wipe). No document
anywhere lists what runs on each Pi; the decommission cross-checks had to
reconstruct it piecemeal. Both boxes answered same-day (home-assistant
session's contribution). **phrpi VERIFIED BY SSH 2026-08-13** — the
second-hand list was incomplete and wrong in one attribution; corrected
below. homeassistant.local is still second-hand (the laptop's key isn't in
its SSH add-on). Then consider promoting this to a `docs/` file:
- *phrpi* — Raspberry Pi 5 Model B Rev 1.1, Debian 13 (trixie), kernel
  6.12.47, user `nico`, laptop has direct key auth. **Dual-homed on one flat
  /22, deliberately** (2026-08-13, after the closet move): eth0
  `192.168.4.53` (MAC `88:a2:9e:08:4a:d9`) carries the default route and is
  what `phrpi.local` resolves to; wlan0 `192.168.5.50` (MAC
  `88:a2:9e:08:4a:da`, SSID "Piano House", netplan-managed) is kept **on
  purpose as the out-of-band path** into a headless closet box — tested
  working by SSH the day it was set up, because an untested fallback is this
  repo's signature failure. Nothing binds the wlan0 address (every service
  listens on `0.0.0.0`/`[::]`), so the second interface costs nothing today.
  **mDNS points at eth0 only, so the Wi-Fi IP is the thing to write down** —
  `phrpi.local` won't save you when ethernet is what died.
  Everything runs in Docker (10 containers): `timescaledb` :5432,
  `grafana` :3000, `influxdb` :8086, `lights` :5002 (phrpi-lights, pushes
  learned prefs into HA `input_text`s), `nudge-board` (:80 internal),
  `span-collector`, `charge-detector`, `bath-detector`, `daily-report`,
  `cloudflared`. Plus `span-backup.timer` (systemd). Note :3000 is
  **grafana**, not the nudge board — an earlier pass guessed that from the
  port alone.
  **`nudge.timer` and `nudge-michael.timer` are `disabled`** (vendor preset
  is `enabled`, units present and static) — this is DELIBERATE: Nico turned
  nudge off just before the 2026-08-13 wipe. Not a silent failure, don't
  "fix" it; re-enabling is a nudge-repo decision.
  One finding that is worth acting on, though not prompt-lab's to fix: the
  **`cloudflared` tunnel token is passed as a plaintext CLI arg**,
  visible to anything that can run `docker inspect` — worth moving to a file
  or env, and it means phrpi has an inbound tunnel from the public internet,
  which is not mentioned anywhere else in these notes.
  The mini's old `com.span.bath-detector` LaunchAgent was ruled LEGACY
  2026-08-13 (detection moved to the Docker service; the plist was a
  potential double-writer and is excluded from the mini rebuild).
- *homeassistant.local* (the "homeaspi" name in old notes is STALE — the box
  is alive and independent of the mini): Home Assistant OS, HA Core 2026.7.2;
  Matter server driving 22 Leviton dimmers + WiZ bulbs; Advanced SSH & Web
  Terminal add-on; recorder at 10-day retention; all lighting automations.
  **Also dual-homed, confirmed 2026-08-13** — and the single address in the
  old notes was the *wrong one*: end0 `192.168.5.14` (ethernet) and wlan0
  `192.168.5.34` (Wi-Fi) both serve :8123 (verified 200 from the laptop,
  12ms vs 20ms), both DHCP-reserved in eero, and **`homeassistant.local`
  resolves to `.5.14`** — so the hostname is already the wired path. Wi-Fi
  stays up deliberately and matters more here than on phrpi: **the laptop
  has no shell into this box at all** (its key isn't in the SSH add-on;
  re-provisioning is queued in the home-assistant repo), so the radio is the
  only out-of-band route to the machine running the house's lighting.
  Consequence to fix, not to admire: **`.5.34` — the Wi-Fi address — is what
  hardcoded consumers point at**, confirmed live for phrpi-lights
  (`HA_URL=http://192.168.5.34:8123` in the `lights` container env, repo
  `/home/nico/phrpi-lights`, **no laptop clone**). Also the home-assistant
  repo's `deploy.py`, `tools/matter_diag.py`, `dashboard/ha_client.py` and
  tests. Both notified via handoff 2026-08-13; the target is
  `homeassistant.local`, not another literal.
  RESOLVED same day, and the fix was a restart rather than a setting: HA's
  Settings → System → Network → **Network adapter** panel — which is what
  integrations bind for zeroconf/SSDP/Matter discovery — read `wlan0` only.
  That was **stale, not wrong**. HA builds the adapter list at startup and
  had not restarted since the cable went in. After a restart it reads
  `end0 (192.168.5.14/22)` and nothing else, so Matter discovery for the 22
  dimmers is on the wire; Autoconfigure stays checked and nothing was
  hand-pinned. The habit worth keeping: **restart before believing that
  panel.** Pinning end0 by hand was considered and rejected — it would trade
  a visible outage for a silent discovery failure if the wire ever dropped,
  since HA would stay reachable over Wi-Fi and look healthy.
  One thing still unproven, cheap to note: a Core restart does not re-acquire
  DHCP leases, so whether ethernet comes back after a real power cycle is
  untested. The closet's next outage tests it.
**`automation-dev` is DELETED — Nico did it 2026-08-14, and nothing broke.**
This closes the only item that carried a live security edge. Verified by SSH
the same day, and the verification is worth reading because it overturns the
note it replaces:

- The `lights` container on phrpi still authenticates to HA — **200 from
  `GET /api/`** with its own credential, tested from inside the container so
  the value never entered a session.
- The container has been **up 28 hours without a restart**, so its environment
  cannot have changed. A still-valid token in an unrestarted container is proof
  the credential it holds was *never* `automation-dev`.
- Therefore the **2026-08-13 "correction" was itself wrong**, and the note it
  overturned was right the first time: **phrpi-lights holds its own separate
  token.** The HA UI listing one long-lived token was read as "there is only
  one"; what it actually showed is one token *of the ones created that way*.
  The lesson to keep: a UI list is evidence about the UI, not about every
  credential in the system — the authoritative test is whether the consumer
  still authenticates.
- Also corrected: the variable is **`HA_TOKEN`**, not `HASS_TOKEN` as this file
  said for two days. `HASS_TOKEN` is unset in the container. A rotation
  following the old instructions would have edited a variable nothing reads and
  "succeeded" while changing nothing.

Residual, both minor now: the plaintext copy in
`~/mini-staging/home/zshrc.mini` is a **dead** credential rather than a live
one, so it's cleanup rather than exposure — still delete it. And the mini's old
consumers (`deploy.py`, `tools/matter_diag.py`, `dashboard/ha_client.py`,
tests, `phrpi-lights/.env.tpl`) now reference a revoked token; they'll need the
new one whenever the HA deploy path is re-provisioned.

Separately, the token card was nearly mistaken for the **Refresh tokens**
card above it — those are login sessions (browser, iOS app), and deleting
one revokes a session, not an API token. Known consumers of the dead token (mini pre-erase grep): the
home-assistant repo (`deploy.py`, `tools/matter_diag.py`,
`dashboard/ha_client.py`, tests), `phrpi-lights/.env.tpl`, and the mini's
`.zshrc`. Separately, the mini was the HA *deploy machine* — the laptop
clone lacks `.secrets` and its ssh key isn't in the HA SSH add-on;
re-provisioning is queued in the home-assistant repo (coordinate there,
not with the decommission notes).

Closet move DONE 2026-08-13 — both Pis wired, both deliberately dual-homed,
all four interfaces DHCP-reserved. What's left, none of it prompt-lab's code
and all of it filed in `~/src/.handoff` (new channels
`home-assistant-prompt-lab.md` + `phrpi-lights-prompt-lab.md`):
- ~~Rotate `automation-dev`~~ — **DONE 2026-08-14, deleted by Nico.** lights
  verified still authenticating (200) afterwards; it holds its own token.
  Only cleanup left: delete the now-dead plaintext copy in
  `~/mini-staging/home/zshrc.mini`.
- **Laptop SSH key into HA's add-on.** The highest-leverage one: today's HA
  work ran on screenshots and inference while phrpi got measured in seconds.
  Everything else about that box stays guesswork until this lands.
- **Repoint hardcoded `192.168.5.34`** → `homeassistant.local` in
  phrpi-lights and the home-assistant repo.
- **`cloudflared`'s token out of argv** on phrpi (owner unclear — the
  container's compose dir wasn't traced; not filed anywhere yet).

**The nightly review email says "no new work" on days full of work — BOTH BUGS
FIXED 2026-08-12.** Full diagnosis in `docs/history.md` / git history
(`877ea15`, `c332ac9`); what happened and what remains:

*Bug A, the window — FIXED in code, 2026-08-12; window logic survived the
2026-08-14 Turso refactor below, raw-session selection did not.* The job
fires at 2:30am and asked for **today**, structurally empty at that hour, so
`review_windows()` in `send-review.py` makes "Today" mean **yesterday's
completed lab-day** (Pacific) — that part is unchanged today. What's gone:
`send-review.py` no longer selects raw sessions at all (Task 2 of the Turso
refactor removed the read entirely; it composes from `daily_summaries`/
`weekly_rollups` instead — see the "Turso refactor DONE" line below). The
overlap-by-time-range logic that originally fixed raconte's 31-hour session
(`get_raw_sessions(overlap_utc=…)` + `day_helper.lab_day_bounds_utc`,
DST-correct) still exists and is still tested, but only at the store layer
(`scripts/test_send_review.py`, 7 tests) — nothing above it calls it anymore.

*Bug B, delivery — RESOLVED by unloading, not by repairing the sender.* The
laptop's 33 Resend 403s came from its stale Jun 6 `.env.local` using the
unverified `send.` subdomain. Per Nico's call 2026-08-12: the laptop's three
reader plists (`review`, `report`, `api-costs`) are **unloaded and parked in
`~/Library/LaunchAgents/disabled-readers-20260812/`** (reverse: move back +
`launchctl bootstrap gui/$UID/<plist>`), and the mini's current `.env.local`
was scp'd over (laptop's old copy at `.env.local.bak-20260812`). The mini is
now the only sender, which was the proposed split — accepted cost: nights the
mini is down (e.g. wipe day) get no review email. Still open, low priority:
a failed send still writes `review_snapshots` (the row records *composition*,
not *delivery* — nothing distinguishes them), and the #45 heartbeat
structurally can't see a last-step delivery failure because the artifact is
upstream of it. Also never explained: the laptop wrote no `review_snapshots`
rows for Aug 10-11 despite its job running — academic now the readers are
unloaded, but if it recurs on the mini, dig.

**Turso refactor DONE 2026-08-14** (tracked in the DB-ownership bullet below):
`send-review.py` no longer reads its **local** `sessions` table, so laptop
session detail reaches the Today section. `generate-report.py` was covered by
the same change.

**The trajectory heatmap's month labels were on a different scale than the grid
— FIXED 2026-08-14** (diagnosed 2026-08-12; Nico re-reported it from a
musicforge screenshot, which is what got it built). The data was always fine;
only the axis lied. `.heatmap-labels` was `justify-content: space-between`,
spreading 13 month labels across the **container's full width** (~1050px),
while `.heatmap` was 53 fixed columns of 8px + 2px gap = **530px**, left-aligned
and never stretched. The grid's right edge (today) therefore landed at ~50% of
the label row — the 7th of 13 labels, **Feb**. Six months of continuous work
read as "dead since March." The smoking gun: the renderer computed
`monthLabels.push({ idx: weeks.length, … })` and then rendered
`<span>${m.label}</span>`, throwing `idx` away — alignment was never
implemented. Second defect, same cause: the label row sat *outside* the
`overflow-x:auto` container, so on a phone it didn't scroll with the grid.

Fixed as agreed, and **the coloring stays on prompt count**: both rows now live
inside one `.heatmap-scroll` container wrapping a `.heatmap-track`
(`width:max-content`), and the label row carries the **same flex geometry as
the grid** — one 8px `.heatmap-labelslot` per week column, `gap:2px`, labelled
slots holding absolutely-positioned text plus a dot at the true column centre,
the convention `DateAxis` already established for the other six charts. `idx`
is finally read (`labelAt[i]`). Alignment is now **structural**: a label is
positioned by occupying its own week's slot, so there is no pitch constant to
keep in sync. `.heatmap-track` carries 16px of horizontal padding so the first
and last labels, which overhang their 8px slots, aren't clipped — applied to
both rows at once, so it can't pull them out of register.

`ActivityHeatmap` has exactly one call site (the project page), so this covers
every project at once. Verified by `node --check` over the extracted module
plus a class-defined/class-used sweep, then **confirmed by eye on prod
2026-08-14** (musicforge): month labels sit over their own columns in both
directions, dots line up, and the six months that read as "dead since March"
now read as the continuous work they were. Note that the sandbox cannot render
the app, so the eye check is not optional here.

**Prompt ratings: ABANDONED 2026-08-14, don't revive it without a new idea.**
The live `prompts` table carries `utility`, `tags`, `notes`, `outcome` and an
`idx_prompts_utility` index; **0 of 1318 rows have ever been rated**, and the
columns are not even declared in `store/` (they exist only in the live DB and
in two test fixtures). Correcting the record: earlier notes claimed `/handoff`
offers rating and `/readup` surfaces utility-4+ prompts — **neither has ever
existed**. `grep -rn "utility" workflow/` returns exactly one hit, a comment in
`log-prompt.sh`. So this was never dead code over an empty column; it was an
empty column with no code at all, and the same claim is in the *global*
`~/.claude/CLAUDE.md` (lines 22, 27-29) describing `/prompts` and rating flows
that don't exist. The columns stay (harmless, indexed); the aspiration is
dropped. If it ever returns, the two ideas worth starting from are a one-word
in-the-moment marker (a `/good` command stamping the previous prompt — slash
commands are already filtered out of the table, so it can't pollute its own
data) or deriving utility from outcome rather than asking a human at all.

**The raw tier undercounted prompts by design — FIXED 2026-08-14.** The old
guess (that `log-prompt.sh` only sees turn-initial prompts) was **wrong**: it
runs on `UserPromptSubmit`, which fires per submitted message, mid-turn
interjections included. The real cause was a write-time filter,
`[ ${#PROMPT} -lt 20 ] && exit 0`. Every prompt under 20 characters was
silently dropped — "yes", "go ahead", "ship it". The fingerprint was exact:
`min(length(prompt))` over the whole table was **20**, with **zero** rows
below. That is a filter, not a distribution.

The damage was never the missing rows, it was the **shape** of the loss: a day
spent steering is mostly short prompts and rendered as a quiet day, while a day
spent writing specs rendered as busy. `daily_summaries.prompt_count` feeds the
trajectory heatmap and the KPI tiles, so the charts presented a filtered signal
as an activity record — the repo's signature failure again. It is also what
made "1 prompt for prompt-lab" on a six-turn day look like a lag.

Now: **store everything, label it, select at read time.** `prompts.kind` is
written by the hook from `scripts/prompt_kind.py` — the single implementation,
shared with `scripts/backfill_prompt_kind.py` so live rules and backfill rules
can't drift. Five kinds: `approval`, `correction`, `question`, `command` (a
bare `/slash` invocation), `spec` (everything else). **No rule consults
length**, pinned by a test that pads a prompt and asserts the label doesn't
move. A label is recomputable; a discarded row is not — that asymmetry is the
whole design, so misclassification is cheap and `--all --apply` relabels
everything.

Backfill applied to all 1353 existing rows: 81% spec, 17% question, 2%
correction, and — the diagnosis confirming itself — **0 approvals**, because
approvals were exactly what the filter had been deleting.

Three things fell out of the same change:
- **`prompts.context` now holds the whole last assistant message, trailing 2000
  chars** (was `head -1 | head -c 500` — the first *line*, averaging 124 chars,
  usually a lead-in rather than the proposal). Paired with `kind='approval'`
  this is what answers "what did I actually say yes to?". `base64` in the jq
  pipeline is load-bearing: `tail -r` makes the first *record* the most recent,
  but a message spans lines, so encoding each to one line makes "first record"
  and "first line" agree again.
- **A failed insert is no longer silent.** It used to go to `/dev/null`; it now
  appends to `~/.claude/hooks/log-prompt-errors.log`. The hook also ALTERs
  `prompts` defensively, because the table predates `store/`'s migrate path
  (the retired Flask dashboard created it) and bash never calls `migrate()` —
  without that, a DB lacking `kind` would fail *every* insert silently.
- `printf` replaced `echo` when escaping, since a prompt can now legitimately
  be exactly `-n` or `-e`.

**The discontinuity is annotated, not smoothed.** Counts before 2026-08-14 are
filtered and counts after are not, so every prompt-count series steps up once
on that date. `CAPTURE_FIX_DAY` + a `.heatmap-note` caption say so on the
chart. Backfill is impossible — the dropped prompts were never stored.
Deployed and confirmed on prod 2026-08-14.

The step won't actually be visible until enough post-cutover days accumulate,
so if a future session finds prompt counts jumping around mid-August and starts
hunting a bug, this is the answer. That is what the caption is for.

**UptimeRobot alerted nobody for six weeks — FOUND AND FIXED 2026-08-09.**
`scripts/uptimerobot.py` declared *what* to watch and never *who to tell*, so
every monitor it created carried an empty `assignedAlertContacts`. **7 of 8
notified nobody**; only garm had one, because garm's monitor was made by hand
in the UI before the script existed. Caught because musicforge asked whether
anything fired during their 2026-08-09 Fly outage: the monitor detected it
exactly as designed (DOWN 17:35:14 PDT → UP 17:45:51, 637s, cause 333333) and
sent no mail. The repo's recurring shape in a new place — the sensor worked,
the output went nowhere, and eight green monitors read as health.

Fixed: contacts declared by **email, not id** (the id is account state, the
address is the intent; resolved against `/alert-contacts` at run time, a
missing address is fatal), reconciled as a **union** so a hand-added contact
survives, all 7 backfilled live, and `list` now prints
`alerts=** NOBODY **` — the state was invisible because nothing rendered it.
Two bugs fell out: the documented **10 req/min free-tier limit was never
respected**, so the first `--apply` patched 2 of 7 and 429'd on the rest,
reporting five real changes as failures (now 6.5s pacing + one 429 backoff).

Still open from that thread: **musicforge asked for the Fly backend as its own
uptime line, and it cannot be done with the current monitor** — the deep check
reaches Fly *through* the Vercel rewrite, so a Vercel outage and a Fly outage
render identically. Needs the direct Fly hostname and a decision on whether the
frontend line stays deep; both asked in the handoff channel, nothing built.
**Delivery verified end-to-end 2026-08-09**, not merely sent: a throwaway
monitor pointed at a real 404 went DOWN (incident `cause 404` at 02:00:09Z)
and the mail landed in Nico's inbox. Two deliberate choices worth keeping if
this is ever repeated — **test on a disposable monitor, never by flipping a
real one to a failing URL**, because that writes a fake outage into that
service's true uptime ratio and the archive is never backfilled; and pick the
404 target carefully, since `https://prompt-labs.org/api/<anything>` returns
**200** from the SPA catch-all (bug #40, re-confirmed live) and would have
produced a false UP. `garm.prompt-labs.org` returns a real 404. And the 4
HEARTBEAT creates still fail on every `--apply` (3× 403 paid-plan, 1× 400
`gracePeriod must not be greater than 86400` — a real declaration bug in the
bi-monthly report's 5-day grace, harmless only because the plan blocks it
first), so `--apply` always exits 1. Cosmetic, but it trains you to ignore the
exit code.

**Mini → headless (closet) migration — switch (TP-Link TL-SG116, unmanaged)
arrives Mon 2026-08-11.** **Settled 2026-08-09: the current laptop IS the new
MacBook Pro and the new primary — no third machine is coming**, so this is one
migration to absorb, not two. Design was started as a brainstorm and **parked
mid-questioning**; nothing is decided beyond that. Full audit 2026-08-08 lives
in memory `project_mini_headless.md` — **on the mini, and memory does not sync
between machines**, so it is unreadable from the laptop; re-read it there or
redo the audit. **Both boot blockers cleared 2026-08-10 on the mini:**
Remote Login is ON (port 22 verified listening) and FileVault is OFF.
Still pending: enable auto-login (System Settings → Users & Groups, greyed out
until FileVault reported Off) and the proof — one reboot with the display
attached that lands on the desktop with no password and answers
`ssh nico@<mini>` from the laptop. Before the move: DHCP-reserve en0 MAC
`d0:11:e5:b5:74:41`. All six custom LaunchAgents (4× promptlab nightly,
rockart backup, SPAN bath detector) stay on the mini — note they're **user**
agents, so they need a logged-in session. mDNS must survive the move (bath
detector → `phrpi.local`, Time Machine → Time Capsule); the unmanaged switch
keeps one subnet, so it does.

Added to the list 2026-08-10, deliberately scoped small: **disconnect Dropbox
from the mini and delete local files it doesn't need** — but only after
confirming each has a copy in iCloud/Dropbox (Nico believes everything
important is in one of those, possibly a third place; verifying that fully is
its own project, not this one). The mini also ends up wired to both Raspberry
Pis (one runs Home Assistant) — parked thought: that adjacency may help
developing the Pi tools later.

**The wipe HAPPENED 2026-08-13 — the mini is being re-purposed, and
RECONSTITUTING prompt-lab's services on the new mini is part of the plan**
(Nico's direction, same day: the wipe plan isn't done until the services are
back). The **mini-decommission agent/repo owns the checklist**; prompt-lab
owns its reconstitution spec, sent to them 2026-08-13: clone repo + venv →
copy staged `.env.local` → **MOVE** (not copy, then delete staging) the
frozen `prompt-history.db` back → restore the 39 memory dirs (478 files;
"44" in earlier notes counted project dirs without memory) → install
`workflow/` from the **fresh clone, never from pre-wipe backups** (repo
copies carry fixes the mini never had) → restore + bootstrap the 4 plists
(check hardcoded paths first) → verify **by artifact** after first overnight
(email arrives + `review_snapshots` row + heartbeats green). Sequencing
deliberately requested: land the `send-review.py` → Turso refactor *before*
the review plist is bootstrapped, so the reconstituted mini's first email
already sees both machines' work. **The full implementation plan is
`docs/turso-readers-plan.md`** — 5 TDD tasks for an Opus session: explicit
store backend, both readers onto processed tables, gate release, plus the
same-day clobber fix via a per-machine parts table (Nico's "simple is
better" call 2026-08-13 after weighing and rejecting mini-as-central-DB;
capture stays local-first, Turso stays the merge point). Execute AFTER the
mini reset, per Nico. **Until reconstitution, prompt-lab is
laptop-only** and the readers run nowhere (see the what-runs-where entry
below). Everything the mini held is staged on the laptop under
`~/mini-staging/`: the final `prompt-history.db` (frozen 2026-08-13 07:20,
11,240 prompts, taken after the LaunchAgents were unloaded and drift-checked),
all 39 claude-memory dirs (478 files), plists, job logs, zshrc/ssh config, SPAN env
files, and a 13-repo sweep of dirty/unpushed working trees (`repo-sweep/` —
sorting those is open curation work, worst case notemaxxing with 24 unpushed
commits). The relocate-don't-wipe debate is preserved in git
(`77dd316`/`d50c14b`/`55488f0`). Worth keeping from it: any future account split must *move* `~/.claude/prompt-history.db`,
never copy it — a second copy of every raw prompt is a privacy regression.
And the process lesson stands: *agreeing with an idea is not the same as the
idea being chosen* — this entry records a decision only because Nico stated
one.

**What runs where — SETTLED 2026-08-20: all four jobs run on the LAPTOP, and
nowhere else.** Nico's call, on the reasoning that he leaves the laptop on and
plugged in and accepts that a closed lid means a late or missing report. Applied
the same day: the mini's four agents are booted out and parked in
`~/Library/LaunchAgents/disabled-promptlab-20260820/` (reverse: move back +
`launchctl bootstrap gui/$UID/<plist>`), and all four are rendered and loaded on
the laptop. **There is exactly one sender — never load the readers on two
machines at once or Nico gets two emails a night.**

Why this beats the mini-only split it replaces: the mini's raw DB is frozen
(nothing is captured there), it deep-sleeps through the night so its jobs
started late and ran for hours of wall clock, and co-locating the readers with
the capture machine removes the cross-machine "Today"-window gap entirely. The
laptop sleeps too — `workflow/run-nightly.sh` is what makes this work, and
launchd re-fires a missed `StartCalendarInterval` on wake, so a closed-lid
night degrades to a late email rather than none.

The laptop's older `~/Library/LaunchAgents/disabled-readers-20260812/` is now a
stale backup of the 2026-08-12 parking; the live copies are the rendered ones in
`~/Library/LaunchAgents/`. The original split, for the record:
- *Local-data jobs* run on **every** machine, over its own DB, because raw
  prompts are machine-local by invariant and never leave. That is
  `com.promptlab.synthesizer`, plus the turso-sync leg. The laptop keeps its
  copy; this is not duplication, it's the federation working.
- *Reader/output jobs* run on the **mini only**, because the laptop being closed
  must mean off. That is `com.promptlab.review`, `com.promptlab.report`,
  `com.promptlab.api-costs`. **Done 2026-08-12 (Nico triggered it):** all three
  unloaded on the laptop and parked in
  `~/Library/LaunchAgents/disabled-readers-20260812/`; only the synthesizer
  remains loaded there. **Reversed 2026-08-20 — see above; the availability
  argument lost to the fact that the mini slept through every night anyway.**
- Vercel crons (the 8am health email) are cloud-side and location-independent —
  out of scope for any of this, don't move them.

**DB ownership: DECIDED 2026-08-10 — Option B, federated.** Raw stays
machine-local per the invariant; each machine synthesizes its own prompts and
pushes processed rows to Turso; the merge happens there; the always-on mini
keeps the reader jobs (review email, report, cost pull) because the laptop
being off must mean off. Nico ruled out running nightly work on the laptop
explicitly. The build-out this implies:
- Laptop gets its own `com.promptlab.synthesizer` + turso-sync LaunchAgents
  (its `/handoff` already covers most days inline).
- **FIXED 2026-08-14**: `send-review.py` and `generate-report.py` both used to
  read `get_raw_sessions()` — raw-tier, local-only, so the mini's review email
  missed laptop session detail and read "no new work" on busy days. Both now
  call `get_store("turso")` directly and read only
  `daily_summaries`/`weekly_rollups`, so the env-var-ordering trap
  (`store/turso_store.py:736` raises `NotImplementedError` on every raw
  method, e.g. `get_raw_sessions`) no longer applies. Residual risk, not a
  current state (see the what-runs-where entry above — only the synthesizer
  is loaded on the laptop today): if the laptop's readers are ever
  re-enabled without the mini also carrying this refactor, two machines
  would again compose nightly reviews from two different DBs.
- `daily_summaries` clobber — **FIXED 2026-08-14**: per-machine parts table
  (`daily_summaries_machine`) + deterministic merge at sync time
  (`merge_summary_parts`/`sync_daily_summaries` in `sync_to_turso.py`);
  `weekly_rollups` still has the same clobber shape, deferred until it bites;
  machine labels come from `GROUND_CONTROL_MACHINE` in each `.env.local` (not
  yet set on any real machine — that's a follow-up, not done by this commit).

**The week-grouping SQL filed every Monday under the previous week —
EXPRESSION FIXED 2026-08-08; DATA REPAIR APPLIED 2026-08-10.** The 207
audited-bad rollups (23 folded Mondays + 184 frozen partial rows) were deleted
(backup: `~/.claude/prompt-history.db.bak-20260809`) and regenerated from the
intact daily summaries by the fixed synthesizer, then full-synced to Turso —
regenerated rows overwrite stale cloud copies via same-key upserts. Verify
anytime with `scripts/regroup_weekly_rollups.py` (dry-run). The trap,
keep it: SQLite's `weekday N` means next-or-**SAME** day, so
`date(<d>,'weekday 1','-7 days')` returned the *previous* Monday when `<d>`
was already a Monday. The correct bucket is `date(<d>,'weekday 0','-6 days')`
— next-or-same **Sunday**, minus 6 — verified for all seven weekdays. Fixed at
all four homes (`store/sqlite_store.py`, `store/turso_store.py`,
`web/api/private_history.py` `WEEK_EXPR`, `workflow/bin/gc-read.sh`); a
`clocks:` test now runs the expression for a full Mon–Sun week and greps
`'weekday 1'` out of all four files.

The second bug was broader than gc-read.sh: its completed-weeks filter
`date < date('now','weekday 1')` resolved to NEXT Monday on Tue–Sun (fixed to
`'weekday 0','-6 days'`), but the stores' `get_weeks_without_rollups` had **no
completed-week guard at all** (`date < today`), so the synthesizer wrote
mid-week rollups constantly and the never-revisit join froze them. Both stores
now cut at the current week's Monday.

Stored damage — audited read-only by `scripts/regroup_weekly_rollups.py`
(dry-run by default, `--apply` fixes only unambiguous non-Monday week keys;
Turso via `GROUND_CONTROL_STORE=turso`, and it mirrors local anyway):
**0 mis-keyed rows** (the buggy expression still emitted Mondays), so nothing
mechanical to apply. What it found instead, all needing human judgment because
rollup prose can't be regenerated mechanically: 23 rollups with the next
Monday folded into their prose/counts (14 of those Mondays also counted in
their own week = double-counted); 21 Monday-only weeks with summaries but no
rollup (the fixed pipeline will now generate these on its own); and 182
project-weeks whose frozen rollup is missing later-in-week summaries — the
in-progress-week admission was systemic, not an edge case. The script prints
the exact DELETE for the frozen set if regenerate-over-existing-prose is ever
wanted.

**Copy review (#49) is IN PROGRESS — batch 1 of ~4 DONE 2026-08-05.**
The review runs page by page at a computer, 3-5 items at a time. Nico answers by
number and often stops mid-batch, so **track which items were actually answered,
not which batch was sent** — the first pass through this lost two items by
recording the batch as finished.

Answered and settled: the primary nav labels passed. The More panel failed
("a bit incoherent") and was rebuilt in `5b53f01` — labeled `BUILT` stamp
leading instead of a bare timestamp trailing, theme promoted to the primary row
as an icon, Log out last, close-on-outside-click. All five smoke-test items on
the rework then passed live on prod in both themes.

The two items the first pass dropped — the KPI tile labels (do they state what
is counted and over what window, consistently?) and the "Today, so far" banner
— were reviewed 2026-08-05 and **both passed**, so batch 1 is closed.

**Ask is mothballed, not deleted** — it was the only *action* in a panel of
destinations and settings and went unused; `web/api/ask.py` and the modal are
untouched, reachable from `#/about` and the `/` shortcut. Deleting it would not
even drop the `ANTHROPIC_API_KEY` dependency, which the Todos classifier holds.

One open question the rework raised, still unsettled: with Ask gone, `More`
guards a single destination plus your identity, so a plain `About` button in the
primary row may be simpler than the panel. Then batch 2 (Activity + the day
page), batch 3 (Costs, Visitors, Todos), batch 4 (Health, About, project pages).

*Note: no usage data exists for Ask and none can be recovered — its history is
`localStorage`-only and its spend is indistinguishable from the Todos
classifier's, since both draw on the same key.*

**The 80-name project list — CLEANED UP 2026-08-05.** Most names weren't
projects. **Root cause, now fixed:** `log-prompt.sh` derived the project from
the cwd *basename*, so every directory ever worked in minted one — `web`, `src`,
`public`, `utils`, `mockups` are subdirectories of real repos. It now resolves
the cwd to its **repo** via `git rev-parse --git-common-dir` (not
`--show-toplevel`: a linked worktree's toplevel is the worktree, which is how
two `agent-<hash>` projects appeared; the common dir is always the main repo).

Three deliberate properties of that hook change:
- **Only exit code 128 ("not a git repository") buckets to `scratch`.** Any
  other git failure falls back to the old basename behavior. This is not
  paranoia — the Xcode license prompt broke every git call on the laptop earlier
  that same day, and a broken git must never silently relabel real project work.
- `scratch` is pre-hidden, so the one bucket never surfaces in the picker.
- Three cases are pinned in `test_session_identity.py` (#10): subdirectory →
  repo, non-repo → `scratch`, worktree → main repo. The fixture had to become a
  real `git init` repo, since a bare directory now takes the scratch path.

Cleanup applied: **8 aliases** folded duplicates into their canonical project
(`recountly`→`raconte` — one project, the web app became a native iOS app,
`docs/history.md:39`; `skitrack` + `skitrack-ntzb-poc`→`person-tracking`;
`bakerylouise_v1` + `bakerylouise-v1`→`bakerylouise`; `audio_journal`→
`audio-journal`; `invitekit-prep`→`invitekit`; `byside-research`→`byside`).
**23 artifacts hidden** via `scripts/hide_scratch_projects.py` — sets
`private=1`, does not delete, and `--unhide <name> --apply` reverses it. Real
but dormant projects (`mars-rover-example`, `roll-your-own`, `djembe`, …) were
left alone; that's what the Dormant section is for.

**Follow-ups the cleanup surfaced, all unconfirmed and needing Nico's memory of
which directory he was actually in** — the names alone aren't evidence:
`koma_art`/`koma-launch` look like the same underscore/dash pair fixed
elsewhere; `freevite` (167 prompts, dormant) may be `invitekit` under an older
directory name, since invitekit deploys to `freevite.vercel.app`; and `spike`
(4 prompts) has the same shape as the hidden artifacts.

**`ACTIVE · N` counts hidden projects.** `activeCount` is `activeList.length`
with no `private` filter (`web/index.html:1165-1167`), and it also feeds the
`active projects` KPI tile (`:1191`), so the home screen read `37` when 16 were
shown and 21 were hidden junk. Chips honor the toggle; the counts don't. The fix
is one filter, but the semantics are a real choice: excluding private is
obviously right while `private` holds only artifacts, and wrong the day a
genuine project is marked private. Alternative is `37 · 16 shown`. Undecided.

**Don't reach for a read-time exclusion list** — read-time allowlists were tried
twice in this repo and deleted both times for drifting; `private` on the row is
the equivalent that can't drift. Two gotchas hit while doing this: `alias.py`
takes two arguments and **zsh does not word-split unquoted variables**, so a
`for pair in "a b"` loop silently wrote the whole pair into the alias column;
and a full `sync_to_turso.py` runs past 120s, so the alias rows were written
straight to Turso (safe — `project_aliases` is upsert-only, unlike
`project_metadata`, which is cloud-direct and must never gain a sync leg).

**The uptime archive wrote on 2026-08-01 and not on 2026-08-02 — DIAGNOSED
2026-08-02.** `uptime_daily` held 9 rows for Aug 1 and none for Aug 2. **The Aug 2
health email arrived**, which settles it: the cron fired, and the pull failed
silently in production. Not cron-dead.

The mechanism, and it is the interesting part: `_archive_uptime`
(`web/api/health_report.py:322`) returns `0` on every failure path — unset key, pull
exception, per-row write failure — logs to stdout and lets the email send. The row
count goes into `uptime_rows` in the **JSON response**, which only the cron's HTTP
caller ever sees, and **Vercel log retention is ~1 hour**. So a totally failed pull
is indistinguishable from a good one in the inbox. Aug 1 wrote 9 rows and nothing
deployed between the two days, so the key was live and this was transient —
plausibly the 8-second `FETCH_TIMEOUT` on the v2 call.

**Fixed 2026-08-02:** the row count now lands in the email body — `9 monitors
archived` normally, a loud red `uptime archive: 0 rows written` when the pull
failed (`_compose` takes `uptime_rows`; dry runs pass None and show nothing).
Same-morning and thresholdless. The `uptime archive` heartbeat from `b179cc1`
remains the backstop for "cron alive, pull broken" at a 2-day threshold.

- **Phase 3 of the uptime plan — COMPLETE 2026-08-02.** musicforge, bakerylouise and
  prntd all shipped `/api/health` and every monitor is repointed off its homepage
  (musicforge's lives only on `www.musicforge.org` — the `.app` domain 404s the path;
  bakerylouise skips the deep Sanity variant on purpose, ISR-cached; prntd is deep
  `?db=1`). raconte is settled: no backend ever, slot closed, the recountly.org
  monitor stays until they post teardown notice.
- **Phase 5 — COMPLETE 2026-08-02.** `TARGETS` now carries all 8 HTTP monitors, and
  a test pins `TARGETS` ⊆ `HTTP_MONITORS` (subset, not equality — paging may
  legitimately cover more than the daily email). Two things fell out of the growth:
  the deep parser knew only `db`/`howl` and rendered ibuild4you, byside and
  pianohouse note-less, since those return the convention's other shape, a
  `checks[]` array — it now summarizes `n/m checks ok` and names only the failures;
  and the poll fans out over a thread pool (`_check_targets`), because sequential
  polling is ~8s at eight targets and `#/health` pays it on every load. 1.6s
  measured. Four older tests that pinned the literal 2-target set now derive from
  `TARGETS`.
- **garm #7 denial-count line** in the health email (`GARM_REPORTING_KEY` shipped on
  garm's side; the garm handoff channel will post the shape).
- **`#/health` has never been visually verified** — both themes were checked by
  computed contrast, not by eye. https://prompt-labs.org/#/health Also unseen:
  **the nav below 640px** — the hamburger path. The 2026-08-05 verification was
  done at a computer, so it covered the wide layout only, and the phone markup is
  a separate CSS branch. (`#/about` and the More panel are verified.) **This sandbox
  cannot render the app at all** — `index.html` pulls Preact from `esm.sh` at
  runtime and the network policy blocks it, so every frontend change here is
  verified by `node --check` over the extracted module plus class-usage greps, and
  needs your eyes before it is real. Don't mistake "tests pass" for "it looks right."
- **Beacon fan-out: `prntd` + `musicforge`** never got the snippet (dirty trees at
  fan-out time). `page_views` has zero rows ever for either. musicforge is Vite
  (`frontend/src/main.tsx`), a different injection than the Next.js root layouts.
- **`/api/private_history` Tier 1 — SHIPPED 2026-08-02**, deployed and verified live
  end-to-end (auth'd smoke test passed). `SERVICE_HISTORY_KEY` in Vercel Production,
  value at `op://dev-secrets/prompt-lab-service-history-key/password`. Ball is in
  selected-projects' court to wire `lib/history.ts`. Tier 2 (narrative behind Garm)
  remains unbuilt by agreement. historyKey settled as `bakerylouise` (alias from
  `bakerylouise-v1`). **This endpoint has no allowlist of its own** — it accepts any
  project and is gated solely by the service key, so don't go looking for one. The
  8-key allowlist is the *public* tier's write gate (see the `public_history` bullet
  above); `bakerylouise` and `songscribe` were added to it alongside this work.
- **Public rollups:** only ibuild4you `2026-05-18` remains unpublished, and that is a
  deliberate skip (cost forensics + internal ops; nothing left after scrubbing). It
  reappears in every future draft by design.
- **#48 time localization — POLICY SET AND INSTANCES FIXED 2026-08-02.** The policy,
  now in the shared-conventions block so every repo carries it: **timestamps are UTC
  at rest, calendar days are `America/Los_Angeles` on display.** Storage in local
  time was rejected — it cannot be migrated across a DST boundary without loss — and
  UTC-on-display was rejected because it makes Nico's day roll over at 5pm.

  What was actually wrong was subtler than the issue described: the raw tier is
  **UTC**, not local, because SQLite's `datetime('now')` is UTC. So three clocks
  disagreed — UTC raw rows, Pacific summary writers, UTC frontend axes — and the
  dashboard drew an `Aug 3` column at 5:30pm on Aug 2 with 13 real prompts in it.

  Fixed: `web/day_helper.py` (`lab_today`/`lab_days_ago`/`lab_window`, in
  `includeFiles`, `tzdata` declared in `web/requirements.txt` — unpinned, but present
  so a missing tzdb can't silently degrade the lambda to UTC); `labDay`/`labDayOf`/`labStamp` in `web/index.html`
  replacing all 14 `toISOString().slice(0,10)` axis builders plus the Ask-history
  stamp; lab-day windows in `activity_timeline`, `overview`, `uptime_overview`; the
  heartbeat freshness grader and the uptime-archive date key in `health_report`; 8
  `date(<ts>)` → `date(<ts>, 'localtime')` bucketings in `store/sqlite_store.py`; and
  `today-counts` in `workflow/bin/gc-read.sh`, which now reads 14/4/5 for an evening
  that used to read 0/0/0. **`daily_summaries.date` deliberately did NOT get
  `'localtime'`** — it is already a calendar day, and shifting it would be the same
  bug pointed the other way. Four existing tests derived their own expectations in
  UTC and so passed by day and failed by night; they now go through `lab_today()`.
  Four `clocks:` drift guards were added — two are greps over the source, because
  the failure is invisible to a test that computes its own date.

  Still open on #48: the "8am" cron is `0 15 * * *`, which is 8am Pacific in summer
  and **7am in winter** — Vercel crons are UTC-only, so this is a choice to make
  (accept the winter hour, or split the schedule), not a bug to fix.
- Open issues: **#14** design tokens (own session), **#27** Garm rollout, **#43**
  sign-ins panel (trigger-gated: fires the day a second reader joins
  `READER_EMAILS`), **#9** beacon fan-out, **#34** health leftovers, **#45** the
  freshness convention, **#50** preload + locally cache per-day aggregates (the
  day page fetches cold and feels sluggish on a phone), **#49** copy review across every dashboard page (filed
  2026-08-02 at Nico's ask — he wants to read it at a computer, not a phone),
  **#51** unmapped costs, **#52** exclude test-agent traffic from `page_views`
  (both filed 2026-08-08 off Nico's backlog list; same list also settled: Ask's
  per-user history is parked with Ask itself, and the selected-projects commit
  counts wait on *their* repo wiring `lib/history.ts`).
- Deferred deliberately: UptimeRobot paid plan / real `HEARTBEAT` monitors.

**Mobile pass, 2026-08-02.** Four things, all from the same phone session:
`DateAxis` replaced six copy-pasted axes (tick count from measured width, labels
absolutely positioned inside a clipped box, plus a dot under each labelled
column so the label maps to a bar without counting); the home chart's tap now
navigates to a real `#/day/<date>` page rather than opening a panel that lands
off-screen when pinch-zoomed — **any overlay positions against the layout
viewport, so a "fixed" sheet fails under zoom exactly like the panel did**, which
is why this is a route and not a modal; `/api/day` backs it so a cold-opened link
to any date works; the nav collapses behind one button below 640px (both markups
always render, CSS picks — no viewport state in JS to desync on rotate); and 7d
joined the window toggles. Home offers 7|30 only, because it reads `overview`,
which is capped at 30 days and stays lean on purpose.

Round two, same evening, all three from one phone screenshot. **The wide nav and
the hamburger both rendered at once** because `display:contents` was set INLINE on
the wrapper — an inline style outranks every selector, so the media query could
never hide it. Moved to CSS. **Every chart now navigates to the day page** and all
four below-chart panels are gone; `/api/day` grew spend/visitors/uptime sections
so nothing was lost with them. **Today's column is drawn as a dashed outline and
the day page carries a "Today, so far" banner** — counts come from
`daily_summaries`, written at `/handoff` time, so a live session isn't in them and
a short solid bar read as "a quiet day" instead of "not tallied yet." That is this
repo's recurring failure shape rendered as a chart.

Round three: the nav is two tiers. PRIMARY is the five views; everything else —
Ask (an action, not a destination), About, theme, email, log out, build stamp —
sits behind **More**, because mixing them put "Log out" the same distance from a
thumb as "Costs". One declaration renders both navs. The header's built/synced
sub-line is gone; that detail lives on the new `#/about` page and as a terse
stamp at the foot of the More panel. **Not yet verified by eye** — shipped after
Nico signed off for the night.

### The failure shape this repo keeps hitting

Eight incidents now share one shape: **a job keeps running while its output stops,
and the absence is recorded as "nothing" rather than "failure."** The review email
403'd for 60 nights while `review_snapshots` simply froze, reading as "the job
stopped" instead of "the job fails at its last step." The bi-monthly report was dead
4 months because its plist did `source <deleted-file> && python …` and `&&`
short-circuited. CI was red 3 days with `deploy` showing *skipped*, not failed.

Two mechanisms recur: **a fallback quietly covers the dead primary path**, and
**absence is recorded as nothing.** The countermeasure, shipped as #45: every
recurring job declares a max artifact age, checked with `max(date)` over a table that
already syncs to Turso, reported in the daily health email (`HEARTBEATS` in
`web/api/health_report.py`).

Three rules that fall out of it, each earned:
- **Alarm on the artifact, never on the job's exit status or a synthetic ping.** A
  ping is a side-channel claim that the job ran and can succeed while the artifact is
  missing — precisely how the review email looked healthy for sixty nights.
- **A failed check reports "could not check", never "fresh."** Deliberately *not* the
  fails-open pattern the pause lookup uses in the same module: a Turso outage must not
  block an email, but freshness failing open would rebuild the exact bug. An empty
  table is *stale* ("never produced"), not fresh.
- **Check the job's log before concluding anything from table rows.** The dead review
  email had 60 identical 403s in `send-review.log`. That log only exists under launchd
  — a manual run prints to the terminal instead, so the file looks empty.

Known hole, don't mistake it for closed: the `uptime archive` heartbeat is written and
graded by the *same* request, so it catches "cron alive, pull broken" and cannot catch
"cron dead." That case degrades to "no email arrived," the weakest signal in the
system. Closing it needs a check on infrastructure that fails independently of
Vercel's scheduler; UptimeRobot's `HEARTBEAT` type is paid-only, which is what sent
#45 down the artifact route in the first place.

### Invariants — the things that must not be broken

- **Turso holds no `prompts`, `sessions`, or `commits` tables at all.** Raw prompt
  text, commit messages, hostnames and local paths are physically unreachable from
  `web/`. That is the strongest guarantee in the system. Preserve it by never adding a
  sync leg — not by filtering at read time. Read-time allowlists were tried twice and
  deleted both times for drifting.
- **Cloud-direct tables have no leg in `sync_to_turso.py` and must never gain one:**
  `page_views`, `health_email_state`, `project_metadata`, `issue_categories`,
  `uptime_daily`. That absence is what makes drift structurally impossible.
- **Nothing automated writes the `public_*` tables.** They are written only by the
  reviewed, git-committed draft-to-artifact flow (`scripts/draft_public_refresh.py` →
  human review → `scripts/publish_public_draft.py`). Never by `/handoff`, the
  synthesizer, or raw sync. The invariant is "never write un-scrubbed text into the
  public tables."
- **The uptime archive is never backfilled.** UptimeRobot exposes rolling ratios, not
  per-day history, so a gap is missing data — render it grey, never 0%. An invented
  past would be worse than a short one.
- **Cross-repo work goes through `~/src/.handoff`, never a PR from here.** The repo
  boundary is the ownership boundary and each repo's agent owns its conventions. The
  practical tell: agents working in a sibling repo run from a cold permission slate, so
  a wall of permission prompts mid-task is the convention signalling it's being
  bypassed, not a config annoyance to route around.

### Traps that cost real time

- **`gc-read.sh`/`gc-write.sh` derive project via `basename($PWD)`, not the
  git-common-dir fix `log-prompt.sh` got 2026-08-05.** Run either from a
  worktree under `.claude/worktrees/<name>/` and `PROJECT` resolves to
  `<name>`, not the real repo — `current-session`, `today-counts`, and
  `weekly-rollup-check` all silently return nothing/zero even when the real
  session (found under the correct project via the hook's own resolution)
  has real prompts and commits. Hit during `/handoff` from a worktree
  2026-08-15. Workaround: query `sessions`/`prompts`/`commits` directly by
  id when this happens; the actual fix (mirror `log-prompt.sh`'s
  `git rev-parse --git-common-dir` resolution in both scripts) is unstarted.

- **`workflow/bin/*` and `workflow/commands/*` run from installed copies under
  `~/.claude/`, not from the repo.** A fix committed to the repo is not live
  until copied over (per machine!). Bit hard 2026-08-10: the Monday week-bug
  fix landed in `workflow/bin/gc-read.sh` while the installed copy kept the
  buggy SQL, and `/handoff`'s rollup check invented two phantom missing weeks
  from Monday-dated summaries. After fixing anything under `workflow/`,
  diff-sweep: `for f in workflow/bin/* ; do diff -q "$f" ~/.claude/bin/$(basename "$f"); done`
  (and the same for commands) — on BOTH machines.

- **`tail -r` is BSD-only; CI is Linux.** `log-prompt.sh` reversed the
  transcript with `tail -r`, which works on the Macs it actually runs on and
  silently produces nothing everywhere else — so `prompts.context` was empty on
  any Linux host and nobody knew, because no test asserted on the column until
  2026-08-14. The hook now detects (`tail -r /dev/null` → else `tac`). The
  general lesson: a macOS-only shell idiom in `workflow/` is a latent bug the
  moment the code touches a Pi (phrpi is Debian) or CI, and it fails by
  producing empty output rather than an error.
- **A Vercel-origin service behind Cloudflare bot protection fails ~95%, not
  100%, and the partial failure impersonates a rate limit.** Diagnosed on SPAN
  2026-08-21. Vercel egresses from a rotating pool of AWS IPs; Bot Fight Mode
  scores each independently, so a check occasionally draws an unchallenged IP,
  succeeds once, then fails again on the next draw. That produced UP windows of
  exactly one check interval separated by multi-hour DOWN runs, with gaps
  regular enough (three consecutive at 2:07:4x to the second) that both agents
  on the incident independently reached for "refilling budget / rate limit."
  It was IP roulette. Cloudflare's firewall-events export settles it in
  seconds — read `ruleId`/`source`/`action`, don't infer the control from the
  failure pattern.
- **Two sampling traps from the same incident, both of which produced confident
  wrong answers.** A probe of 10 requests at 3s intervals spans 30 seconds and
  cannot distinguish "blocked 100%" from "~5% pass rate spread over hours" — at
  p=0.05, 10/10 failures is the *expected* result ~60% of the time. And
  UptimeRobot's v2 log caps at **25 entries** regardless of `logs_limit`, while
  Cloudflare's firewall-events export caps at **500** — so neither bounds an
  onset time, and the oldest visible entry is a cap artifact, not a start.
  Before accepting any peer's "we tested it, it isn't that", ask what sampling
  window produced it.
- **Turso returns `SUM()`/`COUNT()` aggregates as JSON strings.** An explicit `int()`
  coalesce is load-bearing — without it chart math concatenates instead of adding.
- **UptimeRobot v2's `custom_uptime_ratio` is a string** (`"100.000-99.980-99.990"`,
  1d-7d-30d). Split and float, or every downstream average is text.
- **The SPA catch-all serves `index.html` with a 200 for unknown paths.** A health
  target pointed at a nonexistent path becomes a permanent false UP. Health targets
  must also be unauthenticated — the first health email false-DOWNed prompt-labs.org
  by polling auth-gated `/api/info`.
- **`vercel env add` takes no value argument** — it opens an interactive prompt and
  reads one line from stdin, so the trailing newline is the *submit*. Never pipe
  through `tr -d '\n'` (it blocks forever, writes nothing, exits without error) and
  never wrap it in a `for` loop (the first prompt seizes the TTY). Always verify with
  `vercel env ls`: a good write reads seconds old.
- **`op inject` substitutes `op://` references inside `#` comments** — a commented
  reference is still live, and one unresolvable ref aborts the whole file. And
  `op inject -i .env.tpl -o .env.local` is **not** a working workflow here: the
  template is the union of local + cloud secrets, so regenerating locally tries to
  materialize cloud-only values. Append single variables instead.
- **The public-draft path regex only matches `/Users/…`.** Tilde paths (`~/src/…`)
  sail straight through — a human-only catch.
- **Reading `/api/public_history`: the envelope key is `rollups`, not
  `weekly_rollups`.** A probe using the wrong key reports 0 rows on a healthy endpoint.
- **A missing site in `#/visitors` is a hole, not a zero.** recountly showed zero rows
  for weeks because the beacon had never once fired, not because there was no traffic.
- **prntd's domain is `.org`, not `.com`.** pianohouse must be monitored at **www**,
  not the apex — the apex 307s, and a monitor leaning on redirect-following is one
  setting away from a false DOWN.
- **Vercel log retention is ~1 hour.** Post-hoc forensics on a daily cron is not
  available.
- **CI ruff is pinned to `0.15.22` — don't unpin.** An unpinned `pip install ruff`
  grabbed a new release and produced 339 new-rule errors on a docs-only push. Local
  ruff passing while CI fails on a docs commit = version drift; check the pin first.
- **`deploy` has `needs: test`**, so a starved or failing test run shows as *skipped*,
  not failed, and no prod deploy goes out silently.
- **Three Vercel diagnostics that produce false conclusions — don't reuse them:**
  `gh api repos/:owner/:repo/hooks` is no evidence about Vercel linkage (Vercel
  connects via a GitHub App, which creates no repo-level webhooks — check `link` on
  `GET /v9/projects/<id>`); grepping served HTML for `_vercel/insights` false-negatives
  on any current site (`@vercel/analytics` 2.x uses a randomized anti-adblock path);
  and `githubCommitSha`/`githubCommitRef` on a deployment do **not** imply a git
  trigger (the CLI stamps local checkout metadata onto manual deploys). The real tell
  for "never linked" is zero preview deployments across the project's whole history.

### Testing

Tests are standalone runners, **not pytest** — `python -m pytest` fails at collection.
Run each directly:

```bash
for f in scripts/test_*.py; do .venv/bin/python "$f"; done
```

~243 tests across 7 files as of 2026-08-04 (162 in `test_web_api.py`, plus alias-layer
22, cost-pipeline 22, public-draft 21, session-identity 9, heartbeat 7, and
`test_imports.py`, which is an import smoke script with no test cases).
`_health_mod(up=, hb=, ur=)` stubs the health endpoint; its Turso stub dispatches on
the SQL because the pause lookup, the freshness lookups and the uptime upsert share
`turso_query` and must not be conflated — pause fails open, freshness fails loud, and
the archive write must be separately observable.

### Settled — don't re-litigate

- **UptimeRobot is the sensor AND the pager; prompt-lab samples nothing and pages for
  nothing.** 5-min polling on independent infra, free tier, 3-month retention. Ratified
  in garm's 2026-07-29 handoff: prompt-lab shares the Vercel+Turso+Resend stack, so a
  watcher built on it would die with the watched. No Pi, no launchd sampler.
  API facts, probed live (the published docs are thin and partly wrong): **v3
  provisions but has no history endpoints** (`/logs`, `/response-times`, `/uptimes` all
  404); **v2 legacy is the only source of history** and works on free; `HEARTBEAT` type
  needs a paid plan (403 `009-005` at every interval and grace value); free tier is 50
  monitors, 5-min interval, 10 req/min, 3-month retention.
- **OAuth is hand-rolled in Python, zero new deps.** Because this is a confidential
  client doing its own server-side code exchange, the `id_token` arrives from Google
  over TLS — no JWT signature verification, no JWKS fetch, no crypto dependency.
  Rejected: Next.js conversion, mixed Node+Python runtime, third-party auth. Spec in
  `docs/phase2-oauth-plan.md` — read it before touching auth. `verify_token` requires
  both `role` and `email` **keys** (key-presence, not truthiness) — that subtlety is
  load-bearing.
- **No display names in the sign-ins panel.** With two accounts the beacon role already
  identifies the person, and a name would cost the log's anonymity. #43 tracks the
  trigger: when a second reader joins, the fix is a stable **opaque per-user id** (HMAC
  of email under a server salt, like `visitor_hash`) — never an email or a name.
- **First-party beacon over Vercel Analytics.** Drains are Pro-only and Hobby Analytics
  has no read API, so it could never feed a unified dashboard. The beacon is also
  hosting-neutral and writes cloud-direct.
- **The public tier's curation is the consumer's job** — the `selected-projects` MDX
  manifest is the single source of truth for which projects appear publicly.
  `docs/public-allowlist.txt` mirrors it and gates *writes*, not reads.
- **The public-draft division of labour:** the machine refuses to publish on anything
  regex-able (absolute paths, emails, credential tokens, internal DB hosts, unedited
  blockquotes, prose <15 words, prose ≥75% similar to the private source). The human
  owns the four things regexes structurally cannot see: **named people/orgs,
  identifiability-by-description, unreleased plans stated as fact, and commercially or
  personally sensitive detail.**
- **`private` on `project_metadata` is cosmetic only** — a hide-toggle, not the
  public-data gate, and it does not gate any API. `public_counts` is the real gate.
- **Machine-voice convention:** any AI-authored text renders italic + muted with a
  `↳ from claude` marker.

<!-- SHARED-CONVENTIONS:BEGIN v=e5fb79b2ef4d — auto-managed, do not edit here; source: prompt-lab/workflow/claude-md-shared.md (edit + re-sync) -->
## Shared conventions

<!-- These are Nico's cross-repo output rules. They're materialized into each repo's
CLAUDE.md so every agent (local, cloud, third-party) sees them as plain text. Source
of truth: prompt-lab/workflow/claude-md-shared.md — edit there and re-sync, never here. -->

- **Clickable URLs.** When pointing at any web destination (dashboard, repo, PR, deploy, settings, docs, localhost), print the full bare URL — `https://example.com` or `http://localhost:8080` — on its own, never just the page's name and never a markdown `[label](url)` link. Nico's terminal auto-linkifies raw `https://` text, so a bare URL is one-click and stays copyable.

- **Number your questions.** Any time you ask Nico more than one question, present them as a numbered list (1., 2., 3.) so he can answer by number with no ambiguity. A single standalone question needs no number.

- **Self-contained smoke-test instructions.** When you ask Nico to manually test or verify an app or website, assume zero carried-over context — he should never scroll back or recall a URL/path/credential from earlier. Always include: the exact URL (full `https://…` or `http://localhost:…`, restated even if mentioned above), the precise steps in order, and what a pass vs. fail looks like. Repetition here is a feature, not clutter.

- **UTC at rest, Pacific on display.** Timestamps are stored in UTC, always. A *calendar day* shown to a human is `America/Los_Angeles` — Nico's day, and the clock the work actually happened on. The two rules that follow are the ones that get broken: never form a date bucket with `new Date(…).toISOString().slice(0,10)` (that is UTC, so every chart axis and "today" silently rolls over at 5pm Pacific — it put a phantom tomorrow bar on the Prompt Lab dashboard), and never bucket UTC-stamped rows with a bare `date(col)` in SQL. Use `Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' })` in JS and an explicit zone in SQL/Python. Storage in local time is also wrong — it can't be migrated across a DST boundary without loss.

- **No marker before a copy-paste command block.** Nico's terminal renders markdown bullets (`-`, `*`, `•`) as `●`, which breaks paste into zsh. The line directly above a fenced command block must be a plain-text label ending in a colon — never a bullet, dash, asterisk, or number. For loud copy targets, lead the label with `📋` + bold `COPY THE BELOW`, then a colon, then the block.
<!-- SHARED-CONVENTIONS:END -->
