# Current work and deferred decisions

Open items only. Shipped work is in git and the narrative is in `history.md`.
Trimmed 2026-11-14; the long version is this file's git history.

## Open

- **Review kit.** PR open, branch `claude/review-kit`: a read-only reviewer agent, a "Landing a change" section for CLAUDE.md and a PR template. After the merge, start a new session and confirm the `reviewer` agent dispatches by name.
- **elusion's bulletin ask (handoff 2026-11-06).** A new `op://` reference in `.env.tpl` comes with an `op item create` command. Not yet answered.
- **Review emails after the design pass.** Read a few built since 2026-11-05 and judge the layout.
- **ntz-conveyor in `~/src/mini-rescue/`.** Kept until person-tracking confirms its gitignored `db.sqlite3` data lives elsewhere (asked 2026-11-03).
- **Open issues:** #43 sign-ins panel (waits on a second reader), #9 beacon fan-out, #85 second language for `/localize`.
- **Nightly pipeline step 4** (outstanding-work queries for the readers) is unbuilt. Report catch-up already covers most of it.

## Waiting on other repos

- Playwright 1.60.0 cannot install on GitHub's ubuntu-26.04 runners; 1.62.1 and later can. prntd and split-recording are fixed. musicforge and bakerylouise-v1 were told 2026-11-09.
- `AGENTS.md` is still committed in musicforge, person-tracking and split-recording. Each repo's call.
- Two Pi leftovers, filed in `~/src/.handoff`: a laptop SSH key into Home Assistant's add-on, and repointing hardcoded `192.168.5.34` to `homeassistant.local`. See `pi-inventory.md`.
- Tideline needs its own `tideline`-scoped Garm consumer key.

## Garm

`GARM_GATING` is off for this dashboard and `READER_EMAILS` is the live gate. Off is a
Vercel env var, not the code default, so check `vercel env ls` before trusting this line.
Garm is the record of app admins; prompt-lab relays between garm, ibuild4you and the app
repos through handoff. Loop Phase B is live (2026-10-31). The reader-side design is in
`garm-consumer-plan.md`.

## How-to

- **New 1Password item.** Create its secret field with the literal placeholder `replace-this-value`; Nico pastes the real value in 1Password.
- **Unmapped API spend.** A new workspace lands as `__unmapped__` and the health email says so. Add it to `scripts/seed_project_workspaces.py`, run that with `--remap`, then run a FULL `sync_to_turso.py`: the nightly `--days 7` sync never carries older remapped rows.
- **Neon compute per project, this month.** `neonctl projects get <id> --org-id org-spring-cherry-36158724`.
- **Before deleting a rescued checkout,** run `git status --ignored`. A clean `git status` is not "nothing unique".

## Settled

- stars-demo is not being onboarded (2026-10-09). It stays a grey "more" entry in the chart.
- The health cron is `0 15 * * *`: 8am Pacific in summer, 7am in winter. Vercel crons are UTC-only. Not a bug.
- ibuild4you's `2026-05-18` public rollup is a deliberate skip and reappears in every draft.
- The `spike` project (4 prompts) stays unaliased.
- Parked from the design review: the iOS standalone status bar is `black-translucent`, so `theme-color` may not show; dark `--chart-1` could become `#5558e6`.

## Deferred

- UptimeRobot paid plan and real `HEARTBEAT` monitors. The mini (shut down 2026-09-25) could become the independent watcher for the "cron dead" hole.
- Cross-machine `weekly_rollups` reconciliation, until it bites.
