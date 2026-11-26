#!/bin/bash
# PreToolUse hook: block Claude from reading secrets.
# Exit 0 = allow, exit 2 = block (shows stderr message to Claude).
#
# Allowed: .env.example, .env.template, .env.sample, .env.tpl (templates / op:// refs,
#          committed to git — no real secret values). Matched as EXACT lowercased
#          basenames, so variants (.env.tpl.bak, .env.tpl~, .env.tpl.swp) stay blocked.
# Blocked: .env, .env.local, .env.production, .env.development, synthesizer.env,
#          *.key, *.pem, credentials*, ~/secrets/* and ~/.secrets/* (contents only — listing OK)
# Symlinks: resolved before matching — an allowlisted name pointing at a real
#           secret (e.g. .env.tpl -> .env.local) is blocked on the resolved target.
#
# Principle for the Bash branch: block commands whose OUTPUT could carry a secret
# value into the conversation. Commands that only write secrets to places the hook
# already refuses to read (a .env file, the 1Password vault, a child process's
# environment) are allowed.
#
# Quotes: the hook does not parse the shell. A reader verb, an op command or the
# name of a secret file counts wherever it is written, inside quotes or not, so
# a quoted commit message or note that mentions one is blocked. Pass such text
# by heredoc (heredoc bodies are not scanned) or from a file. Every word is also
# expanded as a wildcard, quoted or not, with one exception: a bare .* inside
# a quoted search pattern, which is not a file list (see mark_quoted_stars).
#
# Matching: every `grep -q` reads its text from a here-string (`<<<"$CMD"`),
# never from `echo "$CMD" | grep -q`. Under pipefail, grep -q exiting at an
# early match kills the echo, and the SIGPIPE status read as "no match": a
# secret read followed by ~200 KB of filler was allowed (fixed 2026-11-26).
# Known limit: a here-string needs a temp file (bash 3.2 always, bash 5 above
# the pipe size), so an unwritable $TMPDIR makes the check fail open, as a
# grep error already does.

set -euo pipefail

INPUT="$(cat)"
TOOL="$(echo "$INPUT" | jq -r '.tool_name // empty')"

# --- helpers ---

# Resolve a symlink chain to its real target. Portable (iterative plain
# `readlink`, one level at a time) because macOS `readlink -f` is unreliable
# on older versions. Non-symlinks / missing paths return unchanged.
resolve_path() {
  local p="$1" count=0 target
  while [ -L "$p" ] && [ "$count" -lt 40 ]; do
    target="$(readlink "$p" 2>/dev/null || true)"
    [ -z "$target" ] && break
    case "$target" in
      /*) p="$target" ;;
      *)  p="$(dirname "$p")/$target" ;;
    esac
    count=$((count + 1))
  done
  printf '%s' "$p"
}

# Classify a single basename: return 0 (secret) or 1 (allowed/neutral).
# Lowercases first so APFS case-insensitivity (.env.TPL) is handled. The
# allowlist matches EXACT basenames only, so variants like .env.tpl.bak,
# .env.tpl~, .env.tpl.swp fall through to the .env.* block (fail-safe).
name_is_secret() {
  local b
  b="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"

  # Allow safe env templates (no real secrets, committed to git)
  case "$b" in
    .env.example|.env.template|.env.sample|.env.tpl) return 1 ;;
  esac

  # Block .env files
  case "$b" in
    .env|.env.*|synthesizer.env) return 0 ;;
  esac

  # Block key/credential files
  case "$b" in
    *.pem|*.key) return 0 ;;
    credentials|credentials.*) return 0 ;;
  esac

  return 1
}

# Block if EITHER the literal name OR the symlink-resolved name is a secret —
# so an allowlisted name (e.g. .env.tpl) symlinked to .env.local can't bypass.
is_secret_file() {
  local f="$1" real
  if name_is_secret "$(basename "$f")"; then return 0; fi
  real="$(resolve_path "$f")"
  if [ "$real" != "$f" ] && name_is_secret "$(basename "$real")"; then return 0; fi
  return 1
}

is_in_secrets_dir() {
  local f="$1" p
  # Check both the literal path and the symlink-resolved target.
  for p in "$f" "$(resolve_path "$f")"; do
    # Block both ~/secrets/ and ~/.secrets/ (contents only, listing OK)
    case "$p" in
      "$HOME/secrets"|"$HOME/secrets"/*) return 0 ;;
      "$HOME/.secrets"|"$HOME/.secrets"/*) return 0 ;;
      ~/secrets|~/secrets/*) return 0 ;;
      ~/.secrets|~/.secrets/*) return 0 ;;
    esac
  done
  return 1
}

# Remove heredoc bodies (<<TAG ... TAG, <<'TAG', <<"TAG", <<-TAG) from a command
# string so that FILE CONTENTS being written are not mistaken for file paths
# being read. Only the shell syntax outside the heredoc is matched afterwards.
strip_heredocs() {
  awk '
    BEGIN { skip = 0; tag = "" }
    {
      if (skip) {
        line = $0; sub(/^[ \t]+/, "", line)
        if (line == tag) { skip = 0; tag = "" }
        next
      }
      line = $0; gsub(/<<</, "###", line)     # a here-string is not a heredoc
      if (match(line, /<<-?[ \t]*['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/)) {
        t = substr($0, RSTART, RLENGTH)
        sub(/^<<-?[ \t]*/, "", t); gsub(/['"'"'"]/, "", t)
        tag = t; skip = 1
        print substr($0, 1, RSTART - 1)
        next
      }
      print
    }
  '
}

# The reader verbs: commands whose output can carry a file's contents.
VERBS='cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|xxd|strings|base64|od|hexdump|cut|tr|sort|uniq|wc|python3?|node|ruby|perl'

# Mark every * inside a quoted string that reads as a search pattern (as the
# byte \001). Reads the command on stdin. A quoted string is NOT a pattern, and
# keeps its stars, when it holds a reader verb (it may be a command something
# runs: awk system("cat .*")), is .* and nothing else (a whole argument: a
# file list for ssh host cat '.*'), or starts with a colon (a git pathspec).
# Pairs quote marks the way the shell does in the plain cases and gives up on
# the rest, printing the input unchanged: a command that hands words to a
# second shell (RUNNER), a # , backslash, backtick or $'...' outside quotes,
# a $( ${ or backtick inside double quotes, quotes that do not balance.
# Giving up costs nothing but the exception in words_to_expand.
RUNNER='(sh|bash|zsh|dash|ksh|csh|tcsh|fish|eval|ssh|mosh|su|watch|osascript|tmux|screen|parallel|docker|kubectl|[$][{]?SHELL[}]?)'
mark_quoted_stars() {
  LC_ALL=C awk -v sq="'" -v dq='"' -v verb="(^|[^A-Za-z0-9_])($VERBS)[ \t\n]" \
      -v runner="(^|[^A-Za-z0-9_.-])$RUNNER[ \t\n]" '
    { all = all $0 "\n" }
    END {
      if (all ~ runner) { printf "%s", all; exit }
      n = length(all); q = ""; out = ""; seg = ""
      for (i = 1; i <= n; i++) {
        c = substr(all, i, 1); d = substr(all, i + 1, 1)
        if (q == "") {
          if (c == "\\" || c == "`" || c == "#" || (c == "$" && d == sq)) { printf "%s", all; exit }
          if (c == sq || c == dq) { q = c; seg = "" }
          out = out c; continue
        }
        if (q == dq && c == "\\") { seg = seg c d; i++; continue }
        if (q == dq && (c == "`" || (c == "$" && (d == "(" || d == "{")))) { printf "%s", all; exit }
        if (c != q) { seg = seg c; continue }
        if (seg !~ /^[ \t\n]*\.\*\??[ \t\n]*$/ && seg !~ /^:/ && seg !~ verb) gsub(/\*/, "\001", seg)
        out = out seg c; q = ""
      }
      printf "%s", (q == "") ? out : all
    }'
}

# The words of a command that may be expanded as wildcards, one per line: all
# of them, as the hook always did, except a bare .* (or .*?) that
# mark_quoted_stars marked. "(a|b).*" and "for .* in x" are search patterns;
# expanded here, that .* would name the env file and block every such search.
# Nothing else is exempt: a quoted .e* still expands, since a tool or a second
# shell may expand it too.
words_to_expand() {
  printf '%s\n' "$1" | mark_quoted_stars | tr '"'"'"'`|;&()<>' '          ' | tr -s ' \t' '\n\n' \
    | { grep -vxE $'\\.\001\\??' || true; } | tr '\001' '*'
}

# Classify one word from the command line: return 0 if it names a secret file.
# Uses the same classifier as the file-tool branch, so the two agree: .env.tpl
# is allowed here exactly as it is for Read/Edit/Write.
word_names_secret() {
  local tok="$1"
  case "$tok" in
    *.env*|*.pem|*.key|credentials*|*/credentials*) ;;
    *) return 1 ;;
  esac
  tok="${tok%%=*}"
  [ -z "$tok" ] && return 1
  # --env-file=.env.tpl and friends are classified by the flag loop below
  case "$tok" in --*) return 1 ;; esac
  if is_secret_file "$tok"; then return 0; fi
  # A name spelled with wildcards (.env*, *.env.*) names the file it wraps.
  case "$tok" in
    *[*?]*) is_secret_file "${tok//[*?]/}" ;;
    *) return 1 ;;
  esac
}

# Flags whose argument is a file pattern the tool matches itself (find -name,
# grep --include, rg -g, a git pathspec after --). A quoted wildcard there
# selects files, so it is tested against sample secret names.
is_pattern_flag() {
  case "${1%=}" in
    -name|-iname|-path|-ipath|-wholename|-iwholename|--include|-g|--glob|--iglob|--) return 0 ;;
  esac
  return 1
}
pattern_selects_secret() {
  local pat="$1" n
  # A catch-all (*, */*) says no more than leaving the flag out, and a
  # recursive search with no pattern is not blocked either.
  [ -z "${pat//[*?\/]/}" ] && return 1
  # Bare names for -name and --include, paths for -path and pathspecs: a
  # pattern like */node_modules/* matches neither.
  for n in .env .env.local x.pem x.key credentials; do
    # shellcheck disable=SC2254
    case "$n" in $pat) return 0 ;; esac
    # shellcheck disable=SC2254
    case "./$n" in $pat) return 0 ;; esac
    # shellcheck disable=SC2254
    case "d/$n" in $pat) return 0 ;; esac
  done
  return 1
}

# Does the command name a secret file?
cmd_mentions_secret_file() {
  local cmd="$1" tok prev="" found=1
  # Names as written, quoted or not. Read twice: with quote marks turned into
  # spaces, and with them deleted, since .e"nv" is one word to the shell. No
  # wildcard expansion here: a quoted .* is a pattern, not a file list.
  set -f
  # shellcheck disable=SC2086
  for tok in $(printf '%s\n%s' "$(printf '%s' "$cmd" | tr '"'"'"'`' '   ')" "$(printf '%s' "$cmd" | tr -d '"'"'"'"'"'"'"')" | tr '|;&()<>' '       ' | tr -s ' ' '\n'); do
    if word_names_secret "$tok"; then found=0; break; fi
    if is_pattern_flag "$prev" && pattern_selects_secret "$tok"; then found=0; break; fi
    prev="$tok"
  done
  # --flag=VALUE forms (e.g. --env-file=.env.local): classify the value part
  if [ "$found" -ne 0 ]; then
    for tok in $(printf '%s' "$cmd" | tr '"'"'"'' '  ' | grep -oE -- '--?[A-Za-z-]+=[^ ]+' || true); do
      if word_names_secret "${tok#*=}"; then found=0; break; fi
      if is_pattern_flag "${tok%%=*}" && pattern_selects_secret "${tok#*=}"; then found=0; break; fi
    done
  fi
  set +f
  [ "$found" -eq 0 ] && return 0
  # Every word again, expanded as a wildcard: `cat .e*` names .env. The hook
  # runs in the session's directory, so this matches what the shell would do.
  # shellcheck disable=SC2046
  for tok in $(words_to_expand "$cmd"); do
    if word_names_secret "$tok"; then return 0; fi
  done
  return 1
}

block() {
  echo "BLOCKED: $1 — ask the user to handle this file directly." >&2
  if [ "$TOOL" = "Bash" ]; then
    echo "If the match is only words inside a quoted message or note, pass that text by heredoc or from a file; the hook does not read heredoc bodies." >&2
  fi
  exit 2
}

# --- tool checks ---

case "$TOOL" in
  Read|Edit|Write)
    FILE="$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')"
    if [ -n "$FILE" ] && is_secret_file "$FILE"; then
      block "Access to secret file: $(basename "$FILE")"
    fi
    if [ -n "$FILE" ] && is_in_secrets_dir "$FILE"; then
      block "Access to file in ~/secrets/ — ask the user to handle it directly"
    fi
    ;;

  Grep)
    TARGET="$(echo "$INPUT" | jq -r '.tool_input.path // empty')"
    GLOB="$(echo "$INPUT" | jq -r '.tool_input.glob // empty')"
    # Block if grepping inside a specific .env file
    if [ -n "$TARGET" ] && [ ! -d "$TARGET" ] && is_secret_file "$TARGET"; then
      block "Grep inside secret file: $(basename "$TARGET")"
    fi
    # Block if grepping inside ~/secrets/
    if [ -n "$TARGET" ] && is_in_secrets_dir "$TARGET"; then
      block "Grep inside ~/secrets/ — ask the user to handle it directly"
    fi
    # Block if glob pattern targets .env files
    if [[ "$GLOB" == *".env"* ]] && [[ "$GLOB" != *".env.example"* ]] && [[ "$GLOB" != *".env.template"* ]] && [[ "$GLOB" != *".env.tpl"* ]]; then
      block "Grep glob targets .env files"
    fi
    ;;

  Glob)
    PATTERN="$(echo "$INPUT" | jq -r '.tool_input.pattern // empty')"
    if [[ "$PATTERN" == *".env"* ]] && [[ "$PATTERN" != *".env.example"* ]] && [[ "$PATTERN" != *".env.tpl"* ]]; then
      block "Glob pattern targets .env files"
    fi
    ;;

  Bash)
    RAW="$(echo "$INPUT" | jq -r '.tool_input.command // empty')"
    # Match on the shell syntax only; heredoc bodies are file contents, not paths.
    CMD="$(printf '%s\n' "$RAW" | strip_heredocs)"

    # --- secret files on the command line ---
    # A reader verb anywhere + a secret-classified file token anywhere = block.
    # The verb may follow a quote mark or backtick (sh -c "cat x"), a backslash
    # (\cat), a path (/bin/cat) or a shell-escape bang. The "." verb (source)
    # may follow a quote mark but not a slash: "/." ends a path.
    # Writers (cp, mv, touch, test -f, op inject -o) with no reader verb pass.
    READER='((^|[|;&(!\\/"`'"'"']|\s)('"$VERBS"')|(^|[|;&("`'"'"']|\s)\.)\s'
    if grep -qE "$READER" <<<"$CMD" 2>/dev/null && cmd_mentions_secret_file "$CMD"; then
      block "Shell command reads a secret file"
    fi
    # Redirect-in from a secret file: < .env, < .env.local, <.env
    # A quoted <.*> is a pattern, not a redirect. Stops at ) for $(<file).
    for tok in $(printf '%s\n' "$CMD" | mark_quoted_stars | grep -oE '<\s*[^ <>|;&)]+' | sed -E 's/^<\s*//' | { grep -vE $'^\\.\001\\??[\"\']?$' || true; } | tr '\001' '*' || true); do
      tok="${tok//[\"\']/}"
      if is_secret_file "$tok"; then block "Shell command reads a secret file via redirect"; fi
    done

    # --- ~/secrets and ~/.secrets: contents never, listing OK ---
    if grep -qE "$READER"'.*(~|\$HOME|\$\{HOME\}|/Users/[^/]+)/\.?secrets' <<<"$CMD" 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi

    # --- 1Password CLI ---
    # Still blocked, always: anything whose purpose is to PRINT a secret value.
    if grep -qE '\bop\s+read\b' <<<"$CMD" 2>/dev/null; then
      block "op read prints a secret value — suggest the user run it manually"
    fi
    if grep -qE '\bop\s+item\s+(get|delete)\b' <<<"$CMD" 2>/dev/null; then
      block "op item get/delete — suggest the user run it manually"
    fi
    if grep -qE '\bop\b.*--reveal' <<<"$CMD" 2>/dev/null; then
      block "op --reveal prints secret values"
    fi
    if grep -qE '\bop\s+item\s+(create|edit)\b.*--format' <<<"$CMD" 2>/dev/null; then
      block "op item create/edit with --format prints field values"
    fi
    # op inject: allowed only when writing to a file (-o / --out-file). Without
    # it, the materialized secrets go to stdout.
    if grep -qE '\bop\s+inject\b' <<<"$CMD" 2>/dev/null; then
      if ! grep -qE '\bop\s+inject\b[^|;&]*(\s-o\s|--out-file[ =])' <<<"$CMD" 2>/dev/null; then
        block "op inject without -o would print secrets — add -o <file>"
      fi
    fi
    # op run: secrets go into the child's environment, not the transcript. Block
    # only if the child command obviously dumps the environment.
    if grep -qE '\bop\s+run\b' <<<"$CMD" 2>/dev/null; then
      CHILD="${CMD#*op run}"
      CHILD="${CHILD#* -- }"
      if grep -qE '(^|[|;&(]|\s)(env|printenv)(\s|$)|\bexport\s+-p\b|\bdeclare\s+-[xp]\b|\becho\b[^|;&]*\$' <<<"$CHILD" 2>/dev/null; then
        block "op run child command would print environment variables"
      fi
    fi
    ;;
esac

exit 0
