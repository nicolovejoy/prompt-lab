# Dual-agent commands: Claude Code + Codex CLI

Status: approved by Nico 2026-09-12, ready for implementation planning.

## Problem

Nico now uses Codex CLI (in addition to Claude Code) in several repos —
first musicforge and songpath, prompt-lab itself not yet. He wants:

1. `/readup` and `/handoff` (and the rest of `workflow/commands/*`) usable
   from Codex, not just Claude Code.
2. This repo (prompt-lab) to be the canonical source/distribution point for
   that tooling across repos, the same way it already is for the
   shared-conventions block in CLAUDE.md.
3. The `~/src/.handoff` cross-repo channel to work correctly regardless of
   which agent is running.
4. Songpath (currently Codex-only) to actually show up on the prompt-lab
   dashboard with real activity, not as a manual registration step.

## Investigation findings (grounding for the design)

- **The dashboard has no project allowlist.** `web/api/overview.py:130-132`
  derives the project list purely from which `project` values already have
  rows in `daily_summaries`/`weekly_rollups` on Turso. Songpath is invisible
  today only because nothing populates those tables for it — not because it
  needs registering anywhere.
- **The real blocker is `workflow/hooks/log-prompt.sh`**, a Claude-Code-only
  `UserPromptSubmit` hook — the sole writer of the local `prompts`/`sessions`
  tables everything downstream depends on. Codex has no hook mechanism
  (`find ~/.codex -iname '*hook*'` returns nothing), so raw per-prompt
  capture from Codex sessions is not achievable without new capture
  infrastructure Codex doesn't expose. **Out of scope for this spec** — see
  "Explicitly out of scope" below. What *is* in scope (porting `/readup` and
  `/handoff`) gets songpath real session-level data as a side effect, which
  is the practical fix Nico actually wants.
- **Codex has two distinct extension mechanisms**, confirmed by reading
  `~/.codex/` directly and OpenAI's docs (not taken on faith from a
  third-party paste):
  - `~/.codex/skills/<name>/SKILL.md` — same open frontmatter shape as
    Claude's Agent Skills, auto-triggered by description match.
  - `~/.codex/prompts/<name>.md` — explicit slash commands, invoked as
    `/prompts:<name>`. Frontmatter supports `description` and
    `argument-hint`; args via `$1`/`$ARGUMENTS` or `KEY=value`. No
    `allowed-tools`, no model override.
  - `/readup` and `/handoff` are deliberately-invoked, session-lifecycle
    actions — they belong in the **prompts** bucket, not skills (skills
    auto-fire on description match, which is wrong for a command you want
    explicit control over).
- **The existing `workflow/commands/*.md` bodies are already mostly
  agent-neutral.** The bash they call (`gc-read.sh`, `gc-write.sh`,
  `handoff.sh`, `sync-claude-md.sh`) has zero Claude dependency — it's plain
  shell/sqlite/Turso code that already runs from any shell. `readup.md`
  already phrases its one Claude-tool-specific step conditionally ("if the
  ListAgents tool is available"). The only hard-coded Claude-only bits are
  the `allowed-tools:` frontmatter line, and a couple of call-outs by name to
  Claude-only tools/skills (the `Agent` tool in `resync.md`, the closing
  nudge in `readup.md` to invoke `superpowers:subagent-driven-development`).
- **`sync-claude-md.sh` is already target-path-agnostic.** Its marker tokens
  (`SHARED-CONVENTIONS:BEGIN/END`), hashing, and safety-diff logic don't
  reference "CLAUDE.md" anywhere except in messages and the script's name.
  Pointing it at `./AGENTS.md` works unmodified today.
- **`daily_summaries.model` already exists** and is already populated with
  `'claude-code'` by the example script in `readup.md`'s lazy-synthesis step.
  No schema change needed to attribute a summary to Codex — a Codex-invoked
  `/handoff` just writes a different value (e.g. `'codex'`) into the same
  column.
- **No collision detection exists across agent types.** `ListAgents` only
  sees Claude sessions; Codex's own `codex agents` session browser is local
  to Codex and doesn't cross over. This is a real gap, addressed by
  convention (branch naming) rather than tooling — see Decision 5.

## Design

### 1. Command porting — one source file per command

`workflow/commands/*.md` (all 8: readup, handoff, pulse, resync, review,
roadmap, ask, bulletin) stay the single source of truth. A light editing
pass removes the remaining hard-coded Claude-tool/skill names in favor of
capability-conditional phrasing (already the dominant style in these files):

- `resync.md`'s use of the `Agent` tool → "if a subagent-spawning capability
  is available, use it to keep context lean; otherwise do the research
  inline."
- `readup.md`'s closing nudge → "if a plan/subagent-driven-development
  workflow skill is available, invoke it before starting implementation."

`workflow/install.sh` installs each file to **both** targets:

- `~/.claude/commands/<name>.md` — unchanged, `allowed-tools:` kept.
- `~/.codex/prompts/<name>.md` — same body, `allowed-tools:` line
  mechanically stripped (sed/awk on install, not a hand-maintained second
  copy).

No generated or duplicated prose — a one-line frontmatter transform at
install time is the only divergence.

### 2. The SessionStart-hook gap → extract `session-context.sh`

Claude gets today's date, last-session summary, recent commits, working-tree
state, bulletin headlines, and the cross-repo handoff "Active" section
auto-injected via `workflow/hooks/session-start.sh` before `/readup` even
runs. Codex has no hook, so it gets none of this for free.

Extract the context-gathering body of `session-start.sh` (everything that
builds the `CTX` string) into a new plain script, `workflow/bin/session-context.sh`,
which prints the same information as plain text (no JSON envelope).
`session-start.sh` becomes a thin wrapper: call the script, JSON-wrap its
output for the hook protocol. `readup.md` gains a new first step, worded for
both agents: "if this context wasn't already injected at session start
(Claude usually has it via the hook; Codex never does), run
`~/.claude/bin/session-context.sh` now and read its output before
continuing." One script, two consumers.

### 3. AGENTS.md sync — rename, don't duplicate

Rename `workflow/bin/sync-claude-md.sh` → `sync-shared-md.sh` (it's already
fully generic; the name is what's misleading). Update its callers:
`readup.md` step 6, `install.sh`'s copy step, the `allowed-tools`
frontmatter line in `readup.md`. `readup.md` step 6 loops over whichever of
`CLAUDE.md` / `AGENTS.md` exist in the current repo and checks each against
the same canonical `workflow/claude-md-shared.md` source — same content hash,
same markers, so "keeping them in sync" is structural (single source
compiled to both files), not a maintained comment. Marker token
(`SHARED-CONVENTIONS:BEGIN/END`) doesn't collide with songpath's existing
`next dev`-managed `BEGIN:nextjs-agent-rules` block in its `AGENTS.md`.

Content: identical between CLAUDE.md and AGENTS.md targets, per Nico's
2026-09-12 decision — no Codex-specific trimming for now.

### 4. Songpath / attribution

No schema change. A Codex-invoked `/handoff`'s lazy-synthesis step passes
`model='codex'` (or the real model id) instead of `'claude-code'` into the
existing `daily_summaries.model` column. Running `/handoff` once from Codex
in songpath is what actually resolves "add songpath to the dashboard" — not
a separate registration step.

### 5. Collision hygiene across agent types (convention, not tooling)

No cross-agent session registry exists or is being built here. Nico's
proposed mitigation: Codex always works on a branch with `codex` in the
name (and Claude may adopt an equivalent convention) so a `git branch`/
`git status` glance — by a human or either agent's own "other agents on this
repo" check — reveals which tool touched what, even though neither tool's
session list crosses over to the other. **Exact convention (naming pattern,
whether Claude adopts one too, whether `readup.md`'s worktree-check step
should start grepping branch names for `codex-`) is left for the
implementation plan** — flagged here as a decision to make during planning,
not resolved in this spec.

## Explicitly out of scope

- Per-prompt capture from Codex sessions (no hook mechanism exists in Codex
  today; would require new capture infrastructure Codex doesn't expose).
- A cross-agent-type live session registry/detection tool.
- Porting anything into musicforge's or songpath's own repos directly —
  per the existing cross-repo invariant, prompt-lab hosts the canonical
  source and tooling; each repo's own agent pulls and applies it (already
  true of `sync-shared-md.sh --apply` today).
- Trimming the AGENTS.md shared-conventions content vs. CLAUDE.md's (Nico:
  start identical).

## Testing / acceptance

- `workflow/install.sh` run produces correct files under both
  `~/.claude/commands/` and `~/.codex/prompts/` (frontmatter differs only by
  the stripped `allowed-tools` line; diff the rest).
- `sync-shared-md.sh --check ./AGENTS.md` and `--check ./CLAUDE.md` both
  report the same hash after `--apply`.
- `session-context.sh` run standalone produces the same text
  `session-start.sh` used to embed in its JSON output (diff before/after the
  extraction, same inputs).
- Manual: run the ported `/handoff` from Codex in songpath once; confirm a
  `daily_summaries` row appears with `model='codex'` and songpath appears on
  the dashboard.
