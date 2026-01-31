# devlog

## 2026-01-31 (afternoon)

Dashboard UX improvements: clickable stat buttons that filter views, grid-based arrow key navigation across stats/toggles/filters/cards, 30% size reduction for rating buttons and tags input, and square corners throughout. Fixed focus bug where filter inputs retained focus when navigating to cards, blocking rating/delete keystrokes.

## 2026-01-31

Implemented commits-to-sessions linking: updated schema to use session_id instead of prompt_id, added migration for existing DBs (backfilled all 33 commits), updated /handoff to include session_id. Simplified /readup by removing prompt curation (now dashboard-only). Fixed dashboard refresh bug when viewing sessions.

## 2026-01-30 (afternoon)

Restructured repo for easy installation: `install.sh` symlinks workflow tools, `dashboard.sh` starts UI. Added session summaries to /handoff that get stored in DB and displayed in new Sessions view. Improved dashboard UX: auto-advance after rating/deleting, undo toast for deletes, context-aware stats. Integrated Ralph Wiggum one-task-per-session approach into /readup.

Commits: 917dab1, 79b4c86, 2b1d936, 57571e5, 04bdcb2, 19eef76, 6809213, f64ec23, 78f94f5, bca5170

## 2026-01-30

Fixed context capture: `tac` not available on macOS, switched to `tail -r`. Context now working - tested and confirmed in dashboard.

Added context capture: hook now extracts Claude's last response from transcript and stores it with the prompt. UI shows context above each prompt with "Claude:" prefix.

Added help overlay (`?` to toggle) and context-aware footer that shows relevant shortcuts based on state. Made repo public on GitHub.

Added bulk delete feature with checkboxes, select all, and keyboard shortcuts (space to toggle, x to delete). Added search box that filters prompts by text, tags, or project name.

Confirmed prompt auto-logging hook is now working after the absolute path fix. Updated CLAUDE.md to reflect.

## 2026-01-29

Set up local dev environment. Created `run.sh` to bootstrap venv and run Flask server. Investigated why prompt auto-logging hook isn't firing - hook script works manually but isn't being triggered by Claude Code. Changed hook command from `~` to absolute path in `~/.claude/settings.json`, needs restart to test.
