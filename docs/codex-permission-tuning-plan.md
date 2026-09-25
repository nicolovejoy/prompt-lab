# Codex permission tuning — plan (2026-09-23)

Status: **applied 2026-09-25** (laptop), except step 1, which Nico applies by hand.

- Writable root over `~/src/.handoff` (added to the plan on 2026-09-25): in the
  candidate and installed. The sandbox protects `.git` under any writable root, so
  the grant is five lines: the repo and its `.git` as `write`, `.git/hooks`,
  `.git/config` and `.git/commondir` as `read`. `commondir` matters: with `.git`
  writable, a copied gitdir with a planted hook plus a one-line `.git/commondir`
  pointing at it bypasses both other carve-outs on the next unsandboxed git run
  (review finding, 2026-09-25; git 2.54 honours it in a plain repo). The workspace
  block had the same hole and got the same line. `scripts/probe_codex_permissions.py`
  now points the handoff grant at a disposable repo under `~/.cache` and checks
  lock, commit and protection: 95/97 before the grant, 99/99 after (needs
  Python ≥ 3.11 for `tomllib`; the repo `.venv` is older, use `python3`). Not yet verified: whether the
  sandboxed push reaches the keychain credential. Exit 4 from a Codex
  `handoff.sh append` means it does not; the entry stays local and the next
  `handoff.sh sync` from a Claude session pushes it.
- Step 2 done: `default.rules` pruned to `uv venv` and `op vault list`; backup in
  `~/.codex/backup-2026-09-25/`. Those two are staged in
  `workflow/codex-rules/reviewed.rules` with examples, **not yet installed** (Nico
  reviews first, then `cp` to `~/.codex/rules/reviewed.rules`). `git add`,
  `git merge` and `npm run build` were not promoted: they run sandboxed inside the
  clone and only escalated from worktrees outside it or `> /private/tmp/…`
  redirects, both now forbidden by the conventions block. `git push` prompts again
  (verified with `codex execpolicy check`).
- Step 3 decided (Nico, 2026-09-25): `npm ci` / `npm install` and
  `firebase emulators:*` keep prompting; `npx playwright test` is allowed per repo,
  in that repo's own `.codex/rules/`, never in the user layer. musicforge got the
  rule text. *Unverified:* that Codex loads `<repo>/.codex/rules/` for a trusted
  project is from the Codex docs (learn.chatgpt.com/docs/agent-configuration/rules),
  not tested here. If musicforge's rule never matches, that assumption is the first
  suspect; `codex execpolicy check` only evaluates files passed with `--rules`.
- Step 4 done: shared block v=`28022362f01b` carries the Codex command-hygiene
  bullet and the PR-review rule from #70. Other repos pick it up at their next
  readup (`CONVENTIONS … behind`).
- Step 5 done: posted to `musicforge-prompt-lab.md`.
- Step 1 pending: Nico adds the nvm node 22 bin to `~/.zprofile`, then verifies
  `command -v node npm npx` from a Codex session. musicforge's CI pins node 22, and
  Codex was already prefixing `v22.16.0` by hand.

Acceptance is re-measured after one week of use (see the end of this file).

## Problem

Codex still prompts for permission far too often, five days after the reviewed
profile and rules went in (2026-09-18, see `current-work.md` item 3).

## Evidence (laptop, `~/.codex/sessions`, files modified since 2026-09-18)

- **118 escalation requests** (`sandbox_permissions: "require_escalated"`). Almost
  all are musicforge: `musicforge-codex` 30, plus eight scratch worktrees/clones.
  This counts *requests*, not prompts. A request that matches an allow rule never
  reaches Nico.
- **The prompts that did reach Nico are in `~/.codex/rules/default.rules`.** Every
  "don't ask again" click is appended there, and it has 36 rules after five days.
- Method, for re-measuring after the fix: Codex now runs commands through the
  `custom_tool_call` named `exec`. Its `input` is JavaScript that calls
  `tools.exec_command({cmd:"…", workdir:"…", sandbox_permissions:"require_escalated", justification:"…"})`.
  Count those calls per command prefix. The older `function_call` /
  `exec_command` path accounts for only 6 of the 118.

Top escalated prefixes: node/npm/npx/vercel run with a `PATH=` prefix (~30),
`handoff.sh` (8), `gc-write.sh` (6), `git -C … worktree` (6), `kill <pid>` (5),
`gh pr view … > /private/tmp/…` (5), `rmdir .git/rebase-merge` (5).

## Root causes

1. **Wrapped commands can't match any rule.** Prefix rules match a command's leading
   tokens only. Codex's shell can't find node, so it writes
   `PATH=/Users/nico/.nvm/versions/node/v22.16.0/bin:$PATH npm …`, often inside
   `/bin/zsh -lc "…"` and with a `> /private/tmp/…` redirect or `$(cat …)`. Every
   variant is a new literal string, so it prompts again, and the resulting
   "don't ask again" rule matches only that exact string. Proof: `handoff.sh append`
   is already allowed in `reviewed.rules`, yet `default.rules:33` holds a
   `zsh -lc "handoff.sh append … $(cat …)"` approval.
2. **musicforge's Codex works outside its clone.** It creates worktrees and scratch
   clones (`~/src/musicforge-review`, `/private/tmp/musicforge-b3-b6`,
   `musicforge-rethink-2b-screens`, …). Anything outside `~/src/musicforge-codex`
   is outside the sandbox, so git, npm and rmdir there all escalate. This violates
   BULLETIN 2026-09-19 (one long-lived clone, no worktrees).
3. **`default.rules` has decayed.** Most entries are dead one-offs: `kill <pid>`,
   specific `/private/tmp/*.py` scripts, one exact cherry-pick. Three are broad and
   risky:
   - `git push` allows `--force` to main, contradicting DECISION 1 in `reviewed.rules`.
   - `npm ci` runs package install scripts unsandboxed.
   - `git clone` feeds cause 2.

## Plan

1. **Node on Codex's PATH.** Add the nvm default node's bin directory to
   `~/.zprofile`. Codex runs `zsh -lc`, a login shell, so it reads `.zprofile` but not
   `.zshrc`, which is where nvm loads. Verify from inside a Codex session that
   `command -v node npm npx` resolve without a prefix. *Unverified assumption:*
   Codex's exec environment inherits the login-shell PATH. If it doesn't, fall back
   to `[shell_environment_policy]` in `~/.codex/config.toml`.
2. **Prune `default.rules`.** Back it up to `~/.codex/backup-2026-09-23/` first.
   - Delete: every `kill <pid>`, every rule naming a `/private/tmp/…` path or a
     specific worktree, the exact cherry-pick, `git push`, and `git clone`.
   - Keep: `git add`, `git merge`, `uv venv`, `npm run build`, and
     `op vault list --format=json` (it lists vault names, not secrets).
   - `npm ci`: move the decision to step 3.
   - Anything worth keeping long-term moves into `workflow/codex-rules/reviewed.rules`
     with `match`/`not_match` examples, so it's reviewed and committed rather than
     accreted.
3. **OPEN: which commands may run outside the sandbox.** To discuss before any rule
   is written. Candidates:
   - `npx playwright test`: Chromium's MachPort startup is denied inside the
     sandbox, so it can't run there at all.
   - `npm run test:emulator` / `firebase emulators:*`: downloads and starts the
     Firestore emulator and writes its CLI cache outside the repo.
   - `npm ci` / `npm install`: needs the network plus the npm cache. Unsandboxed, the
     install scripts run with full access. `--ignore-scripts` narrows the risk, but
     rules can't see flags past the prefix.

   The trade-off: an allow here runs repo-controlled code (test files, package
   scripts) outside the sandbox without asking, which is the exact thing the sandbox
   exists to stop. Options: allow per-repo, allow globally, keep prompting, or run
   these gates only from Claude or by hand.
4. **Teach Codex to write matchable commands.** Add to the shared conventions block
   (`workflow/claude-md-shared.md`, then sync, so every AGENTS.md carries it):
   - Call helpers and tools directly as the first token.
   - No `/bin/zsh -lc` wrapper, no `$(…)`, no `PATH=` prefix.
   - Redirect only to files inside the workspace, and put temp files inside the
     workspace (a gitignored `tmp/`), never `/private/tmp`.
5. **Tell musicforge.** Post one entry in `musicforge-prompt-lab.md`: work only in
   `~/src/musicforge-codex`, no worktrees and no scratch clones, and why (every
   command there escalates). Link BULLETIN 2026-09-19.

## Acceptance

- After one week of normal use, `default.rules` has gained ≤ 3 rules, and none of
  them is a one-off literal.
- Re-running the tally shows no `PATH=` or `zsh -lc` wrapped escalations, and no
  musicforge workdir outside `musicforge-codex`.
- `git push` prompts again.
