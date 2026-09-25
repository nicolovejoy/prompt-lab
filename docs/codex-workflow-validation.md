# Readup and handoff validation

## Hook request consumer — Phase 4 step 2, review gate (2026-09-19)

Implemented and tested with disposable data only. No installed files, permission
profiles, real history DB, or live rows were read/changed. `scripts/test_hook_bookkeeping.py`
is a standalone CI runner using staged copies of the actual entry point plus
`_gc_session_identity.py` and `_gc_project.sh`, fake SQLite and throwaway Git.

Twenty scenario groups pass: stable repeated/concurrent registration and resume;
distinct peer/fork IDs; absent, inconsistent and wrong identity; zero/nonzero commits;
original UTC commit seconds; global first-hash attribution with/without the #57
unique index; concurrent commits and UUID/content replay; summary/closure isolation;
request/open/lock/commit/summary/ledger failure rollback; host receipts and no-request
pending state; repeated Stop; real process death after commit before output;
malformed, deeply nested, oversized, symlink, hard-link, FIFO, writable and replaced
files; unknown/duplicate JSON keys; dependency symlinks, environment import injection
and dot-dot placement; and planted peer requests without the owner's final-message
digest. Required-save failures leave open rows open and request bytes recoverable.

The CLI 0.155.1 localhost Responses fixture passed with the actual staged consumer:
nonzero-commit save and wrong-ID rejection, each with three model requests (tool,
queued final, host continuation). The real Stop final message carried the authored
UUID/digest. A committed `GC_RECEIPT` arrived only via `decision: "block"`; repeated
Stop terminated without a loop. Evidence:
`/private/tmp/prompt-lab-hook-probe-ptm2kn3r/{continue,reject}/`.
The deterministic model stub proves transport, not an LLM's adherence to the command.

Repeat the disposable checks from the source checkout:

```bash
python3 scripts/test_hook_bookkeeping.py
python3 scripts/probe_codex_hooks.py --consumer --outer-sandbox
```

Pass: 17 standalone groups and two CLI `PASS` results. Any traceback, missing identity,
receipt or nonzero-commit result is a failure. `--outer-sandbox` avoids unsupported
nested macOS Seatbelt while retaining this session's enclosing sandbox. It does
**not** test the nested production profile. From an ordinary human terminal, omit
that flag to test the fixture's own temporary deny profile; that mode is still gated.

### Contract and remaining limits

- Host events supply conversation, cwd and turn; the existing resolver binds a
  `codex:<conversation>` identity. `log-prompt.sh` also runs for Codex; it detects
  a Codex payload (a `turn_id`, or a `rollout-*.jsonl` transcript) and registers the
  same `codex:<conversation>` owner, so prompts land on the consumer's row. Claude
  payloads keep the bare native UUID. Two rows owned by one `codex:` identity fail
  explicitly. Historical bare-native Codex rows (written before this rule) are
  ignored: never adopted, rewritten or treated as a collision, since the consumer
  never handed one to an agent. A resumed pre-rule conversation gets a new row.
- One injected workspace filename per project/conversation; no directory scanning.
  UUID plus SHA-256 in the host Stop final message authorizes the exact new bytes.
  The agent computes this from authored bytes before publishing, never by adopting
  an unknown pending file. Strict bounded JSON admits only the lean write operation.
- Save transaction also records `hook_bookkeeping_requests`, keyed globally by UUID
  and bound to project/conversation/session/content digest. Existing commit hashes
  retain their first row unchanged; no historical deduplication runs. The ledger is
  local bookkeeping and has no cloud sync leg.
- Receipt delivery cannot be atomic with SQLite. A committed receipt is replayable;
  its turn is marked emitted only after stdout flush. A crash before that mark can
  repeat the receipt, never the save. A missing model-visible receipt stays pending;
  later-turn replay can deliver it again. Input files are never removed by the hook,
  so delivery is once: after the receipt is marked emitted, a Stop whose final
  message lacks the matching `GC_REQUEST` marker outputs `{}`.
- Structural checks reject workspace dependencies and symlinks; `-I -S` excludes
  cwd/PYTHONPATH/site hooks. **Actual OS protection of the bundle, config, interpreter,
  stdlib and DB still requires a fresh production-profile pilot.** File modes alone
  cannot make code unwritable to a same-user agent. No permission widening is allowed.
- Codex readup avoids DB-backed bundled checks; full handoff, context/pulse reads and
  raw prompt capture have no new host contract. The dedicated Codex hook replaces
  legacy Codex registrations through Claude's prompt hook in the pilot. Claude's
  hooks and direct-helper path remain unchanged and their regression suites pass.
- Production profile, live DB pilot, Desktop, fresh-launcher resume/fork, and actual
  LLM adherence remain untested. This is step 2 only, not rollout acceptance.

### Step 3 — Nico's installation after review only

Do not run these steps as part of this PR. Review/merge the source, then use a normal
human terminal on the pilot machine. Do not use the broad workflow installer merely
to enable this pilot; it also updates unrelated shell/launchd configuration.

1. Run the disposable tests above and the CLI probe without `--outer-sandbox` from
   that normal terminal. Record the CLI version, reviewed commit and results.
2. Stage a fresh versioned bundle outside every agent-writable path. The following
   example targets this clone; choose only the intended pilot workspace. The tool
   refuses an existing destination and does not open the database or enable hooks.

Stage the reviewed bundle (human only, after review):

```bash
cd /Users/nico/src/prompt-lab-codex
python3 scripts/stage_codex_bookkeeping.py \
  --destination /Users/nico/.claude/codex-bookkeeping-step2 \
  --db /Users/nico/.claude/prompt-history.db \
  --workspace /Users/nico/src/prompt-lab-codex
```

3. Back up the existing Codex hook configuration and the three affected skills.
   Review the generated `hooks.toml`, then merge its `SessionStart`,
   `UserPromptSubmit`, and `Stop` entries into the Codex runtime configuration for
   this pilot. Use the absolute command exactly as generated (`python -I -S` plus
   the copied entry point). The shared `log-prompt.sh` may stay: it registers
   Codex prompts under `codex:<conversation>`. Remove any other legacy **Codex-only**
   registration hook that would mint bare-native rows; leave Claude's configuration
   untouched.
   Copy the generated `skills/source-command-readup`, `source-command-handoff`, and
   `source-command-handoff-full` directories into `/Users/nico/.agents/skills/`.
   The general installer no longer generates the retired `gc-write` approval rule;
   review/remove that obsolete rule separately, never broaden it.
4. Confirm the effective existing profile prevents agent writes to the bundle,
   config, interpreter and all dependencies, and retains DB/secret denial. If any
   dependency is writable, stop the pilot; do not weaken protection. Launch a fresh
   Codex conversation through `cx prompt-lab`, record effective profile/rules and
   helper revision, and follow Phase 4 step 3 with disposable nonzero Git commits.
   Readup must receive the host identity. Handoff must report queued with one digest
   marker, receive a matching host receipt, then acknowledge saved. Nico verifies
   persisted records through an authorized host interface. Missing identity,
   unsupported final-message payload, denied hooks or missing receipt means failure.
5. Resume/fork and Claude-pair checks are step 4; Desktop needs independent evidence.
   Expand only after those gates. To disable a failed pilot, restore the prior hook
   configuration and report bookkeeping unavailable; do not expose the database.

## Hook lifecycle probe — passed 2026-09-19 (fixture only)

`scripts/probe_codex_hooks.py` exercised the installed Codex CLI 0.155.1 against
a localhost Responses stub, temporary hooks and a fake SQLite database. No paid
model calls, real credentials, installed hooks or live history were used. The
child had its own temporary Codex configuration directory, in-memory credential
storage, and user config/rules/plugins disabled.

Three cases passed:

- **Identity:** SessionStart and UserPromptSubmit delivered the same native
  conversation and database session ID in the first model request. The actual
  agent tool loop wrote the fake request file.
- **Notification only:** Stop saved the summary and closed the fake session,
  but `systemMessage` did not cause another model request. The final model reply
  remained `QUEUED`; a UI notification alone cannot justify a saved claim.
- **Receipt continuation:** Stop returned `decision: "block"` with the committed
  receipt in `reason`. Codex made one additional model request containing that
  receipt, then ran Stop again with `stop_hook_active=true`. The fixture's replay
  guard ended the turn without a loop. The final reply was `SAVED` with the receipt.
- **Wrong session:** A forged session ID produced a rejection receipt through the
  same continuation. The summary and closure remained NULL; final reply `REJECTED`.

Evidence directories (each contains the exact invocation, hook events, model
context observations, CLI output and persisted-result assertions):

- Notification: `/private/tmp/prompt-lab-hook-probe-zk81xlgw/notify/`
- Save/continuation: `/private/tmp/prompt-lab-hook-probe-ekiz_uss/continue/`
- Rejection: `/private/tmp/prompt-lab-hook-probe-pra6jbo7/reject/`

**Scope:** This proves event ordering and model-visible delivery with a deterministic
stub, not an LLM's interpretation, the production identity adapter, or a hardened
request consumer. macOS refused nested Seatbelt even on the approved retry. The
successful runs used `--outer-sandbox`: the child CLI did not add a second sandbox,
while the enclosing session's sandbox remained active. The temporary fake-DB deny
profile was therefore not exercised in these successful runs. Production profile
acceptance remains pending. Earlier startup attempts failed before any hook ran.

For a repeat from an already sandboxed session, run from the source checkout:

```bash
python3 scripts/probe_codex_hooks.py --outer-sandbox
```

Pass: three `PASS` results; notification has no model receipt, continuation saves
and delivers a receipt, rejection delivers an error without saving. Any assertion
or startup error is a failed/incomplete probe. From a normal terminal, omit
`--outer-sandbox` to exercise the temporary profile too; that mode remains unverified.
This is a manual probe, not a CI test or an install command.

Protocol reference:
https://learn.chatgpt.com/docs/hooks

## Acceptance reopened — 2026-09-19

MusicForge reported `unable to open database file` during readup registration,
followed by handoff stopping without a validated session ID. This is a reported
live failure, not a newly reproduced database check. Source inspection confirms
the profile's database denial and handoff's separate direct-SQLite commit-write
requirement. The installed registration helper matches source. The exact failing
MusicForge invocation/rule handling remains to be established.

The results below are historical evidence. The successful resumed Songpath
handoff preceded the global permission-profile installation and had no commits.
It does not pass the current end-to-end acceptance gate. No new live gate has
passed as part of this documentation update.

Follow the staged recovery in
[the roadmap](codex-workflow-roadmap.md#phase-4--installation-and-live-validation).
Installation and the historical smoke steps require the design and disposable-data
gates to pass first.
New acceptance evidence must record the runtime/version, actual launch path,
effective policy, installed helper revision, stable identity, and persisted results
for registration, validation, nonzero commit capture, summary save, and closure.
Also record retry behavior, peer/fork isolation, and denial/failure handling.
Use disposable data first; direct access to a denied live database is never a
verification step. Human verification or an explicitly permitted interface must
supply the persisted-result evidence.

## Fake-database permission test — reported 2026-09-19

Source: Claude's entry in `~/src/.handoff/prompt-lab-prompt-lab-codex.md`, titled
"fake-DB permission test run — escalation route is closed by Codex's own prompt;
go hook-side". Reported runtime: Codex CLI 0.155.1, throwaway repository and fake
database with an explicit deny. Real DB and installed permissions were untouched.

- Plain helper registration: exit 1, `unable to open database file`.
- Escalated registration and repeat: **not run**; the noninteractive session
  injected `approval_policy=never`. Interactive escalation was not measured.
- UserPromptSubmit nevertheless created a row in the fake database, according to
  the report. This supports investigating a hook interface, not claiming that
  identity injection or Stop-driven handoff already works.
- Separately, Codex's escalated `register-session --help` returned exit 0 without
  another prompt. It exits before DB access and cannot establish registration.

The active explicit prohibition on escalating access to denied paths rules out
that design. The roadmap now requires a disposable hook-lifecycle test: trusted
identity injection, request validation, persistence, and host-origin receipt
delivery. Stop timing must be observed; queued requests cannot be reported saved.
No complete handoff gate has passed, and no hook changes have been installed.

## Earlier verification scope

### Approval-rule probe — 2026-09-19 (historical)

Codex invoked `/Users/nico/.claude/bin/gc-write.sh register-session --help` using
`sandbox_permissions = "require_escalated"`. It returned the installed identity
helper's usage and exit 0 without a further approval prompt. Source inspection
establishes that argument parsing exits before any database connection.

This tests acceptance of the escalated command prefix only. It does not test
registration, ID read-back, DB access, or complete handoff. The active session's
DB denial was explicitly non-escalatable, so none of those live operations was
attempted. No implementation or installed files were changed. The original
recommendation to wait for a permitted disposable-data test before selecting the
implementation route predates, and is superseded by, the decision to drop
escalation recorded above. Retain this probe as evidence, not a live recovery gate.

## Earlier fixture and paired-session scope

The source changes are exercised against temporary databases and temporary
installed helper copies. They do not install a permission profile, change
launchd, or repair existing session rows. The remaining acceptance check is a
real Claude/Codex conversation pair after Nico installs the updated workflow;
that paired check passed on 2026-09-14 as recorded below.

## Live results — 2026-09-14

Nico reports installing the workflow containing `f5cb2cf`. The paired exercise
uses Songpath with distinct read-only audits: Claude reviews Notes completion
rules; Codex reviews Wild Flowers derivation readiness. Coordination is recorded
in `~/src/.handoff/songpath-prompt-lab.md`.

- Both sessions reported stable repeated registration: Claude `596`, Codex `595`.
- Claude's handoff saved its summary and closed only `596` at 08:28:02 Pacific.
  A read-only database check confirmed `595` remained open with no session summary.
  The daily account retained both audits, with two sessions and zero commits.
- Codex's ordered handoff closed `595` at 11:15:49 Pacific, leaving Claude's
  closure unchanged. The final daily row retained both audits and prior decisions,
  with 15 prompts, two sessions and zero commits. Both agents reported successful
  guarded saves without revision conflicts. Read-only database verification found
  Claude's previous prose and the initial readup prose in the superseded archive.
  The paired exercise passed; both sessions received a DONE message.
- Fresh-launcher resume/fork acceptance and permission-profile installation remain
  separate, unverified gates.

### Codex command-interface follow-up

The first installed lean-command smoke later on 2026-09-14 found a separate
interface failure: Codex CLI 0.154.0 did not register the correctly installed
`~/.codex/prompts/readup.md`, and both `/readup` and `/prompts:readup` were rejected.
Plain-text and misspelled attempts caused the model to improvise only
`readup-checks.sh`; the absence of the required `<session_id>|<started_at>` proved
that readup had not run. The desktop Claude importer had created a discoverable
`source-command-readup` skill, but corrupted its body by rewriting
`~/.claude/bin` to nonexistent `~/.Codex/bin` and `CLAUDE.md` to `AGENTS.md`.

The source installer now renders the canonical command files directly to
explicit-only `~/.agents/skills/source-command-*/` skills. After reinstalling,
the `$source-command-readup` live smoke passed in a fresh Codex session. Two
successive invocations reported the same authoritative identity,
`610|2026-09-14 22:50:41`. A read-only database check confirmed that row `610`
belongs to Songpath, remained open, and had no session summary after readup.

The subsequent `$source-command-handoff` reached the correct row but initially failed its
first write with `attempt to write a readonly database`. It stopped before closing
`610`, as required; a read-only check confirmed the row was still open and empty.
Cause: the database is outside Songpath's writable workspace, and handoff's heredoc
command could not match a narrow executable-prefix rule. The source installer now
adds `prompt-lab-session.rules` for only the installed `gc-write.sh` subcommands,
and Codex handoff passes its summary through a constrained, consumed
`/tmp/gc-session-<id>-<nonce>.txt` file. After reinstalling, the exact native Codex
thread was resumed directly. Readup retained `610`; handoff saved a 604-character
Wild Flowers audit and closed the row at `2026-09-15 22:43:17` UTC. The Songpath
tree remained clean and there were no commits. The narrow-rule live acceptance passed.

Readup also created an initial daily summary before either handoff. Its stored
session count was zero despite the two open sessions; Claude's guarded handoff
subsequently wrote two. Track that older readup synthesis path separately from
the new handoff path when simplifying the commands.

## Lean follow-up smoke test

Source verification after the command-interface follow-up: all 26 standalone
script suites passed locally, including exact rendering of every command into a
skill and its explicit-only policy. Ruff, installer shell syntax and whitespace
checks passed. Heartbeat tests required permission to bind a local test server;
session-context tests required access to their installed-state marker. The
installed readup, repeated-identity, resumed handoff, and narrow-rule checks now
pass. Full handoff, fresh-launcher fork, and live nightly acceptance remain pending.
The failure path also passed: it left session `610` open after the denied write.

Run the automated tests from `/Users/nico/src/prompt-lab`. They use disposable
local databases and a stubbed model response; no live API calls or history edits:

```bash
cd /Users/nico/src/prompt-lab
.venv/bin/python scripts/test_lean_nightly.py
.venv/bin/python scripts/test_workflow_roundtrip.py
.venv/bin/python scripts/test_install_codex_prompts.py
.venv/bin/python scripts/test_handoff_md_structure.py
.venv/bin/python scripts/test_readup_md_structure.py
```

Pass: each command exits zero. The nightly test deliberately prints one
`ERROR: Day context changed` before its final PASS: that proves a concurrent
peer save is preserved rather than overwritten. Any assertion/traceback is a fail.

Only after the revised pilot gate authorizes installation, Nico installs the
reviewed commands and opens fresh terminal/agent windows:

```bash
cd /Users/nico/src/prompt-lab
./workflow/install.sh
```

Use `work songpath` for Claude and `cx songpath` for Codex. In each session:

1. Run `/readup` (Codex: `$source-command-readup`). Retain the returned ID. Repeat once:
   pass means the ID stays the same, differs from the other session's ID, and
   readup does not generate any daily summary.
2. Ask for a tiny read-only audit: Claude describes Notes full-song versus loop
   credit; Codex describes Wild Flowers derivation readiness. No code/doc edits,
   services, or new child agents.
3. Run `/handoff` (Codex: `$source-command-handoff`), Claude first then Codex. Pass means
   each writes a useful session summary and closes only its own ID, leaves the
   repository unchanged, and does not synthesize daily/weekly recaps or trim docs.
4. For the explicit full path, reopen either conversation and run `/handoff-full`
   (Codex: `$source-command-handoff-full`). Pass means fresh whole-day input includes both
   session summaries, the guarded daily save retains both audits/decisions, and
   prior changed prose remains archived. No project-doc maintenance should run.
5. Resume that same Codex conversation in a fresh launcher. Readup must retain
   its ID; a new/forked conversation must get a distinct ID. This fresh-launcher
   check remains a live acceptance gate, separate from fixture coverage.

Use an explicitly permitted interface, or ask Nico to verify only the two recorded
session rows, the Songpath Pacific-day daily summary and its superseded rows.
An agent whose policy denies the DB must not execute direct queries. A missing/wrong
identity, missing contribution, unintended doc edit, or routine recap write is a failure.
Do not repair live rows to make the test pass.

For nightly acceptance, leave one ordinary session with only a lean handoff and
check the next successful night's artifact: its completed Pacific day must
include that session's findings. Check `nightly-pipeline.log` for stage failures.
Do not manually trigger the full pipeline just for this smoke test: it can send
review email. The live nightly/API-cost check is still pending.

## Local checks


From `/Users/nico/src/prompt-lab`:

```bash
.venv/bin/python scripts/test_readup_checks.py
.venv/bin/python scripts/test_public_allowlist.py
.venv/bin/python scripts/test_session_identity.py
.venv/bin/python scripts/test_day_context.py
.venv/bin/python scripts/test_workflow_roundtrip.py
.venv/bin/python scripts/test_readup_md_structure.py
.venv/bin/python scripts/test_handoff_md_structure.py
.venv/bin/python scripts/test_install_codex_prompts.py
.venv/bin/python scripts/test_paid_artifacts.py
.venv/bin/python scripts/test_sync_clobber.py
.venv/bin/ruff check . --exclude .venv
```

The roundtrip test copies the actual helper files into a temporary HOME. It
registers two conversations, checks stable distinct IDs, writes distinct session
summaries, fetches both in whole-day context, rejects a stale second daily write,
preserves the prior prose in the archive, and closes only the intended row.
The day tests cover Pacific midnight, DST, a host in another timezone, sessions
crossing midnight, exact counts despite truncation, and changes during synthesis.

## Full handoff identity regression (optional repeat)

Only after the revised pilot gate authorizes installation, Nico runs the installer
from the source checkout:

```bash
cd /Users/nico/src/prompt-lab
./workflow/install.sh
```

Open a **new terminal window** afterwards. An existing terminal retains the old
`work`/`cx` functions even when the installed file on disk has changed. Start a
fresh Claude window with `work prompt-lab` and a fresh Codex window with
`cx prompt-lab`. Do not run simultaneous code edits in this shared checkout.

1. Run `/readup` in Claude and `$source-command-readup` in Codex. Each must report its
   authoritative `id|started_at`; record the two IDs. They must differ.
2. Repeat readup in each conversation. Each must retain its own original ID.
3. Give each a distinct read-only task: Claude describes the audit result states;
   Codex describes the whole-day revision check. These give the summaries two
   recognizable contributions without concurrent repository edits.
4. Run Claude's `/handoff-full`, then Codex's `$source-command-handoff-full`. Each must update and
   close only its retained session row. The second daily account must retain
   both contributions and use the exact counts supplied by `today-context`.
5. Resume the same Codex conversation in a fresh launcher window and repeat
   readup: its ID must remain unchanged. A new/forked conversation must get a
   distinct ID.

For human-run verification only, replace the two placeholders below with the IDs
from step 1. These queries are not authorized agent steps under a database denial.
The first query should show two different summaries and each row's own closure.
The second should include both contributions. The final query should retain
the replaced daily prose; it is local-only and is never synced publicly.

```bash
sqlite3 -header -column ~/.claude/prompt-history.db "SELECT id, started_at, ended_at, summary FROM sessions WHERE id IN (<claude_id>, <codex_id>);"
sqlite3 -header -column ~/.claude/prompt-history.db "SELECT date, summary, prompt_count, session_count, commit_count FROM daily_summaries WHERE project='prompt-lab' ORDER BY date DESC LIMIT 1;"
sqlite3 -header -column ~/.claude/prompt-history.db "SELECT date, summary FROM daily_summaries_superseded WHERE project='prompt-lab' ORDER BY id DESC LIMIT 2;"
```

Stop and report a missing/different session ID or lost contribution. Do not fix
the test by selecting whichever row is newest. This live check evaluates the
agent-written prose as well as the deterministic helpers; automated tests cannot
judge whether the synthesis faithfully describes both conversations.


Nightly discovery uses prompt/commit timestamps and saved session start/close
timestamps. A prompt-free conversation needs a saved session summary to contribute
recoverable findings. A successful lean handoff always saves then closes. A manual
in-place summary edit without refreshing the close timestamp is not an automatic
backfill signal; use explicit full handoff in that case.
