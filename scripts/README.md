# Script inventory

Run scripts from the repository root with `.venv/bin/python`. Consult each
script's `--help` and source before a mutation; being listed here does not mean
it is safe or necessary to rerun against live data.

| Category | Entry points |
| --- | --- |
| Workflow checks | `test_session_identity.py`, `test_workflow_roundtrip.py`, `test_lean_nightly.py`, `test_day_context.py` |
| Operational checks | `check_public_allowlist.py`, `probe_codex_permissions.py` |
| Project names and URLs | `alias.py`, `backfill_project_urls.py` (maintained GitHub scanner) |
| Public review/publishing | `draft_public_refresh.py`, `publish_public_draft.py`, `unpublish_public.py` |
| Regression suites | `test_*.py`; the CI gate is `.github/workflows/test.yml` |

Historical repairs and initialization utilities are kept at their existing paths:
`backfill_prompt_kind.py`, `backfill_public_*.py`, `cleanup_agent_worktree_rows.py`,
`close_stale_sessions.py`, `merge_cutover_sessions.py`, `regroup_weekly_rollups.py`,
`hide_scratch_projects.py`, `create_*.py`, and `seed_*.py`. They are not routine
maintenance and are not run by handoff. Their old names and paths may appear in
incident records; preserving those references is preferable to a bulk rename.

The older root URL backfill, unwired todo scanner and legacy mobile UI are in
[the source archive](../archive/README.md). Public drafts remain in `drafts/` as
an audit trail.
