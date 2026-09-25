# Claude/Codex workflow roadmap — 2026-09-13

Scope: Prompt Lab's CLI/iTerm launchers, secret protection, session bookkeeping,
and installed readup/handoff commands. Nico installs locally; implementation and
fixture tests happen before that step. No live secret reads are used for testing.

## Current status — 2026-09-19

**Bookkeeping acceptance is reopened; further rollout is on hold.** The permission
profile was installed globally on 2026-09-18, but MusicForge now reports that
readup failed with `unable to open database file`. No validated session ID was
returned, so handoff correctly stopped without saving a summary or closing a row.
The source consumer below is ready for review; no installed helpers, skills, or
permissions have been changed.

The installed `f5cb2cf` workflow passed the paired Songpath identity and full
handoff exercise. Results and repeatable smoke steps live in
[codex-workflow-validation.md](codex-workflow-validation.md).

The lean follow-up is implemented in source: routine handoff captures continuity
and closes its own row; `handoff-full` explicitly adds recaps;
`workflow-maintenance` owns docs and backlog work. Readup no longer backfills.
Nightly discovers prompt-free sessions and stale completed days, uses bounded
whole-day input and guarded daily saves, and refreshes stale completed weeks.
The first live Codex smoke exposed that CLI 0.154.0 rejected the deprecated
`/prompts:*` interface despite correctly installed files; plain-text attempts merely
improvised a partial readup and never registered a session. The installer now also
renders the canonical commands as explicit-only `$source-command-*` user skills,
repairing the desktop migrator's incorrect `~/.Codex/bin` and `AGENTS.md` rewrites.
The installed readup skill passed repeated identity checks as Songpath session `610`.
Its first lean handoff stopped safely when the sandbox denied the private DB write.
After installing a narrow rule for only the reviewed `gc-write.sh` helper and the
constrained temporary-summary path, the exact Codex thread resumed session `610`,
saved the audit, and closed it successfully. That test preceded the global profile
installation and had zero commits; it does not establish complete handoff support
under the currently active restrictions.

Remaining gates: full-handoff smoke, actual before/after usage measurement,
fresh-launcher fork, complete bookkeeping under the installed permission profile,
and the separate sleeping-host nightly test. No overnight or API-cost result is claimed
by the isolated local tests.

### Phase 4 step 2 — implemented for review, 2026-09-19

The source consumer is `workflow/codex/bookkeeping.py`; explicit staging through
`scripts/stage_codex_bookkeeping.py` copies it and the existing identity/project
resolvers into a separate host bundle. No installation or real-DB change occurred.
The standalone CI suite uses disposable installed copies, databases and Git repos.
The real CLI fixture now supports `--consumer`, including nonzero commits.

A new request also requires `GC_REQUEST=<uuid>:<sha256>` in the owning
conversation's host-supplied Stop final message. Matching file identity alone
cannot prevent a peer in the same writable workspace from planting a request.
The digest binds the exact authored bytes; only an already-committed matching
request can replay without new intent. One transaction stores commits, summary,
closure and receipt, with global first-hash attribution and a durable UUID ledger.
No existing commit rows are deduplicated or migrated (issue #57 remains separate).

**Review gate:** disposable tests and the CLI continuation fixture pass. Production
profile enforcement, live pilot, Desktop, fresh-launcher resume/fork and full
handoff remain untested. See validation for evidence, limitations and Nico's gated
step-3 installation instructions. Do not install or expand rollout from this PR.

### Permission failure and proposed recovery

**Lifecycle experiment completed, 2026-09-19:** the real CLI with a deterministic
local Responses stub received hook-injected identity and a Stop receipt delivered
by a one-time `decision: "block"` continuation. Notification-only Stop output did
not reach a subsequent model request. Wrong-session input was rejected without a
save or closure. See validation for evidence and limits: these runs remained in
the enclosing sandbox but could not exercise a nested production-style permission
profile. This is a working lifecycle fixture, not an installed bookkeeping fix.
Next implementation step: integrate the existing identity resolver with a bounded
hook request consumer, durable replay handling and a post-commit continuation
receipt; preserve the independent installation and production-profile gates.

Evidence available on 2026-09-19:

- MusicForge's agent reported failed registration and no validated ID. Its review
  remains at `/private/tmp/musicforge-mvp-review.GxfZFE/REVIEW.md` according to that
  report. This investigation has not independently verified that file or any DB row.
- The source profile denies `~/.claude/prompt-history.db`, `-wal`, and `-shm`.
  This Prompt Lab session's active policy also makes those denials
  non-escalatable. We did not attempt database access or a bypass to reproduce it.
- The installed `gc-write.sh` and `_gc_session_identity.py` match the repository
  byte-for-byte. Registration opens the denied database. The narrow allow rule
  documents an intended helper route, but does not prove that route is permitted
  in every runtime. MusicForge's exact invocation and effective rule handling
  remain unverified.
- `workflow/commands/handoff.md` still requires direct Python SQLite inserts for
  commit capture. This is a separate uncovered access path even if registration
  succeeds; the earlier zero-commit smoke did not exercise it.

**Root cause, verified from Claude 2026-09-19** (not under the Codex profile, so it
could read the DB and `~/.codex/sessions`):

- Both failing MusicForge Codex conversations (`01a0ba63-…`, `01a0ba8d-d918-…`,
  cwd `~/src/musicforge-codex`) ran `/Users/nico/.claude/bin/gc-write.sh
  register-session` as a plain `exec_command`, with no `sandbox_permissions`. Output:
  `Session bookkeeping failed: unable to open database file`, exit 1. No retry.
- Their session rows **exist anyway**: 691 and 693, project `musicforge-codex`,
  `claude_session_id` equal to the conversation IDs. The `UserPromptSubmit` hook
  (`log-prompt.sh` → `_gc_session_identity.py claude`) wrote them; Codex hooks run
  outside the sandbox. The row exists; the agent just cannot read its ID back.
- `~/.codex/rules/prompt-lab-session.rules` has `decision = "allow"` for the four
  `gc-write.sh` subcommands. An allow rule removes the approval prompt. It does not
  lift the sandbox, and the profile's `prompt-history.db = "deny"` applies to every
  sandboxed child process, the reviewed helper included. Session 610 passed only
  because it ran before the profile was installed.

**Escalation route dropped; proposed recovery uses hooks (2026-09-19).** Claude's
follow-up in `~/src/.handoff/prompt-lab-prompt-lab-codex.md` reports a disposable
test through Codex CLI 0.155.1. Plain registration failed on the fake DB as
expected. Escalated registration and the repeat were **not run**: that
noninteractive invocation injected `approval_policy=never`. This is not evidence
that an interactive escalation was tried and refused. The separate explicit
instruction forbidding escalation of denied paths is the reason to reject that
design, irrespective of whether an approval rule might accept the command.

The fake DB nevertheless acquired a session row through UserPromptSubmit, according
to Claude's report. Codex's own escalated `register-session --help` probe also
returned exit 0 without another approval prompt, but argument parsing exits before
SQLite access; it establishes no database capability. Neither result passes the
complete bookkeeping acceptance gate. The real database and installed permissions
were unchanged by these probes.

**Codex approval-rule probe, 2026-09-19 — historical finding:** An
`exec_command` invocation of
`/Users/nico/.claude/bin/gc-write.sh register-session --help` with
`sandbox_permissions = "require_escalated"` returned help and exit 0 without a
further approval prompt. The installed Python parser handles `--help` before
opening SQLite, so this confirms the matching escalated command can be accepted,
**not** that registration or database access succeeds. This session's explicit
non-escalatable DB denial prohibited testing real registration through that route.
No live registration, rule/profile change, or helper installation occurred.
At the time, the proposed next step was a permitted disposable-data execution test,
holding the larger interface until the gate chose between the existing helper and
hooks; an accepted help call was insufficient evidence for either. That proposed
gate is superseded by the later decision above to drop escalation and use hooks.

Preserve the database denial and conversation-ownership checks. Do not choose a
different session, copy the database, broaden Python/sqlite permissions, or treat
an approved command prefix as authority to bypass a non-escalatable deny.

Proposed implementation, after review — a host-managed hook interface, not an
agent-invoked escape from the database denial:

1. **Prove the hook lifecycle with disposable data first.** Confirm the supported
   Codex event payload, trusted native conversation ID, project resolution, context
   injection and Stop execution through the real launcher. The existing
   `session-start.sh` explicitly does not register, and `session-stop.sh` is a
   Claude token-count hook that can exit when transcript usage is absent. Neither
   is already a Codex handoff consumer. A successful prompt hook proves only that
   event's operation; do not assume the remaining lifecycle works identically.
2. **Inject identity from the host.** SessionStart, or UserPromptSubmit when the
   native identity first becomes available, registers/resolves the conversation
   through reviewed installed code and injects `Session: <id>|<started_at>` with
   project and conversation provenance. Readup retains that identity without a DB
   call. Missing or inconsistent context is an error; no newest-row or pointer
   fallback. Repeated events and resumes retain the ID; forks get distinct IDs.
3. **Submit a bounded handoff request.** The agent writes a structured file in a
   sandbox-writable location containing the summary, commit records and a unique
   request ID. The hook derives the authoritative conversation and project from
   its host event, not the file, then checks the requested session against that
   binding. File ownership alone is not proof of conversation ownership. Reject
   arbitrary SQL, commands, database paths, unknown fields, oversized inputs,
   symlinks and unsafe file replacement. Do not scan other sessions' requests.
4. **Save through protected hook code.** The Stop hook validates and applies only
   the permitted bookkeeping operations. Move commit persistence out of the
   agent's direct SQLite instructions. Preserve UTC commit timestamps and the
   first recorded attribution for an existing hash; retries never reassign it.
   Save commits, summary and routine closure atomically, with a durable request
   identifier so replay cannot duplicate work. Failure leaves the request
   recoverable and does not close an open row. The hook executable and all code it
   imports must be outside agent-writable paths; do not install a hook that imports
   privileged logic from the working checkout.
5. **Acknowledge persistence accurately.** Emit a host-origin receipt only after
   commit, bound to the request, conversation and session. Writing a request means
   **queued**, not **saved**. Establish when Codex actually receives Stop results:
   if the runtime cannot resume the turn before the final response, report queued
   at handoff and inject the receipt on the next supported event. Do not poll for
   a Stop event that cannot occur until the turn ends, or trust an agent-writable
   receipt file as proof. The lifecycle probe demonstrated that Stop can use a
   one-time `decision: "block"` reason to deliver a receipt before the final
   acknowledgement; the second Stop must recognize replay and exit. Failed hooks
   must surface an explicit failure on that
   acknowledgement path. Missing receipts leave status pending, never successful.
6. **Update commands and installation together.** Codex readup/handoff consume
   host identity and receipts; they never invoke DB readers/writers by escalation.
   Keep Claude's supported path compatible. Full handoff and DB-backed pulse/context
   reads need separate contracts and remain gated; the lean write path does not
   authorize raw-prompt access. Nico installs only after the fixture and review
   gates; this plan changes no installed hooks, rules or policy.

Validate and deploy in the stages under Phase 4. Architecture, implementation,
installation, and live acceptance are separate review points.

## Phase 1 — secret protection

Nico approved moving safe templates to a separate naming convention if the
runtime cannot reliably exclude them from secret-file denies. Prompt Lab now uses
`env.tpl` for 1Password references and `env.example` for placeholders. Actual
environment files retain `.env` / `.env.local`. Historical docs keep their old
filenames as history; current setup instructions use the new names. Other repos
are not migrated by this change.

On Codex CLI 0.154.0/macOS, an exact `.env.tpl = read` entry did not reopen a
matching deny glob. A single-character negated class worked, but the
multi-character class needed by the four-template complement denied templates.
The complex pattern approach is rejected for this runtime.

`workflow/codex-permissions.candidate.toml` is the source for the globally installed
profile described below (its candidate filename is retained). Revised 2026-09-18
after mining 444 escalation requests from
`~/.codex/sessions` (442 approved; causes: bookkeeping writes outside the repo 108,
network 133, local git writes 86, dev servers/builds 73). The first version's
`":root" = "deny"` broke git (`~/.gitconfig`), node (OpenSSL config) and gh, and it
silently disables exact-path carve-outs. Reads are now open by default, with explicit
denies for home secrets, the raw prompt database and the 1Password CLI socket. A custom
profile does not inherit `:workspace`'s `.git` protection, so the candidate reopens
`.git` for local commits and keeps `.git/hooks` and `.git/config` read-only (a planted
hook would run later outside the sandbox). Network is on; credentialed calls (`gh`,
push, private fetch) still fail in the sandbox because the gh config, `~/.ssh` and the
keychain credential are unreachable, so they remain escalations or reviewed rules.
`scripts/probe_codex_permissions.py` uses this candidate against disposable fake files
in a git repo: 91/91 on CLI 0.155.1 and the app's 0.155 alpha, covering secret-file
reads, recursive search, symlinks, writes, local commit, hook/config protection, every
denied home path, and git/node/python/public network still working. Sandboxed `op`
reports no accounts. Run it with an `rg` on PATH (this laptop has one only inside
`/Applications/ChatGPT.app/Contents/Resources`). The custom profile also drops
`:workspace`'s read-only `.codex` and `.agents`, so both are reopened read-only;
without that a sandboxed agent could rewrite its own project config (93/93 with
those checks).

Installed globally 2026-09-18 after the pilot and a real-use check passed:
`~/.codex/config.toml` sets `default_permissions = "prompt-lab"` and
`approval_policy = "on-request"` with the candidate's tables, and
`~/.codex/rules/reviewed.rules` replaced `default.rules`. A fresh session in songpath
recorded the profile. Backups are in `~/.codex/backup-2026-09-18/`. The candidate
remains the source; future installations must pass the revised Phase 4 gates.
Prefix rules cannot see trailing flags (`git push origin main --force` matches a
`git push` allow), so push stays
prompting. Known wrinkle: repos that still have `.env.tpl` (songpath) print
`Operation not permitted` from git status and the file can't be edited from the
sandbox; renaming it to `env.tpl` fixes both.

Pilot, 2026-09-18 (superseded by the install): the candidate was copied to
`prompt-lab/.codex/config.toml` and applied only to Codex sessions in this repo. A fresh
`codex exec` in the repo recorded `active_permission_profile: prompt-lab` with every
entry in its session log's `turn_context`. That record is the proof of which profile a
session ran, and it's the check to repeat after any change. The same profile name from
another directory fails to resolve.

Environment: sandboxed commands inherit the launching shell's variables, including
secret-named ones. `shell_environment_policy` (`inherit = "core"`, `exclude` globs) had
no effect on CLI 0.155.1, from `-c` or from the config file. The launching shell
currently exports no secrets. The rule that follows: never start Codex under
`op run` or with a secret exported. Wrap the single command that needs the secret
instead, where it runs as an escalation.

The installation evidence does not replace these acceptance requirements:

- Test the profile loaded from its actual configuration location in a fresh CLI
  session, with legacy sandbox settings removed from that candidate's launch.
- The separate narrow `gc-write.sh` rule passed through the installed fresh-resume
  path before the global profile installation. It has not established complete
  bookkeeping support under the current policy, which denies database access.
- Test shell startup and environment inheritance using fake values; unreadable
  files do not remove credentials already inherited by a process.
- Keep secret operations human-run until protected helpers have constrained
  inputs/outputs and code the agent cannot modify. Test approval behavior with
  fake data; approved unsandboxed commands have a separate boundary.

The official permission documentation describes profiles as governing local
sandboxed command execution, with separate controls for escalations and external
tools. It also warns against mixing profiles and legacy sandbox settings:
https://learn.chatgpt.com/docs/permissions

## Phase 2 — session identity

Status 2026-09-14: integrated in source and verified against isolated databases.
`workflow/bin/_gc_session_identity.py` owns registration and resolution for the
wrappers and Claude hooks. Native Codex thread IDs are authoritative; the local
`session_identity_bindings` table preserves launcher ownership after Claude
adopts its native UUID. Pointer files cannot establish scoped ownership.
Twenty-one scenario groups pass, including concurrent registration, resume/fork,
wrong-ID writes, legacy closed rows, quoted project names and stop-hook tokens.
The earlier draft is retained as historical input, not an installation source.

Registration must return the authoritative `id|started_at`, bind it immediately,
and be idempotent for the same conversation. A scoped caller must never silently
select another window's project pointer. Codex rows must not be eligible for the
Claude hook's adoption of unbound rows. Keep older direct Claude usage compatible.

Acceptance tests use isolated databases and concurrent conversation identities:
two Claude/Codex windows in one repo, repeated registration, thread resume/fork,
worktree project attribution, stale/wrong-project pointers, explicit closure,
and the next prompt after a mid-session handoff. No live session rows are repaired
by the implementation tests.

## Phase 3 — whole-day handoff and CI

Status 2026-09-14: integrated in source. `today-context` reads an explicit Pacific
day from local SQLite, including sessions with activity across midnight and the
validated caller. `save-daily-summary` rejects stale revisions and incorrect
counts under a write lock, then uses the store's archive-before-replace upsert.
Existing daily prose is part of synthesis input. The installed-copy roundtrip,
day-context regressions and prompt contract checks are now in CI. The earlier
draft is retained as historical input; it is superseded by these source files.

Daily prose must summarize the project's whole Pacific calendar day. Before
replacing the live daily row, fetch all available session summaries, bounded
prompt/commit context, exact counts, and explicit truncation metadata. A second
agent's handoff must not reduce the live account to its own work.

Acceptance: two sessions contribute distinct work, context includes both, counts
remain exact under truncation, UTC timestamps bucket to the correct Pacific day,
and a replaced paid summary remains archived. Exercise installed prompt output
and add the relevant structure and artifact tests to CI. Tests cannot judge the
quality of model-written prose; the live two-session smoke test must check it.

## Phase 4 — installation and live validation

The profile is already installed globally. Do not repeat or expand installation
based on the earlier paired test. Use this staged recovery sequence; the live
steps in [validation](codex-workflow-validation.md) are gated by it.

1. **Verify and review the hook contract.** Run the disposable lifecycle check
   above before building the request consumer. Record the actual identity payload,
   event ordering and receipt-delivery behavior for each target runtime. Resolve
   the file-ownership, commit-attribution and retry contracts before implementation.
   If trusted identity or acknowledgement cannot be delivered, keep bookkeeping
   unavailable and report that exact limitation. Do not reopen the escalation route.
2. **Implement and test with disposable data.** Exercise the actual installed-copy
   interface against a fake database and throwaway Git repository. Require stable
   repeated registration; distinct peer/fork IDs; wrong-ID rejection; zero and
   nonzero commit capture; duplicate-safe retries; original UTC timestamps;
   summary-save receipts; and closure of only the validated row. Inject denial and
   failed saves at each boundary, proving that required-save failures cannot close
   the row. Test malformed/oversized inputs, cross-conversation request injection,
   symlink/replacement attacks and protected helper dependencies. Repeat Stop events
   and a crash after DB commit but before acknowledgement must not duplicate writes.
   Test both missing receipts and explicit failures without false success messages.
3. **Pilot one runtime and project.** After review, Nico installs the reviewed
   version for a controlled pilot. Start through the actual fresh launcher, record
   versions, effective profile/rules and helper revision, and run the entire
   inject identity → queue request → hook validation → save commits/summary and
   close → acknowledge sequence. Include
   a nonzero-commit case in a disposable repo. Verify persisted results through the
   permitted interface or a human check, never direct DB access by a denied agent.
   Repeat the secret-denial probes using fake fixtures through that launch path.
4. **Exercise resume, fork, and the peer agent.** Resume the same conversation in
   a fresh launcher and retain its identity; fork/new conversation gets a distinct
   identity. Verify the Claude/Codex pair cannot alter each other's row. If both
   CLI and Desktop are intended targets, each needs its own evidence; a CLI pass
   does not establish Desktop acceptance. Full handoff remains a separate gate.
5. **Expand only after acceptance.** Record receipts and failures in validation,
   then install on the next intended runtime/machine. Any denied required operation
   stops expansion. Restore a known compatible reviewed installation only if one
   exists for that policy; otherwise retain protection and report bookkeeping as
   unavailable. Do not make the database readable as a rollback shortcut.

No stage is passed by a fake-file probe alone. Live database repair, recovery of
MusicForge's missing session, and push/production deployment are separate work.
