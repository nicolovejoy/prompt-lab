#!/bin/bash
# session-context.sh — print readup-style session context as plain text.
#
# Extracted from workflow/hooks/session-start.sh so both the Claude Code
# SessionStart hook (which JSON-wraps this output) and any agent with no
# hook mechanism (Codex) can get the same context. Pure text out, no JSON.
#
# Silent (no output) if cwd doesn't look like a real project — avoids noise
# on quick launches in ~ or /tmp. Does NOT register a session row or run
# `git pull` — those stay behind the explicit /readup command.

set -u

CWD="$(pwd)"
HOME_SRC="$HOME/src"

# Guard: only run in real project dirs under ~/src/ that are git repos
case "$CWD" in
  "$HOME_SRC"/*) ;;
  *) exit 0 ;;
esac
git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

PROJECT="$(basename "$CWD")"
TODAY="$(date "+%A, %B %-d, %Y")"

# Machine label, derived from hostname. Update the case below if you rename a host.
HOSTNAME_SHORT="$(hostname -s)"
case "$HOSTNAME_SHORT" in
  *[Mm]ini*) MACHINE="mini" ;;
  *[Mm][Bb][Pp]*|*[Mm]ac[Bb]ook*) MACHINE="laptop" ;;
  *) MACHINE="$HOSTNAME_SHORT" ;;
esac

# Last ended session for this project
LAST_SUMMARY="$(sqlite3 "$HOME/.claude/prompt-history.db" \
  "SELECT substr(summary, 1, 400) || '|' || ended_at FROM sessions WHERE project='$PROJECT' AND ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1;" 2>/dev/null)"

# Recent commits + working tree
RECENT_COMMITS="$(git -C "$CWD" log --oneline -5 2>/dev/null)"
DIRTY="$(git -C "$CWD" status --short 2>/dev/null)"

# Bulletin headlines (skip silently if file missing)
BULLETIN="$(grep -E '^## ' "$HOME/src/prompt-lab/BULLETIN.md" 2>/dev/null | head -5)"

# Assemble context
CTX="Session-start context:

Today: $TODAY
Machine: $MACHINE
Project: $PROJECT
Working dir: $CWD
"

if [ -n "$LAST_SUMMARY" ]; then
  CTX+="
Last session: $LAST_SUMMARY
"
fi

if [ -n "$RECENT_COMMITS" ]; then
  CTX+="
Recent commits:
$RECENT_COMMITS
"
fi

if [ -n "$DIRTY" ]; then
  CTX+="
Uncommitted:
$DIRTY
"
fi

if [ -n "$BULLETIN" ]; then
  CTX+="
Cross-project bulletin (/bulletin for details):
$BULLETIN
"
fi

# --- Cross-repo handoff channel (issue #7) ------------------------------------
HANDOFF_DIR="${HANDOFF_DIR:-$HOME/src/.handoff}"
HANDOFF_BIN="${HANDOFF_BIN:-$HOME/.claude/bin/handoff.sh}"
# Headline-only injection (2026-09-13). Full `## Active` bodies were 193 KB /
# ~48K tokens across 14 channels at every session start — 99% of the hook's
# output — because entries are appended far more often than they are archived.
# Inject the dated `### ` headlines newer than HANDOFF_HEADLINE_DAYS plus a
# count; the body is one `cat` away when a headline matters.
HANDOFF_HEADLINE_DAYS="${HANDOFF_HEADLINE_DAYS:-30}"
if [ -d "$HANDOFF_DIR/.git" ]; then
  # Pull BEFORE scanning. Gating the pull on having already matched a file is a
  # chicken-and-egg: a channel created by the other side does not exist in this
  # clone yet, so it can never match, so the pull never runs, so the file never
  # arrives. Hit for real 2026-08-21 — prompt-lab opened span-prompt-lab.md and
  # pushed it; the SPAN agent's hook reported "no span-* file exists, nothing
  # waiting for you" while the file sat on origin. That is this repo's signature
  # failure shape wearing a new hat: the check never looked, and reported
  # nothing found. Best-effort and time-boxed (handoff.sh pull always exits 0
  # and never blocks), so the cost of doing it unconditionally is a short
  # network call in repos that turn out to have no channel.
  [ -x "$HANDOFF_BIN" ] && "$HANDOFF_BIN" pull >/dev/null 2>&1
  MATCHED=""
  for f in "$HANDOFF_DIR"/*-*.md; do
    [ -e "$f" ] || continue
    # Case-sensitive by design: PROJECT is the cwd basename, so a repo living at
    # ~/src/SPAN matches `repos: [SPAN, …]` and not `[span, …]`.
    if head -5 "$f" | grep '^repos:' | grep -qw "$PROJECT"; then
      MATCHED="$MATCHED $f"
    fi
  done
  if [ -n "$MATCHED" ]; then
    HANDOFF_CUTOFF="$(date -v-"${HANDOFF_HEADLINE_DAYS}"d '+%Y-%m-%d' 2>/dev/null \
      || date -d "${HANDOFF_HEADLINE_DAYS} days ago" '+%Y-%m-%d')"
    for f in $MATCHED; do
      # Only `### ` lines inside `## Active`; date is the first token after `### `.
      HEADLINES="$(awk '/^## Active/{a=1;next} /^## /{a=0} a && /^### /' "$f")"
      [ -n "$HEADLINES" ] || continue
      TOTAL="$(printf '%s\n' "$HEADLINES" | wc -l | tr -d ' ')"
      FRESH="$(printf '%s\n' "$HEADLINES" | awk -v c="$HANDOFF_CUTOFF" 'substr($0,5,10) >= c')"
      FRESH_N="$(printf '%s' "$FRESH" | grep -c '^### ' || true)"
      CTX+="
Cross-repo handoff — $(basename "$f"): $TOTAL active entries, $FRESH_N newer than ${HANDOFF_HEADLINE_DAYS}d (bodies: cat ~/src/.handoff/$(basename "$f"); reply via 'handoff.sh append'):
"
      [ -n "$FRESH" ] && CTX+="$FRESH
"
    done
  fi
fi

# Turso staleness check. The async sync runs at most once per 8h and only when
# the machine is in use, and it runs AFTER this hook — so a merely-old stamp
# usually means "machine was idle" and the sync is about to catch up (a >24h
# mtime check here warned on exactly that, falsely). Real breakage = attempts
# are happening and failing: the newest log line isn't an ok. Warn only when
# the stamp is ≥48h old AND the most recent logged attempt didn't succeed.
TURSO_STAMP="$HOME/.claude/.turso-last-sync"
TURSO_LOG="$HOME/.claude/.turso-last-sync.log"
if [ -f "$TURSO_STAMP" ] && [ -z "$(find "$TURSO_STAMP" -mmin -2880 2>/dev/null)" ] \
   && [ -f "$TURSO_LOG" ]; then
  TURSO_LAST_LINE="$(tail -1 "$TURSO_LOG" 2>/dev/null)"
  case "$TURSO_LAST_LINE" in
    *" ok: "*) : ;;  # newest attempt succeeded — stale stamp is just idle time
    "") : ;;         # empty log — nothing attempted, nothing to diagnose
    *)
      LAST_SYNC="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "$TURSO_STAMP" 2>/dev/null || stat -c '%y' "$TURSO_STAMP" 2>/dev/null | cut -d. -f1)"
      CTX+="
⚠️ Turso sync last succeeded $LAST_SYNC on this machine and the most recent attempt did NOT succeed: [$TURSO_LAST_LINE] — check ~/.claude/.turso-last-sync.log. The async sync hook retries each session, but it keeps failing.
"
      ;;
  esac
fi

# Neglected custom commands nudge — at most once per 7 days, only if any
# user-installed slash command has gone unused for 30+ days.
NUDGE_STAMP="$HOME/.claude/state/commands-nudge.touch"
NUDGE_FRESH="$(find "$NUDGE_STAMP" -mmin -10080 2>/dev/null)"
if [ -z "$NUDGE_FRESH" ] && [ -d "$HOME/.claude/commands" ]; then
  CUTOFF="$(date -v-30d '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '30 days ago' '+%Y-%m-%d %H:%M:%S')"
  NEGLECTED=""
  for cmd_file in "$HOME/.claude/commands/"*.md; do
    [ -f "$cmd_file" ] || continue
    cmd="$(basename "$cmd_file" .md)"
    case "$cmd" in *.bak.*) continue ;; esac
    last="$(sqlite3 "$HOME/.claude/prompt-history.db" \
      "SELECT MAX(timestamp) FROM prompts WHERE prompt = '/$cmd' OR prompt LIKE '/$cmd %' OR prompt LIKE '/$cmd' || x'0a' || '%';" 2>/dev/null)"
    if [ -z "$last" ] || [ "$last" \< "$CUTOFF" ]; then
      desc="$(awk -F': *' '/^description:/{sub(/^[ \t]+/, "", $2); print $2; exit}' "$cmd_file")"
      [ -z "$desc" ] && desc="(no description)"
      if [ -z "$last" ]; then
        NEGLECTED+="   /$cmd — $desc (never used)
"
      else
        NEGLECTED+="   /$cmd — $desc (last used $last)
"
      fi
    fi
  done
  if [ -n "$NEGLECTED" ]; then
    CTX+="
Custom commands you haven't used in 30+ days (weekly reminder):
$NEGLECTED"
    mkdir -p "$(dirname "$NUDGE_STAMP")"
    touch "$NUDGE_STAMP"
  fi
fi

printf '%s' "$CTX"
