# Readup and handoff validation

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

Nico installs the updated commands, then opens fresh terminal/agent windows:

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

Ask the verifying agent to read only the two recorded session rows, the Songpath
Pacific-day daily summary and its superseded rows. A missing/wrong identity,
missing contribution, unintended doc edit, or routine recap write is a failure.
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

Nico runs the installer from the source checkout:

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

For verification, replace the two placeholders below with the IDs from step 1.
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
