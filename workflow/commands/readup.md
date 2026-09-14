---
name: readup
description: Start a session — register a session row, sync to remote, read project context
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/sync-shared-md.sh:*), Bash(~/.claude/bin/session-context.sh:*), Bash(~/.claude/bin/readup-checks.sh:*), Bash(~/.claude/bin/handoff.sh:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Bash(mkdir:*), Bash(touch:*), Bash(gh issue list:*), Bash(gh pr list:*), Bash(gh run list:*), Bash(gh run view:*), Bash(.venv/bin/python scripts/check_public_allowlist.py:*), Bash(python3 scripts/check_public_allowlist.py:*), Read, Write, Edit, Glob, Agent, ListAgents
---

Start a session. Be concise.

Note: a SessionStart hook usually already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines (Claude Code sessions get this automatically). **If you already have that context, do not re-fetch it.** If you don't — Codex and any other agent without an equivalent hook won't — run this first:

```bash
~/.claude/bin/session-context.sh
```

and read its output before continuing. Either way, this command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session` (this will prompt — writes aren't auto-allowed)
2. Run the bundled read-only checks (fetch, branch tracking, worktrees, codex branches, resync marker, CLAUDE.md/AGENTS.md conventions drift, handoff flush, CI, public drift) in ONE call: `~/.claude/bin/readup-checks.sh`. It never pulls or modifies the tree. Interpret its output with the table under "Interpreting readup-checks" below.
3. Read CLAUDE.md in full (focus on Next Steps + project conventions). The hook's injected context covers recent activity, but not project intent.
4. Other agents on this repo: if the `ListAgents` tool is available, call it and flag any other local or cloud session whose name/task suggests this repo (a cloud agent's work won't show in `git status` at all until it pushes). `ListAgents` missing or erroring → skip silently, never block session start.

## 4. Backfill recent unsummarized days (lazy synthesis)

Pull recent unsummarized days for this project:

```bash
~/.claude/bin/gc-read.sh unsummarized-context
```

The output is `{"total": N, "days": [...]}`. Behavior:

- `total == 0` → skip silently.
- `total > 5` → print one line ("N unsummarized days; nightly synthesizer will catch them") and skip. Avoids piling a long batch into a session-start command.
- `total ∈ [1, 5]` → for each entry in `days`, synthesize a daily summary from its `prompts`/`commits`/`sessions` (focus on WHAT was done and WHY, 2-4 sentences, 1-3 key decisions). Write to `/tmp/gc-daily-<project>-<session_id>-<date>.json` with shape:

```json
{
  "project": "<basename of pwd>",
  "date": "<the day from the helper>",
  "summary": "<2-4 sentence summary>",
  "key_decisions": ["<decision 1>", "<decision 2>"],
  "prompt_count": <len(day.prompts)>,
  "session_count": <len(day.sessions)>,
  "commit_count": <len(day.commits)>
}
```

Persist each via:

```bash
python3 -c "
import json, sys, os; sys.path.insert(0, os.environ.get('PROMPT_LAB_DIR', os.path.expanduser('~/src/prompt-lab')))
from store import get_store
d = json.load(open('/tmp/gc-daily-<project>-<session_id>-<date>.json'))
s = get_store(); s.migrate()
s.upsert_daily_summary(model='claude-code', **d)
s.close()
print('Daily summary saved for', d['project'], d['date'])
"
```

This saves the nightly synthesizer from running for these days (~$0.02-0.04 each at Sonnet rates). The nightly remains as safety net for projects you don't open via /readup.

## 5. Interpreting readup-checks

One line of behaviour per key. Anything not listed here → say nothing.

- `PROJECT`: informational; silent, except `PROJECT_RESOLVER=fallback-basename` → one line: `_gc_project.sh` not installed alongside.
- `REMOTE` / `TRACKING` / `REMOTE_ONLY`: any branch ahead/behind, or an unfamiliar remote-only branch → flag it in the summary so the user can decide whether to `git pull --rebase` / `git checkout` manually. Clean → silent.
- `WORKTREES:` block (more than the main checkout) → another agent may be mid-task; flag it with its branch. `CODEX_BRANCHES:` block → Codex has touched or is touching this repo (it always works on `codex/<desc>`); flag it. Combine with `ListAgents` from the Do list, item 4.
- `RESYNC=… due=yes` → invoke `/resync --light` inline and fold its findings into the summary (no separate wall of text). `due=no` → silent.
- `CONVENTIONS_CLAUDE` / `CONVENTIONS_AGENTS`: `drift` or `missing` → one line per file offering the exact fix `~/.claude/bin/sync-shared-md.sh --apply ./<file>` (review the `git diff`, then commit). Never apply automatically — materializing into a checked-in file is the user's call. `in sync` / `absent` / `skip` → silent. `unknown` → one line: sync-shared-md.sh printed nothing.
- `HANDOFF_SYNC=conflict` or `offline` → one line; the entry stays safe locally (conflict: resolve in `~/src/.handoff`; offline: re-run `handoff.sh sync` later). `ok` / `absent` → silent. `error` → one line: handoff sync failed for an unexpected reason; check `handoff.sh sync` by hand.
- `CI_PROBE=skip` → silent. `CI_PROBE=error` → say ONE line: "couldn't read CI status (`<first indented line>`)". Never report an error as "no CI configured" — you don't know. `CI_PROBE=ok` with `[]` and no `CI_PROBE_NOTE` → no CI, silent. `CI_PROBE_NOTE=workflow-files-exist-but-no-runs` → flag one line (Actions disabled, or every trigger filtered out). Latest run in `CI_MAIN:` (and `CI_BRANCH:` if present) with `conclusion: "success"` or still `in_progress`/`queued` → silent. `failure` / `cancelled` / `timed_out` → ⚠️ line in the summary naming workflow, branch, and how long it's been red (walk `createdAt`/`conclusion` back to the last success). If the workflow YAML has a job with `needs: test`, say so — a red `test` starves it and it shows as *skipped*, never failed. Offer `gh run view <run-id> --log-failed`; don't auto-fix.
- `PUBLIC_DRIFT=drift` → **urgent** ⚠️: a project that should be private has rows on the live unauthenticated endpoint. List the project(s)/table(s) from the indented lines and point at `.venv/bin/python scripts/unpublish_public.py <project> --apply` (venv python — the script imports `anthropic` via `claude_api`), or re-run the audit with `--fix`. `config` → flag once: `docs/public-allowlist.txt` missing or empty (a config problem, distinct from drift). `ok` / `skip` → silent. `error` → one line: the audit itself failed (see the indented output) — this is *could not check*, not *ok*.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote). Open with the Machine label from the SessionStart-hook context (e.g. "On mini.") so cross-machine context is immediate.

If any branch (current or otherwise) is behind origin, end with a short ⚠️ block listing each behind branch and the suggested `git pull --rebase` / `git checkout` command. If there are remote-only branches that look like in-progress work from another machine, mention them too.

If the CI check found broken CI or the public-drift check found public-data drift, lead the summary with those ⚠️ blocks (drift first — it's a live privacy exposure, not just a build being red) — both are more urgent than a stale branch or a drifted CLAUDE.md.

If the user passed arguments with this command, address those — don't suggest a separate task.

If this session's work turns out to be executing a written plan (or the user hands you a multi-task todo), invoke `superpowers:subagent-driven-development` (if available) before starting implementation — per-task subagents keep the main context lean for the long sessions readup starts. This is a conditional pointer, not a step: sessions that are discussion, ops, or a single fix skip it entirely.
