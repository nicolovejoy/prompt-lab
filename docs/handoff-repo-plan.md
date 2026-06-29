# Cross-repo handoff → standalone synced git repo

Status: **planned + pressure-tested 2026-06-29; not yet built.** Tracking issue: see GitHub.

## Problem

Cross-repo agent coordination lives in `~/src/.handoff/*.md` (currently
`selected-projects-prompt-lab.md`, `prntd-prompt-lab.md`). Two structural faults:

1. **Not in git** — no history, no backup. A bad append or `rm` is unrecoverable.
2. **Machine-local** — it's a "cross-agent" channel that only syncs agents on the
   *same* machine. mini and laptop hold divergent copies and never reconcile.
3. **One-sided awareness** — only prompt-lab's `CLAUDE.md` references the channel;
   selected-projects and prntd never mention it, so their agents don't read it.

Near-miss that prompted this: the `sync-claude-md.sh --apply` clobber (2026-06-29)
showed how fast unversioned/automated edits destroy content. Git was the backstop
for CLAUDE.md; the handoff files have no such net.

## Why a standalone repo (not "commit into prompt-lab", not Turso)

- **Deploy coupling is the killer.** prompt-lab `main` → GitHub Actions → Vercel
  prod deploy, no path filter. Committing handoff notes into prompt-lab would
  redeploy the dashboard on every coordination note. Absurd. A standalone repo has
  no such side effect.
- **Ownership matches reality.** The file coordinates two *peer* repos; neither
  owns it. A neutral shared repo scales symmetrically to N pairings (already 2).
- **Pure git logs.** Code repos keep code history; the handoff repo keeps
  coordination history. No interleaving, no cross-repo agent committing into a repo
  it isn't working in.
- **Turso is the wrong layer.** The value is "an agent opens a markdown file at
  session start." A DB adds a fetch+creds step at exactly the frictionless moment.
  Keep it a file. (Same reasoning that rejected `@import` for shared conventions.)

## Decisions (recommended)

- **A1** Host: new private GitHub repo `nicolovejoy/handoff`, cloned to `~/src/.handoff`.
- **B1** Keep the `~/src/.handoff` path (zero reference churn).
- **C1** Fresh baseline import (no prior git history exists to preserve).
- **D1** Sync trigger: auto-pull at session start, time-boxed + best-effort, plus
  push-on-write. (Pull must NEVER block a session — see portability findings.)
- **E2** Write path: a small wrapper `workflow/bin/handoff.sh` (`append`, `sync`)
  that pull-rebases → commits → pushes atomically and surfaces conflicts loudly.
- **F1+F2** Awareness: session-start hook auto-injects the matching file's `## Active`
  section (load-bearing), plus a short pointer stanza in each side's CLAUDE.md.
- **G2** Matching: front-matter `repos: [a, b]` manifest in each file; hook greps it.
  (Filenames can't be split on `-` — repo names contain hyphens.)

## Pressure test — results (2026-06-29)

Harness committed at `workflow/handoff-sim/` (`run-tests.sh` drives real git in a
throwaway `/tmp` tree against a prototype of the wrapper + hook pull). **26/26 pass.**

Scenario → invariant verified:
- **A** stale push-reject, different files → auto-rebase converges (both entries land).
- **B** stale push-reject, **same file same region → git CONFLICTS** (confirmed
  empirically). Wrapper surfaces rc=3, aborts the rebase, **keeps the local commit**,
  leaves the remote's entry intact. No data lost. (See "Known property" below.)
- **C** offline append → kept local (rc=4); a later `sync` pushes it. Nothing lost.
- **D** session-start pull with a dirty/uncommitted tree → `--autostash` preserves it
  and still merges the remote advance.
- **E** offline at session start → pull fails fast, hook returns 0 (graceful), working
  tree intact. The session is never blocked.
- **F** two concurrent same-machine appends → `mkdir` mutex serializes them; exactly
  two commits, no lost update, lock released.
- **G** `repos:` manifest matching: both sides match their file, unrelated project
  matches nothing.
- **H** no-op `sync` is idempotent; creates no empty commits.

### Portability findings (these shape the real implementation)

The machines are macOS with bash 3.2 and BSD userland. Discovered before building:
- **`flock` absent** → use a `mkdir`-based atomic mutex (validated in scenario F).
- **`timeout`/`gtimeout` absent** → use a background-process + watchdog-`kill` timeout
  (validated in scenario E). Real hook may want to kill the process *group* for
  network hangs over ssh/https.
- **bash 3.2** → no associative arrays / `${var^^}` in the shipped wrapper + hook.
- **BSD `sed`** rejects GNU `1,5{/re/p}` brace syntax → use `head -N | grep` for the
  manifest match.

### Known property: same-thread concurrent appends conflict

Scenario B proved two appends to the same file (same EOF region) **conflict** under
git rebase — they do not auto-merge. The wrapper handles it safely (surface + preserve,
never drop), but it IS a human-resolved conflict. Acceptable for a low-frequency
coordination log, and the pull-rebase-before-push window is small. If it ever becomes
painful, the mitigation is one-file-per-entry (entries as separate files that never
collide) at the cost of a more complex read model — defer until it hurts.

## Build steps (ordered, reversible)

1. `gh repo create nicolovejoy/handoff --private`.
2. `cd ~/src/.handoff && git init`, add `repos:` front-matter to each file, commit
   baseline, `git remote add origin … && git push -u origin main`.
3. Ship `workflow/bin/handoff.sh` (harden the prototype: stale-lock recovery, clear
   exit codes) + add to `install.sh` distribution + an allow rule.
4. Extend `workflow/hooks/session-start.sh`: time-boxed best-effort pull + inject the
   matching file's `## Active` block (portable patterns above).
5. CLAUDE.md: update prompt-lab's handoff stanza to the new write path; add pointer
   stanzas to selected-projects + prntd.
6. Update `/handoff` + `/readup` docs to call `handoff.sh`.
7. Re-run `install.sh` on mini.
8. **Laptop reconcile** (the one fiddly step): back up the laptop's `~/src/.handoff`
   copies, diff against the mini baseline now on the remote, splice in any laptop-only
   entries, push, then replace the laptop dir with a clean clone. Then `install.sh`.

## Rollback

Files stay plain markdown throughout. `rm -rf ~/src/.handoff/.git` + strip the hook
stanza returns to exactly the pre-migration state. No lock-in.
