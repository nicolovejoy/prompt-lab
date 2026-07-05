#!/bin/bash
# reap-playwright.sh — kill orphaned Playwright browsers (issue #8).
#
# Playwright browsers ("Chrome for Testing", headless shells) run from
# ~/Library/Caches/ms-playwright* — never /Applications — so their command
# lines contain "ms-playwright". A browser whose owner (Playwright MCP server
# or `playwright test` runner) is still alive has that owner as its parent;
# a genuine orphan has been reparented to launchd (PPID 1). Killing only
# ms-playwright processes with PPID 1 therefore never touches a live
# session's browser. A bare `pkill -f ms-playwright` is NOT safe.
#
# Single SIGTERM pass: killing an orphaned main browser process takes its
# helpers down with it. Helpers that were individually reparented to PPID 1
# are matched directly; anything that survives is caught by the next run
# (fires on every Claude session start).

for pid in $(pgrep -f "ms-playwright" 2>/dev/null); do
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
    [ "$ppid" = "1" ] && kill "$pid" 2>/dev/null
done
exit 0
