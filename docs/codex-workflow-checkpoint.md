# Codex workflow checkpoint — 2026-09-13

## Readup and session bookkeeping — source integrated 2026-09-14

The launcher failure remains closed. This pass fixed readup's false drift alarm
on audit crashes, distinguished incomplete audits, and made failed fetch/auth
checks visible. Confirmed public drift now uses exit 10; both readup and the
non-fatal post-sync consumer classify it separately from generic failures.

The session identity and whole-day drafts below are superseded by integrated
source: shared SQLite ownership for wrappers/hooks, guarded daily saves, and a
passing temporary-installation roundtrip. `AGENTS.md` now points at CLAUDE.md
and carries the shared conventions. Installer and real paired-conversation
acceptance remain Nico's next step; no permission profile was installed or
selected. See `docs/codex-workflow-validation.md` and the updated roadmap.


## iTerm `-10000` blocker — diagnosed and closed, 2026-09-14

Root cause: a stale shell function, not a defect in `work.zsh`. Commit `eab5b13`
(2026-09-13 10:11am Pacific) had already removed the AppleScript line that crashes
on iTerm 3.6.11 (`set title of current tab to windowTitle` — the same
incompatibility fixed earlier in this document for `cx songpath`) and replaced it
with an OSC-title-via-shell-precmd approach. `~/.claude/shell/work.zsh` on disk
matched the repo byte-for-byte. But `.zshrc` sources `work.zsh` only once, at
shell startup — any iTerm tab opened *before* the fix+reinstall keeps the old,
crashing function definition in memory regardless of what's on disk. The
`musicforge-505-drive-oauth` failure almost certainly came from exactly that: a
tab that predated the fix.

Verification performed:
- Isolated each AppleScript operation (window create, session split
  horizontal/vertical, `write text` on all three panes, select) with `try`/`on
  error` blocks directly via `osascript` — every stage succeeded cleanly with
  realistic command strings.
- Ran the real, unmodified `cx` function (sourced fresh in a new non-interactive
  shell) against `musicforge-codex` (the closest existing project —
  `musicforge-505-drive-oauth` no longer exists, evidently a cleaned-up worktree).
  Window + all 3 panes created successfully, no AppleEvent error.
- Confirmed `workflow/commands/handoff.md`'s dead code path (the removed
  `windowTitle` AppleScript variable is now unused inside the `tell` block, just
  vestigial argv, harmless) is not itself a hazard.

No code change was needed. Fix for next time: **open a new terminal tab/window
after any `work.zsh` install**, not just confirm the file diff — see the new
CLAUDE.md trap. Remaining scope from this checkpoint (permission-profile
rollout, session identity, readup/handoff end-to-end) is unchanged, see below.

## Latest session — 577

**Closing request:** reduce excessive Codex permission prompts, ideally through
`cx`. Audit the source of each prompt before choosing defaults: ordinary network
access, protected Git metadata, and the private DB outside the workspace are
different boundaries. Make cx select a tested named profile; retain on-request
approval for actual boundary crossings. Do not mix legacy sandbox flags with the
candidate permission profile or enable unrestricted bypass. User wants fewer
routine prompts without abandoning the secret-protection roadmap.

**Final blocker:** after opting to run installation himself, Nico tried
`cx musicforge-505-drive-oauth` and received
`518:557: execution error: iTerm got an error: AppleEvent handler failed. (-10000)`.
Installed work.zsh is byte-identical to the repo. The active shell's function
definition was not inspected, and no root cause or fix was established before
Nico invoked handoff. Start with identifying the failing AppleScript statement
and verifying whether the existing terminal needs to source the updated launcher.
Do not treat the earlier successful `cx songpath` as acceptance for this failure.
The assistant's full installer invocation was aborted when Nico said "i do that";
do not rerun installation on his behalf.

Nico asked to continue the roadmap using GPT-5.5/5.6 child agents, then asked to
close soon. The phased plan and remaining gates are in
`docs/codex-workflow-roadmap.md`.

Nico explicitly chose a new naming convention if safe template exceptions could
not be made reliable. Fresh fake-only probes confirmed the issue: a single
negated character works, but a multi-character negated class blocks templates;
exact template allows still do not reopen a matching deny glob. Renamed this
repo's `.env.tpl` / `.env.example` to `env.tpl` / `env.example` and updated current
setup references. No other repositories were changed.

The new `workflow/codex-permissions.candidate.toml` passed 72/72 fake-file checks
via `scripts/probe_codex_permissions.py`, using CLI 0.154.0 on macOS. It remains
uninstalled and unselected. It requires Homebrew runtime reads, and its minimal
read boundary currently blocks the private DB helpers. Installed launch-path,
environment inheritance and escalation behavior still need testing. A GPT-5.5
review independently agreed it is not ready as the default profile.

Two GPT-5.6 reviews confirmed session identity and whole-day handoff bugs, with
isolated implementation patches preserved in the repo, NOT applied:

- `drafts/codex-session-identity.patch`: scoped/idempotent registration,
  CODEX_THREAD_ID priority, fail-closed scoped lookups, Claude adoption isolation,
  launcher scope, 20 passing identity scenarios and passing shell syntax checks.
- `drafts/codex-whole-day-context.patch`: whole-day helper, bounded context with
  exact counts and truncation metadata, readup/handoff contracts, CI additions.
  New day-context test, lint, and existing structure/artifact tests passed in the
  isolated copy.

Before applying, review both patches and reconcile their interface:
the command docs require `current-session <session_id>` validation; the identity
patch must be checked/extended to implement that contract. Integrate
`today-context` into `gc-read.sh` (invoke sibling `_gc_day_context.py` with the
resolved project using the project venv), and add it to the usage string.
Then run combined tests in the actual checkout. Neither patch has had that
combined integration review. Temporary trees also remain at
`/private/tmp/prompt-lab-identity.t7F6Q3` and
`/private/tmp/prompt-lab-day-context.uDKeFH`, but the tracked draft paths above are
the durable copies once committed.

The earlier statement below about CI
omitting the identity and prompt-installation tests was stale: both already run
in CI. The whole-day context and dual-agent regression cases still need coverage.

Session 577 was registered by this readup. Do not close Claude row 573 or trust
the old shared project pointer. Nothing has been installed or pushed in this
session.

## Earlier checkpoint (retained investigation)

Nico wants this work scoped to Prompt Lab. Customer-facing project workflows
belong in their own repos. The aim here is convenient Claude/Codex launchers,
reliable session bookkeeping, and tested secret protection. Nico explicitly wants
to stay in CLI/iTerm, not the Codex desktop app. `cx` must remain a CLI launcher.
The MusicForge suggestion of workspace-write + on-request + network_access=true
is useful for reducing network prompts, but does not itself deny secret reads;
do not combine its legacy --sandbox flag with a new permission profile and
assume both apply.

## Launcher

`workflow/shell/work.zsh` now exposes `work` (Claude) and `cx` (Codex), sharing
the menu, completion, project color, badge and three-pane layout. Titles are
`Prompt-lab -- Claude` and `Prompt-lab -- Codex`. Commands travel as AppleScript
argv with zsh-quoted arguments.

Follow-up: the AppleScript tab-title setter crashed on iTerm 3.6.11 before
launching the agent. Removed it; Nico confirmed `cx songpath` works. Added a
standard OSC title at launch and a per-pane `precmd` that restores it at shell
prompts. Agent-driven title updates may still replace the top pane's title;
there is no permanent title override and no new dependency.

Verified: zsh/bash syntax, generated commands, actual OSC bytes, live launcher
success confirmed by Nico, and isolated execution of the real Codex prompt
installation block. Nico installs via `workflow/install.sh` himself.

Nico authorized reviewing and committing the previous Claude session's installer
edit. Corrected its nested SKILL.md destination back to supported top-level
custom-prompt files, and added a behavior test that checks actual output paths
and contents in a temporary directory without invoking the full installer.

## Secret handling: agreed requirements and proposed rollout

- Permit code edits and ordinary tests without repeated prompts.
- Protect real `.env` variants, backups, keys and credential files.
- Keep `.env.tpl`, `.env.example`, `.env.template`, `.env.sample` usable.
- Never test on real secrets; use disposable fake fixtures.
- When asked for a new 1Password item, create its secret field containing
  `replace-this-value`. Nico supplies the real value in 1Password.
- A template is safe only when it contains references/placeholders. `op run`
  gives real values to the subprocess: arbitrary agent-controlled commands or
  editable scripts can still expose them. Masking isn't a security boundary.
- Recommended first helper: read-only nightly/cloud/deployment status returning
  dates, counts and health only. Later: deploy an exact reviewed commit, without
  running code from an agent-editable working tree. Helpers need protected code,
  constrained inputs and outputs, and narrowly scoped credentials. None built.
- Human-run secret operations in the bottom pane are the initial recommendation.
  Nico asked for education/recommendations, not a general grant to fetch secrets.

## Actual sandbox probes (Codex CLI 0.154.0, macOS)

No permission configuration was installed. No real `.env` contents were read.
Fake-only probes used the real `codex sandbox -P cx -C <temporary-directory>`
command. It needs to run outside the enclosing agent sandbox: nested Seatbelt
fails. CLI `sandbox` accepts the command directly; `sandbox macos` is wrong for
this installed version. Pass a complete inline TOML `permissions` table with
`-c`; the first attempt with individually quoted flattened keys did not load it.

Results:

- With workspace write and `**/.env`, `**/.env.*` denied: ordinary.txt readable;
  .env and .env.local denied as intended.
- Adding exact relative `.env.tpl = read` / `.env.example = read` entries did
  NOT reopen those templates in the tested configuration. Both remained denied.
- An exploratory complement-pattern generator was also unsuitable: isolating
  `**/.env.[!eEsStT]*` alone still blocked a fake `.env.tpl` on this runtime.
  Do not ship those patterns or claim generic glob exclusions work.
- More work remains: verify supported matching/precedence and safe template
  handling, then test direct reads, Python reads, recursive search, symlinks,
  nested files, backups and ordinary writes. Test the final installed profile
  path too, not only CLI overrides.

Disposable probes remain at `/private/tmp/cx-profile-probe.py`,
`/private/tmp/cx-pattern-isolate.py`, `/private/tmp/cx-pattern-probe.py`, and
`/private/tmp/cx-probe.config.toml`. These are investigation aids, not a deliverable;
this document preserves their findings if temp files disappear.

Do not enable automatic sandbox escapes until their interaction with denies is
understood. A command denied in the sandbox is not proof it stays denied after
unsandboxed approval. Old `sandbox_mode`/`--sandbox` settings can override new
permission profiles. Environment inheritance and shell startup files also need
checking; an unreadable file doesn't remove credentials already in environment
variables. The existing Claude global config contains Read deny rules; the
repository block-secrets hook exists but was not in the global hook list read
this session. Do not claim that hook is active without checking other layers.

## Session identity and test coverage

Readup inserted row 574, but `gc-read.sh current-session` returned row 573
(Claude-bound). `gc-write.sh register-session` inserts an unbound row without
returning/binding its id; `gc-read.sh` prefers the per-project pointer last
written by the Claude prompt hook. Worktrees do not isolate this pointer. That
hook can also adopt recent unbound rows. Handoff must use the known row 574,
not summarize or close 573. Fix identity before claiming dual-agent handoff works.

Daily summaries also replace the current per-project/day row (archiving the
previous prose). Two independent handoffs need synthesis of the whole day,
not two isolated session accounts overwriting one another.

CI explicitly lists older test scripts and omits the new workflow tests.
Wire meaningful behavior checks into CI when repairing this workflow.
Local main was 16 commits ahead of origin/main at readup; no push/deploy here.

## Sources checked

- https://learn.chatgpt.com/docs/permissions
- https://learn.chatgpt.com/docs/sandboxing/auto-review
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/custom-prompts
- https://learn.chatgpt.com/docs/build-skills
- https://developer.1password.com/docs/cli/secrets-scripts
- https://iterm2.com/3.5/documentation-variables.html

Docs describe beta permission profiles; verified local behavior above takes
precedence over optimistic assumptions about matching rules.
