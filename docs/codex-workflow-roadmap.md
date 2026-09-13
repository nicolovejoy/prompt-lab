# Claude/Codex workflow roadmap — 2026-09-13

Scope: Prompt Lab's CLI/iTerm launchers, secret protection, session bookkeeping,
and installed readup/handoff commands. Nico installs locally; implementation and
fixture tests happen before that step. No live secret reads are used for testing.

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

`workflow/codex-permissions.candidate.toml` is a candidate, not installed or selected
by either launcher. It permits the workspace and runtime reads, with Homebrew
explicitly readable on this laptop, and denies matching environment/key paths.
`scripts/probe_codex_permissions.py` uses this candidate against disposable fake
files. Initial result: 72/72 checks passed, covering cat/Python reads, recursive
search, symlinks, nested files, backups, ordinary and template writes, and refusal
to create a new matching secret file.

The gate before installation is broader than that result:

- Test the profile loaded from its actual configuration location in a fresh CLI
  session, with legacy sandbox settings removed from that candidate's launch.
- Decide how session helpers reach the private database without broadly reopening
  the home directory. The candidate currently denies that access.
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

Status at close: implementation preserved in `drafts/codex-session-identity.patch`,
not applied. The child agent reports 20 passing identity scenarios and passing
shell syntax checks. Integration review remains.

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

Status at close: implementation preserved in `drafts/codex-whole-day-context.patch`,
not applied. Its isolated tests passed. Add the `today-context` dispatch to
gc-read.sh and reconcile explicit session-ID validation with Phase 2 before
applying and testing the combined change.

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

After local checks and review, Nico runs the installer. Start fresh `work` and
`cx` windows in Prompt Lab, run readup in each, and verify distinct stable session
IDs. Perform one small distinct task in each, hand off both, and verify each
summary and closure affects only its own row. The resulting daily account should
include both tasks without duplicated counts. Verify a resumed conversation
still resolves its own row.

Install/select the permission candidate separately only after Phase 1's remaining
gates pass. Repeat the fake-file probe through the final launch path. A passing
inline sandbox probe alone is not evidence that the launcher selected the profile.

Push/production deployment is separate from local workflow installation.
