# Codex workflow checkpoint — 2026-09-13

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
