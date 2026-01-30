# devlog

## 2026-01-30

Confirmed prompt auto-logging hook is now working after the absolute path fix. Updated CLAUDE.md to reflect.

## 2026-01-29

Set up local dev environment. Created `run.sh` to bootstrap venv and run Flask server. Investigated why prompt auto-logging hook isn't firing - hook script works manually but isn't being triggered by Claude Code. Changed hook command from `~` to absolute path in `~/.claude/settings.json`, needs restart to test.
