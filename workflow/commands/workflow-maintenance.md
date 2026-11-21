---
name: workflow-maintenance
description: Explicitly review project instructions, memory, and maintenance backlog
allowed-tools: Bash(git:*), Bash(~/.claude/bin/claude-md-size.sh:*), Bash(stat:*), Bash(date:*), Bash(wc:*), Bash(mkdir:*), Bash(touch:*), Bash(.venv/bin/python scripts/draft_public_refresh.py:*), Read, Write, Edit
---

Run only when requested. Review the working tree first; preserve unrelated edits.
Update CLAUDE.md Next Steps and MEMORY.md only where current evidence warrants it.
Keep open decisions and invariants; link to reference docs instead of repeating them.
Do not spawn agents for routine maintenance. Review the diff and report changes;
commit only if the user requested a commit. Do not close or summarize sessions.

## CLAUDE.md size check (weekly)

CLAUDE.md is loaded into every session; narrative that has settled belongs in `docs/history.md`, not in the brief. Check whether a trim is due (oversized AND not trimmed in the last 7 days):

```bash
~/.claude/bin/claude-md-size.sh
```

It prints `own_bytes=… shared_bytes=… lines=… limit=… trim_age_d=… due=yes|no`, or `absent`. `own_bytes` leaves out the synced block between the `SHARED-CONVENTIONS` markers, which a repo cannot cut. `/readup` reads the same line, so the two agree on what is too big.

- `absent`, or `due=no` → skip silently (small enough, or trimmed in the last 7 days; let it settle).
- `due=yes` → trim now, then touch the marker `m=~/.claude/state/claude-trim-$(basename "$PWD").touch`:
  1. Move settled narrative out: any paragraph in Next Steps / Traps / Settled that explains *how something came to be* (a fix's story, an incident timeline, rejected alternatives) goes verbatim into `docs/history.md` under a heading `### <its lead-in> (moved YYYY-MM-DD)` at the top of the build log, newest first. Create `docs/history.md` with a one-paragraph intro if the repo has none.
  2. Keep in CLAUDE.md, each at ≤ 3 lines: what is still open, the decision made (with date), invariants, traps as rule + one-line reason, file pointers.
  3. Never edit between the `SHARED-CONVENTIONS` markers; never remove an open item, an invariant, or a trap — compress, don't delete.
  4. `mkdir -p ~/.claude/state && touch "$m"`, then tell the user in one line what moved and the before/after byte counts. Include the move in the reviewed diff.
  5. If nothing qualifies (every item is already at its ≤3-line floor), say so in one line, touch the marker anyway, and do not force a trim.

## Offer a public-refresh draft (prompt-lab repo only, opt-in)

Public data does not refresh itself by design, so it goes stale silently — it sat six weeks stale before a consumer repo noticed. Surface the backlog here, but never act on it unprompted.

Run (prompt-lab repo only; skip silently elsewhere):

```bash
.venv/bin/python scripts/draft_public_refresh.py --list
```

If every project reads `0 unpublished week(s)`, say nothing. Otherwise mention the backlog in one line and offer to draft — do **not** generate a draft unless the user asks. Drafting is cheap; reviewing it is the expensive part, and it's the user's time.

If asked, generate the draft for that project:

```bash
.venv/bin/python scripts/draft_public_refresh.py <project>
```

Then fill in each `### PUBLIC` block in the generated `drafts/public-<project>-<date>.md`. Write each one **from scratch** against the private text as source material — do not lightly edit the private prose. It is unscrubbed synthesizer output over raw prompts and routinely names clients and collaborators, quotes absolute paths, and describes unreleased plans. Target what a stranger reading a portfolio should see: what was built and why it mattered, no issue numbers, no people, no infrastructure specifics. Leave a block as `TODO` to skip that week.

Then stop and hand it to the user for review. **Never run the publish step yourself** — the human review of the committed file *is* the privacy gate. The user runs:

```bash
.venv/bin/python scripts/publish_public_draft.py drafts/public-<project>-<date>.md --apply
.venv/bin/python sync_to_turso.py
```
