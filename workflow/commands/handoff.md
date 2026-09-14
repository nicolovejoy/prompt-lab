---
name: handoff
description: Save session findings and next steps, capture commits, and close this session
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(python3:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/handoff.sh:*), Read
---

Close out this session briefly. Do not delegate. Routine handoff saves local session
continuity; nightly synthesis produces daily and weekly recaps. For an immediate
recap use `/handoff-full` (Codex: `/prompts:handoff-full`). Document and memory
maintenance belongs to explicit `/workflow-maintenance`, not routine closeout.

Stop on any failed write or Python traceback and report the error. Never claim
success or close the session after a failed required save.

## 1. Validate identity and inspect the working tree

Use the authoritative `<session_id>|<started_at>` retained from readup:

```bash
~/.claude/bin/gc-read.sh current-session <session_id>
git status --short
```

If readup has not run, register with `~/.claude/bin/gc-write.sh register-session`
and retain its result. A missing or different validated ID is an error; never
choose another window's row. Report uncommitted files in the final handoff;
leave them intact and continue saving the session. Handoff does not commit files.

## 2. Capture commits and session continuity

Capture commits since session start using actual UTC commit timestamps:

```bash
git log --since="<started_at>Z" --format="%H|%ct|%s"
```

Insert each hash, message and validated session ID into the local database at
`~/.claude/prompt-history.db` with Python sqlite3 parameter bindings:
`INSERT OR IGNORE INTO commits (hash, message, timestamp, session_id) VALUES (?, ?, datetime(?, 'unixepoch'), ?)`.
Use `%ct` for Unix seconds; never substitute insertion time. Zero commits is normal.

Save a concise session summary via stdin, usually 50–100 words. Include findings,
key decisions, unresolved questions and the next concrete step. Preserve details
needed to resume; reference existing files rather than writing new documentation.

```bash
~/.claude/bin/gc-write.sh update-session-summary <session_id> <<'SUMMARY'
<session findings, decisions, open questions, next step>
SUMMARY
```

## 3. Coordinate only when needed

If a peer needs an actionable result and the user authorized messaging, post a
short note through `~/.claude/bin/handoff.sh append <file>` with a complete dated
`### YYYY-MM-DD <from> → <to>: <subject>` heading. Otherwise skip. Do not reread
channel history, poll for replies, or start extra investigations during closeout.

## 4. Close and report

After required saves succeed, close only the validated session:

```bash
~/.claude/bin/gc-write.sh end-session <session_id>
```

Report the saved result, next step and any uncommitted work in a few lines.
Daily/weekly recaps arrive after the next successful nightly run; no recap is
written by this command. Do not run API synthesis, backlog checks, document
trimming, public refresh, or remote synchronization as extra closeout steps.
