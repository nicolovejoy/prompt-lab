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

# Does the command contain any token whose basename classifies as a secret file?
# Tokens are whitespace- or quote-delimited words that look like paths or names.
# Using the same classifier as the file-tool branch keeps the two in agreement:
# .env.tpl is allowed here exactly as it is for Read/Edit/Write.
cmd_mentions_secret_file() {
  local cmd="$1" tok real
  # shellcheck disable=SC2086
  for tok in $(printf '%s' "$cmd" | tr '"'"'"'|;&()<>' '          ' | tr -s ' ' '\n'); do
    case "$tok" in
      *.env*|*.pem|*.key|credentials*|*/credentials*) ;;
      *) continue ;;
    esac
    tok="${tok%%=*}"            # VAR=.env.local  -> keep the value side below
    [ -z "$tok" ] && continue
    # the token may be the right-hand side of --env-file=.env.tpl
    case "$tok" in --*) continue ;; esac
    if is_secret_file "$tok"; then return 0; fi
  done
  # --flag=VALUE forms (e.g. --env-file=.env.local): classify the value part
  for tok in $(printf '%s' "$cmd" | grep -oE -- '--?[A-Za-z-]+=[^ "'"'"']+' || true); do
    tok="${tok#*=}"
    case "$tok" in *.env*|*.pem|*.key|credentials*) ;; *) continue ;; esac
    if is_secret_file "$tok"; then return 0; fi
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

    # --- secret files on the command line ---
    # A reader verb anywhere + a secret-classified file token anywhere = block.
    # Writers (cp, mv, touch, test -f, op inject -o) with no reader verb pass.
    READER='(^|[|;&(]|\s)(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|xxd|strings|base64|od|hexdump|cut|tr|sort|uniq|wc|python3?|node|ruby|perl|\.)\s'
    if echo "$CMD" | grep -qE "$READER" 2>/dev/null && cmd_mentions_secret_file "$CMD"; then
      block "Shell command reads a secret file"
    fi
    # Redirect-in from a secret file: < .env, < .env.local, <.env
    for tok in $(echo "$CMD" | grep -oE '<\s*[^ <>|;&]+' | sed -E 's/^<\s*//' || true); do
      if is_secret_file "$tok"; then block "Shell command reads a secret file via redirect"; fi
    done

    # --- ~/secrets and ~/.secrets: contents never, listing OK ---
    if echo "$CMD" | grep -qE "$READER"'.*(~|\$HOME|/Users/[^/]+)/\.?secrets' 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi

    # --- 1Password CLI ---
    # Still blocked, always: anything whose purpose is to PRINT a secret value.
    if echo "$CMD" | grep -qE '\bop\s+read\b' 2>/dev/null; then
      block "op read prints a secret value — suggest the user run it manually"
    fi
    if echo "$CMD" | grep -qE '\bop\s+item\s+(get|delete)\b' 2>/dev/null; then
      block "op item get/delete — suggest the user run it manually"
    fi
    if echo "$CMD" | grep -qE '\bop\b.*--reveal' 2>/dev/null; then
      block "op --reveal prints secret values"
    fi
    if echo "$CMD" | grep -qE '\bop\s+item\s+(create|edit)\b.*--format' 2>/dev/null; then
      block "op item create/edit with --format prints field values"
    fi
    # op inject: allowed only when writing to a file (-o / --out-file). Without
    # it, the materialized secrets go to stdout.
    if echo "$CMD" | grep -qE '\bop\s+inject\b' 2>/dev/null; then
      if ! echo "$CMD" | grep -qE '\bop\s+inject\b[^|;&]*(\s-o\s|--out-file[ =])' 2>/dev/null; then
        block "op inject without -o would print secrets — add -o <file>"
      fi
    fi
    # op run: secrets go into the child's environment, not the transcript. Block
    # only if the child command obviously dumps the environment.
    if echo "$CMD" | grep -qE '\bop\s+run\b' 2>/dev/null; then
      CHILD="${CMD#*op run}"
      CHILD="${CHILD#* -- }"
      if echo "$CHILD" | grep -qE '(^|[|;&(]|\s)(env|printenv)(\s|$)|\bexport\s+-p\b|\bdeclare\s+-[xp]\b|\becho\b[^|;&]*\$' 2>/dev/null; then
        block "op run child command would print environment variables"
      fi
    fi
    ;;
esac

exit 0
