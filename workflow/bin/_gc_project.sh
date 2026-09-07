#!/bin/bash
# _gc_project.sh — shared project-name resolution for gc-read.sh / gc-write.sh.
# Sourced, not executed. Defines gc_resolve_project().
#
# WHY THIS EXISTS
# ---------------
# Both gc scripts used to do `PROJECT="$(basename "$PWD")"`. Run either from an
# agent worktree under <repo>/.claude/worktrees/agent-<hash>/ and PROJECT
# resolved to `agent-<hash>` — a name no row in the DB has ever carried, because
# the prompt hook (workflow/hooks/log-prompt.sh) got the git-common-dir fix on
# 2026-08-05 and files everything under the real repo. So `current-session`,
# `today-counts` and `weekly-rollup-check` returned nothing/zero on a day full of
# prompts and commits, and /handoff wrote that emptiness into a session summary
# as fact. Hit for real 2026-08-15.
#
# The resolution below is deliberately identical in behaviour to the hook's.
# Three properties are load-bearing; do not "simplify" them away:
#
#  1. --git-common-dir, NOT --show-toplevel. A linked worktree's toplevel IS the
#     worktree, so --show-toplevel reintroduces the exact bug. The common dir is
#     always the main repo's .git.
#  2. ONLY exit code 128 ("not a git repository") buckets to `scratch`. Any other
#     git failure — git missing, or the Xcode license prompt that broke every git
#     call on this laptop on 2026-08-05 — MUST fall back to the old basename
#     behaviour. A broken git silently relabelling real project work as `scratch`
#     is worse than the bug being fixed here.
#  3. The fallback chain never yields an empty PROJECT.
#
# One divergence from the hook, and it is intentional: the hook additionally
# strips a `/.claude/worktrees/...` suffix off its cwd before asking git, because
# it must still name the repo when git is unavailable. Here that stripping is
# redundant — --git-common-dir already resolves a linked worktree to the main
# repo — and adding it would mean a second, differently-shaped copy of the same
# idea. Keep this one function as the only implementation on this side.
#
# Callers use `set -euo pipefail`, so every git invocation is written so a
# non-zero exit is captured rather than aborting the script.

gc_resolve_project() {
    local dir="${1:-$PWD}"
    local repo_name="" git_common="" git_rc=0

    if command -v git >/dev/null 2>&1 && [ -n "$dir" ]; then
        git_common=$(git -C "$dir" rev-parse --path-format=absolute \
                         --git-common-dir 2>/dev/null) || git_rc=$?
        if [ "$git_rc" -eq 0 ] && [ -n "$git_common" ]; then
            repo_name=$(basename "$(dirname "$git_common")")
        elif [ "$git_rc" -eq 128 ]; then
            repo_name="scratch"
        fi
    fi

    if [ -z "$repo_name" ]; then
        repo_name=$(basename "$dir" 2>/dev/null)
    fi
    if [ -z "$repo_name" ]; then
        repo_name="unknown"
    fi

    printf '%s' "$repo_name"
}
