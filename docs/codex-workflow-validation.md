# Readup and handoff validation

The source changes are exercised against temporary databases and temporary
installed helper copies. They do not install a permission profile, change
launchd, or repair existing session rows. The remaining acceptance check is a
real Claude/Codex conversation pair after Nico installs the updated workflow.

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

## Installation and real conversation check

Nico runs the installer from the source checkout:

```bash
cd /Users/nico/src/prompt-lab
./workflow/install.sh
```

Open a **new terminal window** afterwards. An existing terminal retains the old
`work`/`cx` functions even when the installed file on disk has changed. Start a
fresh Claude window with `work prompt-lab` and a fresh Codex window with
`cx prompt-lab`. Do not run simultaneous code edits in this shared checkout.

1. Run `/readup` in Claude and `/prompts:readup` in Codex. Each must report its
   authoritative `id|started_at`; record the two IDs. They must differ.
2. Repeat readup in each conversation. Each must retain its own original ID.
3. Give each a distinct read-only task: Claude describes the audit result states;
   Codex describes the whole-day revision check. These give the summaries two
   recognizable contributions without concurrent repository edits.
4. Run Claude's `/handoff`, then Codex's `/prompts:handoff`. Each must update and
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
