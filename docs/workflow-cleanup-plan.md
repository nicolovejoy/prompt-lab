# Smaller workflows, clearer docs

Implemented in source, 2026-09-14; reinstall and live cost measurement pending. Keep the custom commands and the continuity they provide.

1. **Make routine handoff small.** Save the session’s findings, decisions and next steps; capture commits and close the correct session. Let nightly synthesis handle daily/weekly recaps, with an explicit full handoff when needed. Review readup’s overlapping summary backfill too. Move document trimming and backlog maintenance out of routine closeout. Verify nightly coverage before switching.

2. **Measure the savings.** Compare similar sessions before and after: handoff usage, tool calls and continuity quality. The reported 10% overlaps long-context and subagent usage; it is not all removable overhead. Track any cost shifted to nightly API calls. Use cheaper agents only for bounded tasks that justify delegation.

3. **Give docs a clear front door.** Add a short `docs/README.md` linking setup, daily operations, architecture, active work and history. Keep `CLAUDE.md` focused on essential rules and current pointers. Give each active plan a status; archive completed plans with links preserved. Consolidate repeated workflow status across the roadmap, checkpoint and startup brief.

4. **Review concrete cleanup candidates.** Check consumers before retiring the legacy mobile UI, unwired `todos.py`, and overlapping root/scripts URL-backfill utilities. Separate historical repair scripts from routine tools. Preserve public drafts as the publishing audit trail. Archive resolved `.handoff` entries with outcomes; document same-repo pairing and polling limitations.

5. **Finish and record acceptance.** Complete the Songpath paired-session test, record installation and verified results in one place, and keep untested resume/fork and permission-profile gates explicit. Then make small cleanup changes with relevant checks and repaired links.


Source-size baseline versus this change: handoff 11,681 → 3,037 bytes (74% less),
readup 9,002 → 7,437 (17% less), CLAUDE.md 35,127 → 27,258 (22% less).
This is not a token-usage saving estimate. Compare several similar sessions after
installation, recording model, context size, handoff tool calls and session
continuity alongside the usage report. Check nightly synthesis token/cost logs
for shifted API usage. No extra agents or paid benchmark runs are required.

Results: paired full-handoff acceptance passed; default/full/maintenance commands
are separated; nightly coverage and guarded saves have isolated regressions;
docs index and current-work page are in place; three old plans have archive
redirects; legacy UI/scanner/backfill source is archived. Historical repair scripts
and public drafts keep their original paths with an inventory explaining their role.
The 12 verified Songpath smoke-test messages were moved to the channel archive
with outcomes and all bodies preserved. Other channels remain an evidence-led
task; this change does not guess that unanswered messages are resolved.
