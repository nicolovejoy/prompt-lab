# Hook bookkeeping consumer implementation plan

Spec: `docs/codex-workflow-roadmap.md`, proposed implementation 1–6 and Phase 4 step 2; the user's explicit implementation request approves this scope.

- [x] Add standalone installed-copy tests first. Fake SQLite schema and throwaway Git only; assert identity, ownership, atomic saves, first hash attribution, durable replay, request validation, failures, protected imports, and receipts.
- [x] Add a dedicated Codex host entry point and bounded consumer. Reuse `_gc_session_identity.py` and `_gc_project.sh`; Claude hooks/wrappers retain their existing path. Use isolated Python with copied dependencies, never checkout imports.
- [x] Stage a host bundle with explicit DB and allowed workspace configuration. No default live DB, no installation into user directories in this task. Derive one request filename from host conversation/project. Preserve input files; never delete or replace agent requests.
- [x] Save commits, summary, closure, and durable request ledger together. Hash-only first attribution is compatible with issue #57; do not deduplicate/migrate existing commits. Compare replay payload digests and ownership.
- [x] Extend the existing real-CLI lifecycle fixture to use this installed-copy consumer and nonzero Git commits. Deliver a post-commit receipt through Stop block, suppress its repeated continuation, and recover a commit-before-output crash.
- [x] Update command branches and gated pilot instructions, add CI runner, run relevant regressions/lint, review diff, open PR and wait for green CI (final gate pending until reported). Record disposable results and untested production/desktop/live gates. Install nothing.

Receipt transport cannot atomically acknowledge model delivery with SQLite. Mark a receipt emitted only after stdout flush; interruption before emission leaves it recoverable. Replay in a later turn may re-deliver the same durable receipt without repeating the save. A missing model-visible receipt always means pending.

Review correction: require the owning Stop final message to authorize new request UUID+SHA-256; canonicalize protected paths after rejecting symlinks; normalize deep-JSON errors. All three have regression coverage.
