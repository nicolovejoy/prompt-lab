---
name: handoff
description: Save session findings and next steps, capture commits, and close this session
allowed-tools: Bash(git:*), Bash(sqlite3:*), Bash(python3:*), Bash(~/.claude/bin/gc-read.sh:*), Bash(~/.claude/bin/gc-write.sh:*), Bash(~/.claude/bin/handoff.sh:*), Read
---

Close out this session briefly. Do not delegate. Routine handoff saves local session
continuity; nightly synthesis produces daily and weekly recaps. For an immediate
recap use `/handoff-full` (Codex: `$source-command-handoff-full`). Document and memory
maintenance belongs to explicit `/workflow-maintenance`, not routine closeout.

Stop on any failed write or Python traceback and report the error. Never claim
success or close the session after a failed required save.

## Codex: host request and receipt only

Use this branch exclusively in Codex; the Claude Code instructions below do not apply.
Never call DB helpers, Python SQLite, or escalation for bookkeeping. Full handoff
and DB-backed context reads remain gated separately.

Retain the host-injected `Session: <session_id>|<started_at>` and `GC_IDENTITY`
object from SessionStart/UserPromptSubmit. Require matching session, start time,
project and conversation provenance. Missing or inconsistent identity is an error;
stop bookkeeping, never guess a row or derive authority from a file or environment.
Inspect `git status --short`; leave uncommitted work intact.

Gather commits with `git log --since="<started_at>Z" --format="%H|%ct|%s"`.
Split each line at its first two pipes only. Preserve the integer `%ct` Unix UTC
seconds and full hash; zero commits is valid. Write a concise summary (usually
50–100 words). Queue exactly one UTF-8 JSON file at the injected `request_path`:

```json
{
  "version": 1,
  "request_id": "<new canonical UUID>",
  "project": "<injected project>",
  "conversation_id": "<injected conversation_id>",
  "session_id": 123,
  "started_at": "<injected started_at>",
  "summary": "<findings, decisions, remaining work and next step>",
  "commits": [{"hash": "<full lowercase hash>", "message": "<subject>", "timestamp": 981173106}]
}
```

Replace the example session ID and commit with actual values; use `[]` for no
commits. Maximum file size 131072 bytes, summary 16384 UTF-8 bytes, 256 commits,
and 4096 UTF-8 bytes per subject. No additional fields. Do not silently truncate.
Create a regular mode-0600 file exclusively (`O_CREAT|O_EXCL|O_NOFOLLOW`); do not
follow symlinks or overwrite a pending request. Keep the exact request bytes and
UUID for retries. An existing pending file with different content is an error.
After a matching saved receipt, the agent may remove its own acknowledged file
before a later handoff creates a new UUID. The hook never removes request files.

Compute SHA-256 from the exact UTF-8 bytes you authored before publishing the
request; include exactly one `GC_REQUEST=<request_id>:<sha256>` marker in your
**queued** final message. Never adopt/re-hash an unknown existing request. The
host Stop event's final message binds your intent to those bytes, preventing a
peer from planting or modifying your request. Missing/ambiguous markers fail.
Report **queued**, then end the turn so Stop can run. Do not poll for Stop. Only a
host-origin Stop continuation containing `GC_RECEIPT` with `status: "saved"` and
matching request ID, project, conversation, session ID and start time authorizes a
saved claim. Request files or agent-writable receipt files are not proof. Missing
receipt means **pending**; an explicit failure must be reported. The hook saves
commits, summary and closure atomically; never close separately. After receipt,
report the result and next step briefly and end; repeated Stop exits without a loop.
Do not run the Claude Code steps below.

## Claude Code: existing direct-helper path

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
The unique index on `hash` (see `scripts/dedup_commits.py`) is what makes OR IGNORE actually ignore a re-run.

Save a concise session summary, usually 50–100 words. Include findings, key
decisions, unresolved questions and the next concrete step. Preserve details
needed to resume; reference existing files rather than writing new documentation.

Write the summary as UTF-8 plain text to an exact path matching
`/tmp/gc-session-<session_id>-<nonce>.txt`, using a file-writing tool rather than
shell redirection. The nonce may be a short random alphanumeric value. Then run
the helper as a simple command:

```bash
~/.claude/bin/gc-write.sh update-session-summary <session_id> /tmp/gc-session-<session_id>-<nonce>.txt
```

The helper accepts only that filename shape, a small user-owned regular file,
and consumes the file after a successful database commit. Its original stdin
form remains supported for compatibility, for Claude Code callers.

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
