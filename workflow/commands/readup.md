---
name: readup
description: Start a session — register a session row, sync to remote, read project context
allowed-tools: Bash(git:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/sync-claude-md.sh:*), Bash(~/.claude/bin/handoff.sh:*), Bash(stat:*), Bash(date:*), Bash(basename:*), Bash(mkdir:*), Bash(touch:*), Bash(gh issue list:*), Bash(gh pr list:*), Bash(gh run list:*), Bash(gh run view:*), Bash(.venv/bin/python scripts/check_public_allowlist.py:*), Bash(python3 scripts/check_public_allowlist.py:*), Read, Write, Edit, Glob, Agent
---

Start a session. Be concise.

Note: the SessionStart hook already injected today's date, last-session summary, recent commits, working-tree state, and bulletin headlines. **Do not re-fetch any of that.** This command exists for the side effects (session row, remote check, full CLAUDE.md read) that the hook deliberately skips.

## Do (in parallel)

1. Register session: `~/.claude/bin/gc-write.sh register-session` (this will prompt — writes aren't auto-allowed)
2. Remote check (no pull): `git fetch --quiet --all --prune && git status -sb` for the current branch, then `git for-each-ref --format='%(refname:short) %(upstream:short) %(upstream:track)' refs/heads | awk '$3 != ""'` to catch other local branches that are ahead/behind their upstream (useful when work happened on another machine). Also list remote branches with no local tracking: `git branch -r --no-merged | grep -v HEAD`. Fetch is cheap, never modifies the tree. If anything is behind/ahead or there are unfamiliar remote branches, flag them in the summary so the user can decide whether to `git pull --rebase` or `git checkout` manually. If everything is clean, say nothing.
3. Read CLAUDE.md in full (focus on Next Steps + project conventions). The hook's injected context covers recent activity, but not project intent.

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

## 5. Auto-resync if drift likely

Check the resync marker for this project:

```bash
marker=~/.claude/state/resync-$(basename "$PWD").touch
if [ -f "$marker" ]; then
    age_h=$(( ($(date +%s) - $(stat -f %m "$marker" 2>/dev/null || stat -c %Y "$marker")) / 3600 ))
    commits_since=$(git log --oneline --since="@$(stat -f %m "$marker" 2>/dev/null || stat -c %Y "$marker")" | wc -l | tr -d ' ')
else
    age_h=9999
    commits_since=9999
fi
echo "resync_age_h=$age_h commits_since=$commits_since"
```

If `age_h >= 48` AND `commits_since > 3`, invoke `/resync --light` inline. Fold its findings into the session summary below (don't print a separate wall of text). If either condition is false, skip silently.

## 6. Check shared-conventions drift (check only — never auto-write)

Verify this repo's CLAUDE.md carries the current shared-conventions block:

```bash
~/.claude/bin/sync-claude-md.sh --check ./CLAUDE.md
```

- `in sync` → say nothing.
- `missing` / `drift` → flag one line in the summary and offer the exact fix: `~/.claude/bin/sync-claude-md.sh --apply ./CLAUDE.md` (review the `git diff`, then commit). Never apply automatically — materializing into a checked-in file is the user's call.
- `absent` (no CLAUDE.md) → skip silently; not every repo warrants one.

The block is auto-managed between `SHARED-CONVENTIONS` markers; the source of truth is `prompt-lab/workflow/claude-md-shared.md`.

## 7. Flush the cross-repo handoff channel

The SessionStart hook only *pulls* the handoff repo (read-only). If a prior session appended an entry while offline, or hit a push conflict, that commit is still sitting unpushed in `~/src/.handoff`. Flush it best-effort:

```bash
[ -d ~/src/.handoff/.git ] && ~/.claude/bin/handoff.sh sync
```

- exit 0 → say nothing (nothing pending, or pushed cleanly).
- exit 3 (conflict) / 4 (offline) → flag one line so it's not silently lost; the entry stays safe locally. Skip entirely if `~/src/.handoff` isn't present.

## 8. Check CI health (most recent builds)

Silent CI breakage is easy to miss for days — e.g. a lint error blocked `test` (and everything downstream, including `deploy`) on every push to `main` for 3 days before anyone noticed. Check the most recent runs, not just "does a workflow exist":

```bash
default_branch="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
default_branch="${default_branch:-main}"
gh run list --branch "$default_branch" --limit 5 --json status,conclusion,name,displayTitle,createdAt,headSha,url 2>/dev/null || echo '[]'
```

If the current branch isn't `$default_branch`, also check it (a PR/feature branch can have its own failing CI independent of main):

```bash
current_branch="$(git branch --show-current)"
[ "$current_branch" != "$default_branch" ] && gh run list --branch "$current_branch" --limit 3 --json status,conclusion,name,displayTitle,createdAt,url 2>/dev/null
```

Behavior:

- `gh` missing, not authenticated, no workflows configured, or the API call errors → skip silently. Not every repo runs CI, and this must never block session start.
- Latest run per branch has `conclusion: "success"`, or `status` is still `in_progress`/`queued` → say nothing.
- Latest run's `conclusion` is `failure` / `cancelled` / `timed_out` → **this is CI actively broken.** Don't bury it in the wall of text — surface it as its own ⚠️ line in the summary below, naming the workflow, the branch, and roughly how long it's been red (walk the returned `createdAt`/`conclusion` pairs back to the last `success` to bound it, e.g. "red since <date>, N consecutive failures"). If the workflow YAML defines a `deploy` (or other) job with `needs: test` or similar, call that out too — a red `test` run silently starves it, and a starved job never shows as "failed," just perpetually skipped, so it's easy to miss unless named explicitly. Don't auto-fix; offer to pull the failing step's log (`gh run view <run-id> --log-failed`) and investigate if the user wants to chase it now.

## 9. Check public-data drift (prompt-lab only)

`public_session_summaries` / `public_weekly_rollups` feed the unauthenticated `/api/public_history` endpoint — safe-by-construction only if every row belongs to a project on `docs/public-allowlist.txt`. Drift lands at sync time (`sync_to_turso.py` now runs this same check non-fatally after every sync — see CLAUDE.md), but a sync doesn't always run right before you sit down, so double-check here too. This table only exists in this repo:

```bash
if [ "$(basename "$PWD")" = "prompt-lab" ] && [ -f scripts/check_public_allowlist.py ]; then
  if [ -x .venv/bin/python ]; then
    .venv/bin/python scripts/check_public_allowlist.py 2>&1
  else
    python3 scripts/check_public_allowlist.py 2>&1
  fi
fi
```

Behavior:

- Not in the prompt-lab repo, or the script's missing → skip silently.
- Exit 0 (`OK: no public rows outside the allowlist.`) → say nothing.
- Exit 1 (drift) → flag it — this means a project that's supposed to be private has public rows on the live, unauthenticated endpoint. List the offending project(s) and which store/table (from the script's output), and point at the fix: `.venv/bin/python scripts/unpublish_public.py <project> --apply` (venv python, not system `python3` — the script imports `anthropic` via `claude_api`) (or re-run with `--fix` to have the audit print the exact commands). Treat this as urgent — it's a privacy miss, not a stale-branch nuisance.
- Exit 2 (allowlist missing/empty) → flag once as a config problem (`docs/public-allowlist.txt` missing or empty), distinct from data drift.

## Then

Summarize in a few lines: where the project stands (from CLAUDE.md), what's next, and whether the working tree needs attention (uncommitted changes, behind/ahead of remote). Open with the Machine label from the SessionStart-hook context (e.g. "On mini.") so cross-machine context is immediate.

If any branch (current or otherwise) is behind origin, end with a short ⚠️ block listing each behind branch and the suggested `git pull --rebase` / `git checkout` command. If there are remote-only branches that look like in-progress work from another machine, mention them too.

If step 8 found broken CI or step 9 found public-data drift, lead the summary with those ⚠️ blocks (drift first — it's a live privacy exposure, not just a build being red) — both are more urgent than a stale branch or a drifted CLAUDE.md.

If the user passed arguments with this command, address those — don't suggest a separate task.
