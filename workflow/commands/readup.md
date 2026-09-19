---
name: readup
description: Start a session — register a session row, sync to remote, read project context
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/sync-shared-md.sh:*), Bash(~/.claude/bin/session-context.sh:*), Bash(~/.claude/bin/readup-checks.sh:*), Bash(~/.claude/bin/handoff.sh:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Bash(mkdir:*), Bash(touch:*), Bash(gh issue list:*), Bash(gh pr list:*), Bash(gh run list:*), Bash(gh run view:*), Bash(.venv/bin/python scripts/check_public_allowlist.py:*), Bash(python3 scripts/check_public_allowlist.py:*), Read, Write, Edit, Glob, Agent, ListAgents
---

Start a session. Be concise.

If SessionStart already injected the date, last summary, commits, working-tree state, and bulletin headlines, do not re-fetch them. Otherwise (including Codex without an equivalent hook), run:

```bash
~/.claude/bin/session-context.sh
```

Read its output, then continue: registration, remote checks and the full CLAUDE.md read are still required.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session`. Retain the returned
   `<session_id>|<started_at>` in this conversation and use that exact ID for
   `/handoff`. Empty output or a failed registration is an error: report it,
   never guess another window's session. Repeating registration in the same
   scoped conversation returns the same row.
2. Run the bundled read-only checks (fetch, branch tracking, worktrees, codex branches, resync marker, CLAUDE.md/AGENTS.md conventions drift, handoff flush, CI, public drift) in ONE call: `~/.claude/bin/readup-checks.sh`. It never pulls or modifies the tree. Interpret its output with the table under "Interpreting readup-checks" below.
3. Read CLAUDE.md in full (focus on Next Steps + project conventions). The hook's injected context covers recent activity, but not project intent.
4. Other agents on this repo: if the `ListAgents` tool is available, call it and flag any other local or cloud session whose name/task suggests this repo (a cloud agent's work won't show in `git status` at all until it pushes). `ListAgents` missing or erroring → skip silently, never block session start.

Nightly synthesis owns summary backfill. Do not synthesize days during readup.
Use the recent session summaries in startup context for continuity.

## 5. Interpreting readup-checks

One line of behaviour per key. Anything not listed here → say nothing.

- `PROJECT`: informational; silent, except `PROJECT_RESOLVER=fallback-basename` → one line: `_gc_project.sh` not installed alongside.
- `REMOTE` / `TRACKING` / `REMOTE_ONLY`: `REMOTE=error` → fetch failed; report that remote status could not be checked, never interpret stale tracking data as current. Otherwise, any branch ahead/behind, or an unfamiliar remote-only branch → flag it in the summary so the user can decide whether to `git pull --rebase` / `git checkout` manually. Clean → silent.
- `WORKTREES:` block (more than the main checkout) → another agent may be mid-task; flag it with its branch. `CODEX_BRANCHES:` block → Codex has touched or is touching this repo (it always works on `codex/<desc>`); flag it. Combine with `ListAgents` from the Do list, item 4.
- `RESYNC=… due=yes` → invoke `/resync --light` inline and fold its findings into the summary (no separate wall of text). `due=no` → silent.
- `CONVENTIONS_CLAUDE`: `behind` → calm rollout note offering the exact fix `~/.claude/bin/sync-shared-md.sh --apply ./CLAUDE.md` (review the `git diff`, then commit). `missing` → offer the same command. `tampered` → strong warning: the block no longer matches its own recorded hash; review the local edits manually because `--apply` will refuse to overwrite them. `in sync` / `absent` / `skip` → silent. `unknown` → one line: sync-shared-md.sh printed nothing.
- `CONVENTIONS_AGENTS`: `behind` or `missing` → same calm fix, targeting `./AGENTS.md`. `tampered` → the same strong manual-review warning; do not suggest that `--apply` will repair it (unless `AGENTS_ORIGIN` below applies). `absent` → **do not treat as fine**: Codex reads `AGENTS.md` automatically, and an absent file is where Codex Desktop's Claude importer writes a corrupted copy. Claude Code only: run `~/.claude/bin/make-agents-md.sh` (writes the pointer form with its provenance comment; exits 2 without writing if there is no CLAUDE.md, which is fine), then one line: created `AGENTS.md`, untracked, commit when ready. Codex: offer the same command instead of running it. `in sync` / `skip` → silent. `unknown` → one line: sync-shared-md.sh printed nothing.
- `AGENTS_ORIGIN=codex-import untracked` → the file is a Codex Desktop import copy (find-replaced CLAUDE.md, broken `~/.Codex/` paths). Claude Code only: run `~/.claude/bin/make-agents-md.sh --replace-importer-copy` (it backs the copy up to `~/.claude/agents-md-backups/` first), then one line naming the backup. `codex-import tracked` → strong warning only: it is committed, so replacing it is a reviewed commit, not a readup side effect.
  Apart from those two AGENTS.md cases, never apply a fix automatically. Nothing readup writes is ever committed: materializing into a checked-in file is the user's call.
- `HANDOFF_SYNC=conflict` or `offline` → one line; the entry stays safe locally (conflict: resolve in `~/src/.handoff`; offline: re-run `handoff.sh sync` later). `ok` / `absent` → silent. `error` → one line: handoff sync failed for an unexpected reason; check `handoff.sh sync` by hand.
- `CI_PROBE=skip` → silent. `CI_PROBE=error` → say ONE line: "couldn't read CI status (`<first indented line>`)". Never report an error as "no CI configured" — you don't know. `CI_PROBE=ok` with `[]` and no `CI_PROBE_NOTE` → no CI, silent. `CI_PROBE_NOTE=workflow-files-exist-but-no-runs` → flag one line (Actions disabled, or every trigger filtered out). Latest run in `CI_MAIN:` (and `CI_BRANCH:` if present) with `conclusion: "success"` or still `in_progress`/`queued` → silent. `failure` / `cancelled` / `timed_out` → ⚠️ line in the summary naming workflow, branch, and how long it's been red (walk `createdAt`/`conclusion` back to the last success). If the workflow YAML has a job with `needs: test`, say so — a red `test` starves it and it shows as *skipped*, never failed. Offer `gh run view <run-id> --log-failed`; don't auto-fix.
- `PUBLIC_DRIFT=drift` → **urgent** ⚠️: a project that should be private has rows on the live unauthenticated endpoint. List the project(s)/table(s) from the indented lines and point at `.venv/bin/python scripts/unpublish_public.py <project> --apply` (venv python — the script imports `anthropic` via `claude_api`), or re-run the audit with `--fix`. `config` → flag once: `docs/public-allowlist.txt` missing or empty (a config problem, distinct from drift). `ok` / `skip` → silent. `incomplete` → live Turso data could not be checked (credentials missing or partial); never report it clean. `error` → one line: the audit itself failed (see the indented output) — this is *could not check*, not *ok*.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote). Open with the Machine label from the SessionStart-hook context (e.g. "On mini.") so cross-machine context is immediate.

If any branch (current or otherwise) is behind origin, end with a short ⚠️ block listing each behind branch and the suggested `git pull --rebase` / `git checkout` command. If there are remote-only branches that look like in-progress work from another machine, mention them too.

If the CI check found broken CI or the public-drift check found public-data drift, lead the summary with those ⚠️ blocks (drift first — it's a live privacy exposure, not just a build being red) — both are more urgent than a stale branch or a drifted CLAUDE.md.

If the user passed arguments with this command, address those — don't suggest a separate task.

Delegate only when the user requests it or an applicable instruction requires it.
For a bounded task that benefits from delegation, use a narrowly scoped prompt
and a cheaper model when authorized; do not fork the full conversation by default.
