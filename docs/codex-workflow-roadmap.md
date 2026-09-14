# Claude/Codex workflow roadmap — 2026-09-13

Scope: Prompt Lab's CLI/iTerm launchers, secret protection, session bookkeeping,
and installed readup/handoff commands. Nico installs locally; implementation and
fixture tests happen before that step. No live secret reads are used for testing.

## Current status — 2026-09-14

The installed `f5cb2cf` workflow passed the paired Songpath identity and full
handoff exercise. Results and repeatable smoke steps live in
[codex-workflow-validation.md](codex-workflow-validation.md).

The lean follow-up is implemented in source: routine handoff captures continuity
and closes its own row; `handoff-full` explicitly adds recaps;
`workflow-maintenance` owns docs and backlog work. Readup no longer backfills.
Nightly discovers prompt-free sessions and stale completed days, uses bounded
whole-day input and guarded daily saves, and refreshes stale completed weeks.
Nico must reinstall and smoke-test this follow-up. No permission profile is installed.

Remaining gates: lean installed-command smoke, actual before/after usage
measurement, fresh-launcher resume/fork, permission-profile acceptance, and the
separate sleeping-host nightly test. No overnight or API-cost result is claimed
by the isolated local tests.

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

The earlier paired installation test passed. Follow
`docs/codex-workflow-validation.md` for the lean follow-up installation and smoke
steps. Keep implementation, installation and live validation separate.

Install/select the permission candidate separately only after Phase 1's remaining
gates pass. Repeat the fake-file probe through the final launch path. A passing
inline sandbox probe alone is not evidence that the launcher selected the profile.

Push/production deployment is separate from local workflow installation.
