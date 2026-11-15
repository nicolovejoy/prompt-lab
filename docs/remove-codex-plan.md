# Codex removal: done

Codex was retired 2026-10-15 (Nico: stick with Claude Code). Removal finished 2026-10-28.
The staged plan is this file's git history.

Removed: the Codex command renderer in `workflow/install.sh`, the Codex branches in the
hooks and `workflow/bin/`, the `AGENTS.md` machinery, the `cx`/`duet` launchers, the Codex
workflow files, probes, tests and docs (PRs #88, #89), the `*-codex` clones, `~/.codex`
and the Codex desktop app.

Kept on purpose:

- History rows keep their `codex:` owners, and the `*-codex` rows in `project_aliases` stay, so old sessions still read.
- Codex entries in `~/src/.handoff` and `docs/history.md` stay as history.

Left: `AGENTS.md` in musicforge, person-tracking and split-recording. Each repo's call.

Do not add a second agent path without a new decision.
