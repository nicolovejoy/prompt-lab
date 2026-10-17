# Plan: remove Codex from the workflow

Status: DONE through stage 2, 2026-10-16. Stage 1 merged (PR #88, #89) and installed; fleet CLAUDE.md re-synced and AGENTS.md deletions staged in every sibling (each repo commits its own); Codex docs deleted. Remaining: Nico deletes `~/src/stars-demo-codex` after stars-demo triages its branches. Decision (Nico, 2026-10-15): stick with Claude
Code; Codex is retired.

Done 2026-10-16:
- Decisions 1 and 2 taken by Nico: Codex Desktop is treated as uninstalled (no
  Codex.app was found; only the npm CLI), and sibling AGENTS.md files go.
- Stage 1 is PR #89 (branch `claude/remove-codex-stage1`, built in the worktree
  `~/src/.worktrees/prompt-lab-remove-codex`). `cx`/`duet` left `work.zsh` in PR #88.
- Clone salvage: every local-only branch in `musicforge-codex` (29 refs) and
  `stars-demo-codex` (4) and `prompt-lab-codex` (1) was pushed to origin unchanged;
  12 dead musicforge worktrees pruned. `band-pa-recording-codex` was the ONLY
  checkout of that repo, so it was renamed to `~/src/band-pa-recording` with its
  uncommitted docs intact. `songpath-codex` was clean. Handoff notes posted to
  musicforge, stars-demo and songpath asking each agent to triage its branches.
- Still local, for Nico to delete after PR #89 merges: the five clone dirs,
  `~/.codex`, `~/.agents`, `~/.claude/codex-bookkeeping-step{2,3}`, the `codex`
  git remote here, the npm CLI (`npm uninstall -g @openai/codex`), and the
  `*-codex` handoff channel files. Keep the `project_aliases` rows.

Basis: a grep survey only (`git grep -il codex` = 53 tracked files, plus state under
`~/.codex`, `~/.agents`, five `~/src/*-codex` clones). No file has been read for
entanglement yet; stage 1 starts with that read. Treat every "entangled" file below as
a hypothesis.

## Open decisions

1. **Codex Desktop: unused or uninstalled?** Undecided. Recommendation: uninstall.
   If the app stays installed, its Claude importer writes corrupted AGENTS.md copies
   wherever the file is absent (2026-09-18 finding). That is the only reason
   `make-agents-md.sh` and the AGENTS.md drift check exist.
   - Uninstalled: delete that machinery and every AGENTS.md.
   - Merely unused: keep `make-agents-md.sh` and the AGENTS.md check, and keep a
     pointer-form AGENTS.md in each repo. Everything else in this plan still applies.
2. **Sibling repos' AGENTS.md files.** Recommendation: delete them, conditional on
   decision 1 = uninstalled. They are pointers whose only audience is Codex.

## Invariants to preserve

- Claude's `/readup`, `/handoff`, `/handoff-full` and hooks must work after every
  stage. Run the full standalone suite (`for f in scripts/test_*.py ...`) and
  `node scripts/test_frontend_pure.mjs` before each commit.
- `workflow/bin/*` and `workflow/commands/*` run from installed copies under
  `~/.claude/`, so a merged fix is not live until copied (per the CLAUDE.md trap).
  Sweep after each stage that touches them.
- `prompts`/`sessions` rows written by Codex sessions stay in the history DB.
  `project_aliases` entries for the `*-codex` clones stay, so history still reads.
- The prompt hook runs the repo copy (memory: reference_prompt_hook_runs_repo_copy).
  Edits to `workflow/hooks/*` and `_gc_session_identity.py` are live for every
  session the moment they land on disk. Develop them in a separate clone.
- Nobody runs `install.sh` but Nico (memory: feedback_no_install_scripts).

## Stage 1: stop Codex being produced (behavior change, reversible)

Branch `claude/remove-codex-stage1`, PR, Nico squash-merges.

Read each file first and list every Codex branch before editing.

- `workflow/install.sh`: stop rendering `~/.agents/skills/source-command-*` and
  the deprecated `~/.codex/prompts/` copies.
- `workflow/commands/{readup,handoff,handoff-full}.md`: delete the "Codex:" sections
  and the host-identity paragraph. Keep the Claude path byte-identical otherwise.
- `workflow/hooks/{session-start,log-prompt}.sh`,
  `workflow/bin/{_gc_session_identity.py,_gc_day_context.py,handoff.sh,session-context.sh}`:
  remove Codex identity/sandbox branches. Exit code 6 in `handoff.sh` ("repo
  unwritable under a Codex sandbox") goes away; update the CLAUDE.md exit-code list.
- `workflow/bin/readup-checks.sh`: drop `CODEX_BRANCHES`; drop `CONVENTIONS_AGENTS`
  and `AGENTS_ORIGIN` if decision 1 = uninstalled.
- `workflow/shell/work.zsh`: remove Codex launch helpers. NB: functions load once at
  shell start; open tabs keep the stale copy until closed.
- `workflow/claude-md-shared.md`: remove the Codex rules (`codex/` branch prefix,
  command-form rule, one-clone-per-repo, `$source-command-*` names). This is the
  block every sibling repo carries, so it is what stage 3 propagates.
- `.github/workflows/test.yml` and the ~10 Codex-referencing test files: drop
  Codex-only tests and Codex assertions; keep coverage of the Claude path.
  `test_install_codex_prompts.py`, `test_make_agents_md.py` (if decision 1 =
  uninstalled) are deleted outright.
- `README.md`, `docs/README.md`, `CLAUDE.md`, `BULLETIN.md`: remove Codex mentions
  from the live sections only; do not rewrite history sections.

Gate: suite green; temporary-installation roundtrip passes
(`scripts/test_workflow_roundtrip.py`); Nico reinstalls and runs `/readup` and
`/handoff` in a fresh Claude session.

## Stage 2: delete dead code and archive docs

Straight to main is fine for docs, PR for code.

Delete: `workflow/codex/`, `workflow/codex-rules/`, `workflow/codex-session.rules.tpl`,
`workflow/codex-permissions.candidate.toml`, `scripts/probe_codex_hooks.py`,
`scripts/probe_codex_permissions.py`, `scripts/stage_codex_bookkeeping.py`,
`drafts/codex-*.patch`.

Archive (move to `archive/codex/`, not delete — they explain decisions):
`docs/codex-*.md` (4 files), `docs/superpowers/{plans,specs}` Codex-related files,
`docs/handoff-repo-plan.md` Codex sections stay in place. Leave `docs/history.md`
untouched except for one closing entry: "Codex retired 2026-10-15".

If decision 1 = uninstalled: also delete `workflow/bin/make-agents-md.sh`,
`scripts/test_make_agents_md.py`, `~/.claude/bin/make-agents-md.sh` (+ its `.bak`),
and `~/.claude/agents-md-backups/`. Remove `AGENTS.md` here.

Gate: `git grep -il codex` returns only `archive/`, `docs/history.md`, and
`docs/remove-codex-plan.md`. Suite green.

## Stage 3: fleet

- `~/.claude/bin/sync-shared-md.sh` inventory, then `--apply` per repo (never commits
  sibling repos; Nico commits). Every repo reads `behind` until applied, and the
  localize-kit rollout is also pending, so this is one pass for both.
- AGENTS.md in siblings: delete if decision 2 = delete. Each sibling's agent owns its
  own files (invariant: cross-repo work goes through `~/src/.handoff`, never a PR from
  here), so this is a handoff note, not a sweep.
- One note via `~/.claude/bin/handoff.sh append` to each active pairing file:
  "Codex retired; remove AGENTS.md and the codex rules block; the shared block sync
  does the latter." Entries mentioning Codex in `~/src/.handoff` stay as history.
- `stars-demo` and `musicforge` handoff files have the most Codex-specific entries.

## Stage 4: local state (irreversible, last)

Per clone (`prompt-lab-codex`, `musicforge-codex`, `songpath-codex`,
`band-pa-recording-codex`, `stars-demo-codex`):

1. `git status --short` and `git log origin/main..HEAD` and `git stash list`.
2. Anything unpushed or uncommitted: stop and ask Nico per clone.
3. Remove the `codex` remote from the main checkout.
4. Remove the clone.

Then: `~/.codex` (config, rules, hooks.json, backups — Nico to confirm; backups under
`~/.codex/backup-*` are the rollback for stage 1 and nothing else), `~/.agents`
(skills + `synced`), and `~/.claude/codex-bookkeeping-step3`. Drop the stale
"Codex host bookkeeping" items from `docs/current-work.md`. If decision 1 =
uninstalled: uninstall Codex Desktop.

## Risks

- **Hook edits are live immediately** (see invariants). A bad `log-prompt.sh` edit
  silently stops prompt logging for every session. Test in a separate clone and
  check the prompts table grew after merge.
- **Stale installed copies.** Stage 1 is not done until the install sweep shows no
  diff between repo and `~/.claude/{bin,commands}`.
- **Deleting a Codex branch in a shared helper that Claude also hits.** Hence
  "read each file first, then edit"; the roundtrip test is the net.
- **Identity resolver.** `_gc_session_identity.py` serves Claude too (conversation id
  scoping). Remove only the Codex arms; `test_session_identity.py` must keep its
  Claude cases.
- **Fleet drift if stage 3 lags.** Siblings keep telling their agents to use
  `codex/` branches until the block syncs. Harmless, just noise.

## Out of scope

- Reviving or replacing Codex with another agent.
- Rewriting `docs/history.md`.
- Touching the `public_*` tables, `project_aliases`, or any Turso schema.

## Review asks

1. Is there an entanglement the grep survey missed (Codex logic in a shared helper
   that Claude depends on)?
2. Is the stage order right, especially stage 1 before deletion?
3. Anything in "archive" that should be deleted, or in "delete" that should be
   archived?
