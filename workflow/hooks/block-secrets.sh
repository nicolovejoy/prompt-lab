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
# Quoting rule for the Bash branch: text inside quotes is words, not commands,
# unless the command hands that text to a shell or an interpreter (EXECUTOR and
# INLINE below). So a commit message that mentions a reader command is not a
# read, and a quoted .* is a pattern, not a file list. Three things inside
# quotes still count: a secret file name, a $(...) or backtick command, and a
# $VARIABLE. Quotes that do not balance fall back to the strict reading, where
# everything is a command.

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
      if (match($0, /<<-?[ \t]*['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/)) {
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

# Blank out the quoted text a shell treats as data, keeping what it would run
# or expand. Single quotes: all data. Double quotes: data, except $(...),
# backticks and $VAR / ${...}. Quote marks themselves become spaces. Exit 3 if
# the quotes or the $( ) do not balance, so the caller can fall back to strict.
mask_quoted() {
  awk -v sq="'" -v dq='"' '
    function push(s) { sp++; st[sp] = s; dep[sp] = 0 }
    BEGIN { sp = 0; push("c") }   # c code, s single-quoted, d double-quoted,
    {                             # p $( ) inside d, b backticks inside d
      n = length($0); out = ""
      for (i = 1; i <= n; i++) {
        ch = substr($0, i, 1); nx = substr($0, i + 1, 1); t = st[sp]
        if (t == "s") { if (ch == sq) sp--; out = out " "; continue }
        if (ch == "\\") { out = out ((t == "d") ? "  " : " " nx); i++; continue }
        if (t == "d") {
          if (ch == dq) { sp--; out = out " "; continue }
          if (ch == "$" && nx == "(") { push("p"); out = out "$("; i++; continue }
          if (ch == "`") { push("b"); out = out " "; continue }
          if (ch == "$" && nx == "{") {
            j = index(substr($0, i), "}"); if (j == 0) j = n - i + 1
            seg = substr($0, i, j); gsub("[`" dq sq "]", " ", seg)
            out = out seg; i += j - 1; continue
          }
          if (ch == "$" && match(substr($0, i + 1), /^[A-Za-z_][A-Za-z0-9_]*/)) {
            out = out substr($0, i, RLENGTH + 1); i += RLENGTH; continue
          }
          out = out ((ch == "$") ? "$" : " "); continue
        }
        if (ch == sq) { push("s"); out = out " "; continue }
        if (ch == dq) { push("d"); out = out " "; continue }
        if (ch == "`") { if (t == "b") sp--; out = out " "; continue }
        if (t == "p") {
          if (ch == "(") dep[sp]++
          else if (ch == ")") {
            if (dep[sp] == 0) { sp--; out = out ")"; continue }
            dep[sp]--
          }
        }
        out = out ch
      }
      print out
    }
    END { if (sp != 1) exit 3 }
  '
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
# grep --include, rg -g). There a quoted wildcard selects files, so it is
# tested against sample secret names instead of being read as pattern text.
is_pattern_flag() {
  case "${1%=}" in
    -name|-iname|-path|-ipath|-wholename|-iwholename|--include|-g|--glob|--iglob) return 0 ;;
  esac
  return 1
}
pattern_selects_secret() {
  local pat="${1##*/}" n
  for n in .env .env.local x.pem x.key credentials; do
    # shellcheck disable=SC2254
    case "$n" in $pat) return 0 ;; esac
  done
  return 1
}

# Does the command name a secret file? $1 is the command with every quote mark
# turned into a space (all text visible); $2 is the code view (see mask_quoted).
cmd_mentions_secret_file() {
  local flat="$1" code="$2" tok prev="" found=1
  # Names written out anywhere, quoted or not. No wildcard expansion: a quoted
  # .* is a pattern, and expanding it here would turn it into .env.
  set -f
  # shellcheck disable=SC2086
  for tok in $(printf '%s' "$flat" | tr '|;&()<>' '       ' | tr -s ' ' '\n'); do
    if word_names_secret "$tok"; then found=0; break; fi
    if is_pattern_flag "$prev" && pattern_selects_secret "$tok"; then found=0; break; fi
    prev="$tok"
  done
  # --flag=VALUE forms (e.g. --env-file=.env.local): classify the value part
  if [ "$found" -ne 0 ]; then
    for tok in $(printf '%s' "$flat" | grep -oE -- '--?[A-Za-z-]+=[^ ]+' || true); do
      if word_names_secret "${tok#*=}"; then found=0; break; fi
      if is_pattern_flag "${tok%%=*}" && pattern_selects_secret "${tok#*=}"; then found=0; break; fi
    done
  fi
  set +f
  [ "$found" -eq 0 ] && return 0
  # Unquoted words, expanded as the shell would expand them: `cat .e*` names
  # .env. The hook runs in the session's directory, so the expansion matches.
  # shellcheck disable=SC2086
  for tok in $(printf '%s' "$code" | tr '"'"'"'`|;&()<>' '          ' | tr -s ' ' '\n'); do
    if word_names_secret "$tok"; then return 0; fi
  done
  return 1
}

block() {
  echo "BLOCKED: $1 — ask the user to handle this file directly." >&2
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

    # Two views of the command. FLAT shows all of it, quote marks turned into
    # spaces. CODE shows only what the shell runs or expands. Names of secret
    # files are looked for in FLAT; command verbs (cat, op, env) in CODE.
    FLAT="$(printf '%s\n' "$CMD" | tr '"'"'"'`' '   ')"
    # Commands that run a string as shell code. With one of these present,
    # quoted text is a command, so CODE is all of it. A missing name here is a
    # miss, so keep the list generous.
    EXECUTOR='(^|[^A-Za-z0-9_.-])(sh|bash|zsh|dash|ksh|csh|tcsh|fish|SHELL|eval|ssh|mosh|su|osascript|watch|script|expect|parallel|tmux|screen|trap)($|[^A-Za-z0-9_./-])'
    # An interpreter given inline code (python3 -c, node -e, perl -ne, php -r).
    INLINE='(^|[^A-Za-z0-9_.-])(python[0-9.]*|node|ruby|perl|php)[[:space:]](.*[[:space:]])?-(c|e|ne|pe|r|-eval)([[:space:]]|$)'
    if CODE="$(printf '%s\n' "$CMD" | mask_quoted)" && ! printf '%s\n' "$CODE" | grep -qE "$EXECUTOR|$INLINE"; then
      :
    else
      CODE="$FLAT"   # strict: a shell is handed a string, or the quotes do not balance
    fi

    # --- secret files on the command line ---
    # A reader verb in the code + a secret-classified file name anywhere = block.
    # Writers (cp, mv, touch, test -f, op inject -o) with no reader verb pass.
    READER='(^|[|;&(]|\s)(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|xxd|strings|base64|od|hexdump|cut|tr|sort|uniq|wc|python3?|node|ruby|perl|\.)\s'
    READS=0
    if printf '%s\n' "$CODE" | grep -qE "$READER" 2>/dev/null; then READS=1; fi
    if [ "$READS" -eq 1 ] && cmd_mentions_secret_file "$FLAT" "$CODE"; then
      block "Shell command reads a secret file"
    fi
    # Redirect-in from a secret file: < .env, < .env.local, <.env
    for tok in $(printf '%s\n' "$CODE" | grep -oE '<\s*[^ <>|;&)]+' | sed -E 's/^<\s*//' || true); do
      if is_secret_file "$tok"; then block "Shell command reads a secret file via redirect"; fi
    done

    # --- ~/secrets and ~/.secrets: contents never, listing OK ---
    # The reader must be real code; the path may sit inside quotes.
    if [ "$READS" -eq 1 ] && printf '%s\n' "$FLAT" | grep -qE "$READER"'.*(~|\$HOME|/Users/[^/]+)/\.?secrets' 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi

    # --- 1Password CLI ---
    # Still blocked, always: anything whose purpose is to PRINT a secret value.
    if printf '%s\n' "$CODE" | grep -qE '\bop\s+read\b' 2>/dev/null; then
      block "op read prints a secret value — suggest the user run it manually"
    fi
    if printf '%s\n' "$CODE" | grep -qE '\bop\s+item\s+(get|delete)\b' 2>/dev/null; then
      block "op item get/delete — suggest the user run it manually"
    fi
    if printf '%s\n' "$CODE" | grep -qE '\bop\b.*--reveal' 2>/dev/null; then
      block "op --reveal prints secret values"
    fi
    if printf '%s\n' "$CODE" | grep -qE '\bop\s+item\s+(create|edit)\b.*--format' 2>/dev/null; then
      block "op item create/edit with --format prints field values"
    fi
    # op inject: allowed only when writing to a file (-o / --out-file). Without
    # it, the materialized secrets go to stdout.
    if printf '%s\n' "$CODE" | grep -qE '\bop\s+inject\b' 2>/dev/null; then
      if ! printf '%s\n' "$CODE" | grep -qE '\bop\s+inject\b[^|;&]*(\s-o\s|--out-file[ =])' 2>/dev/null; then
        block "op inject without -o would print secrets — add -o <file>"
      fi
    fi
    # op run: secrets go into the child's environment, not the transcript. Block
    # only if the child command obviously dumps the environment.
    if printf '%s\n' "$CODE" | grep -qE '\bop\s+run\b' 2>/dev/null; then
      CHILD="${CODE#*op run}"
      CHILD="${CHILD#* -- }"
      if printf '%s\n' "$CHILD" | grep -qE '(^|[|;&(]|\s)(env|printenv)(\s|$)|\bexport\s+-p\b|\bdeclare\s+-[xp]\b|\becho\b[^|;&]*\$' 2>/dev/null; then
        block "op run child command would print environment variables"
      fi
    fi
    ;;
esac

exit 0
