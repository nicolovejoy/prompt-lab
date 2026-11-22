# Current work and deferred decisions

Open items only. Shipped work is in git and the narrative is in `history.md`.
Trimmed 2026-11-14; the long version is this file's git history.

## Open

- **`block-secrets.sh` does not parse quotes, on purpose (2026-11-21).** A quoted commit message, note or PR body that mentions a reader command, an `op` command or a secret file is blocked; pass it by heredoc or from a file. A quote-aware version was built and dropped (PR #122's first three commits): two review rounds each found ways past its parser, and on 6,000 real commands it cleared no more false blocks than the simple version. A second attempt cut quoted text out with `sed` before expanding wildcards; review showed mis-paired quote marks hid unquoted words. What shipped expands every word, as before, and drops only a bare `.*` split out of a quoted search pattern. A small scanner (`mark_quoted_stars`) decides that. The quoted string must hold no reader verb, must be more than `.*` alone and must not start with a colon (a git pathspec). The exception is off for a command that names a second shell (`sh`, `ssh`, `eval` and the rest of `RUNNER`) and for anything unusual (a `#`, a backslash, a backtick, `$(` inside double quotes). What it gives up against the old hook: a quoted `.*` that something outside that list expands later from a string that names no reader, such as `python3 -c "glob.glob('.*')"`.
- **`block-secrets.sh` still lets these through (found 2026-11-21; none is new).**
  - A heredoc fed to a shell or interpreter (`bash <<EOF`, `python3 <<EOF`) is treated as file contents, so a reader inside it is not seen. `strip_heredocs` also drops the rest of the line after `<<TAG` and takes a `<<` inside quotes for a heredoc.
  - A secret file reached through a variable (`F=.env; cat "$F"`) is not classified.
  - A recursive read that names no file: `grep -rn KEY .`, and its twin with a catch-all pattern, `find . -name "*" -exec cat {} +`.
  - A file printed by a command that is not on the reader list: `cp .env /dev/stdout`, `diff`, `jq -R`, `dd`, `tac`, `nl`, `paste`, `git diff --no-index`. Also a reader the list cannot see: `$(which cat) .env`, `{cat,.env}`.
  - `echo "$CMD" | grep -q` under `pipefail` can die of SIGPIPE on a command of tens of KB and read as no match.
  - The hook's test is not in CI: it needs `jq`, and the hook's `grep` and `sed` use is only proven on macOS.
- **Left by the unreadable-repository fix (2026-11-21).** `sync-shared-fleet.sh` still skips a repository git cannot read without a trace (`rev-parse ... || continue`). `scripts/test_session_context.py` is not in the CI gate: it only works from under `~/src` and touches the real nudge stamp in `~/.claude/state`.
- **Review emails after the design pass.** Read a few built since 2026-11-05 and judge the layout.
- **ntz-conveyor in `~/src/mini-rescue/`.** Kept until person-tracking confirms its gitignored `db.sqlite3` data lives elsewhere (asked 2026-11-03).
- **Open issues:** #43 sign-ins panel (waits on a second reader), #9 beacon fan-out, #85 second language for `/localize`.
- **Nightly pipeline step 4** (outstanding-work queries for the readers) is unbuilt. Report catch-up already covers most of it.

## Waiting on other repos

- ear-worm's shared Fossil repo does not exist yet. Until it does, `/readup` reports `REMOTE=fossil-unchecked` and nothing checks a Fossil remote.
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

- **New 1Password item.** Hand Nico the `op item create` command, with the secret field set to the literal placeholder `replace-this-value`; he pastes the real value in 1Password. Full rule: `BULLETIN.md`, 2026-11-20.
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
