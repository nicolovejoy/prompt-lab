#!/bin/bash
# gc-vcs.sh — version-control reads for /handoff, the same for git and Fossil.
#
#   gc-vcs.sh kind                            git | fossil | none
#   gc-vcs.sh status                          "VCS=<kind>", then one line per uncommitted file
#   gc-vcs.sh commits-since "<started_at>"    one "hash|unix-seconds|subject" line per commit
#
# <started_at> is sessions.started_at as stored: "YYYY-MM-DD HH:MM:SS", UTC.
#
# WHY THIS EXISTS
# ---------------
# /handoff used to run `git status` and `git log` itself. In a Fossil checkout
# (ear-worm, 2026-11-20) both fail, so uncommitted work went unreported and every
# session recorded zero commits. "Zero commits is normal" made that look healthy.
#
# EXIT STATUS IS THE CONTRACT
# ---------------------------
# 0 means the answer is complete, and an empty answer is a real "nothing".
# Anything else means the checkout could not be read, with the reason on stderr.
# A caller must report that, never record it as "no commits" or "clean".
#   2 usage, git itself is failing, or the helper beside this script is missing
#   3 Fossil checkout without the fossil command
#   4 the VCS command failed            5 a timeline line could not be parsed
#
# Fossil facts this relies on, checked on 2.28:
#  - `timeline after` reads its time as UTC and prints %d in UTC.
#  - The default limit is 20 lines, so `-n 0` is required or a busy session
#    loses commits with no error.
#  - A multi-line comment is printed on one line.
#  - The last line is a trailer such as "+++ no more data (2) +++".
#  - Hashes are 64 hex characters, not git's 40.

set -uo pipefail

BIN_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"
# shellcheck source=./_gc_project.sh
[ -f "$BIN_DIR/_gc_project.sh" ] && . "$BIN_DIR/_gc_project.sh"
if ! command -v gc_fossil_root >/dev/null 2>&1; then
  # A partial install under ~/.claude/bin. Without the helper a Fossil checkout
  # would come out as `none` with exit 0.
  echo "gc-vcs: $BIN_DIR/_gc_project.sh is missing or broken; the checkout was not read" >&2
  exit 2
fi

# Is there a .git entry in $PWD or any parent?
git_entry_above() {
  local d="$PWD"
  while [ -n "$d" ] && [ "$d" != "/" ] && [ "$d" != "." ]; do
    [ -e "$d/.git" ] && return 0
    d=$(dirname "$d")
  done
  return 1
}

# Sets KIND. Mirrors gc_resolve_project: only git's exit 128 ("not a git
# repository") moves on to Fossil or `none`. A git that fails any other way is an
# error, never a quiet "none". Git also answers 128 for a damaged repository and
# for "dubious ownership", so 128 with a .git entry above is an error too.
detect_kind() {
  local rc=0
  KIND=none
  if command -v git >/dev/null 2>&1; then
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then KIND=git; return 0; fi
    if [ "$rc" -ne 128 ]; then
      echo "gc-vcs: git failed with exit $rc; the checkout was not read" >&2
      return 2
    fi
    if git_entry_above; then
      echo "gc-vcs: a .git entry exists here or above, but git cannot read it (exit 128); the checkout was not read" >&2
      return 2
    fi
  fi
  if gc_fossil_root "$PWD" >/dev/null; then KIND=fossil; fi
  return 0
}

need_fossil() {
  command -v fossil >/dev/null 2>&1 && return 0
  echo "gc-vcs: this is a Fossil checkout but the fossil command is not installed; the checkout was not read" >&2
  exit 3
}

CMD="${1:-}"
shift || true

case "$CMD" in
  kind)
    detect_kind || exit $?
    echo "$KIND"
    ;;

  status)
    detect_kind || exit $?
    case "$KIND" in
      git)
        out="$(git status --short 2>&1)" || { echo "gc-vcs: git status failed: $out" >&2; exit 4; }
        ;;
      fossil)
        need_fossil
        # --differ adds untracked files (EXTRA); --dotfiles includes dotfiles among them.
        out="$(fossil changes --differ --dotfiles 2>&1)" || { echo "gc-vcs: fossil changes failed: $out" >&2; exit 4; }
        ;;
      *) out="" ;;
    esac
    echo "VCS=$KIND"
    # `if`, not `[ … ] && …`: as the last command that form exits 1 on an empty
    # answer, and a non-zero exit here means "could not read".
    if [ -n "$out" ]; then printf '%s\n' "$out"; fi
    ;;

  commits-since)
    since="${1:-}"
    if ! printf '%s' "$since" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$'; then
      echo 'usage: gc-vcs.sh commits-since "YYYY-MM-DD HH:MM:SS"   (UTC, as stored in sessions.started_at)' >&2
      exit 2
    fi
    detect_kind || exit $?
    case "$KIND" in
      git)
        # A repository with no commits yet has nothing to list, and `git log`
        # would exit 128 there.
        git rev-parse --verify -q HEAD >/dev/null 2>&1 || exit 0
        out="$(git log --since="${since}Z" --format='%H|%ct|%s' 2>&1)" || { echo "gc-vcs: git log failed: $out" >&2; exit 4; }
        if [ -n "$out" ]; then printf '%s\n' "$out"; fi
        ;;
      fossil)
        need_fossil
        out="$(fossil timeline after "$since" -n 0 -t ci -F '%H|%d|%c' 2>&1)" || { echo "gc-vcs: fossil timeline failed: $out" >&2; exit 4; }
        printf '%s\n' "$out" | python3 -c '
import calendar, re, sys, time

row = re.compile(r"^([0-9a-f]{40,64})\|(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\|(.*)$")
trailer = re.compile(r"^(\+\+\+|---) .* (\+\+\+|---)$")
unreadable = 0
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line or trailer.match(line):
        continue
    m = row.match(line)
    if not m:
        unreadable += 1
        print("gc-vcs: unreadable timeline line: " + line, file=sys.stderr)
        continue
    stamp = calendar.timegm(time.strptime(m.group(2), "%Y-%m-%d %H:%M:%S"))
    print(f"{m.group(1)}|{stamp}|{m.group(3)}")
sys.exit(5 if unreadable else 0)
' || exit $?
        ;;
      *) : ;;  # not a checkout: there are no commits to capture
    esac
    ;;

  *)
    echo 'usage: gc-vcs.sh {kind|status|commits-since "<started_at>"}' >&2
    exit 2
    ;;
esac
