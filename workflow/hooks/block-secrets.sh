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
    if [[ "$GLOB" == *".env"* ]] && [[ "$GLOB" != *".env.example"* ]] && [[ "$GLOB" != *".env.template"* ]]; then
      block "Grep glob targets .env files"
    fi
    ;;

  Glob)
    PATTERN="$(echo "$INPUT" | jq -r '.tool_input.pattern // empty')"
    if [[ "$PATTERN" == *".env"* ]] && [[ "$PATTERN" != *".env.example"* ]]; then
      block "Glob pattern targets .env files"
    fi
    ;;

  Bash)
    CMD="$(echo "$INPUT" | jq -r '.tool_input.command // empty')"
    # Match commands that read file contents and target .env files
    # (but not commands like "test -f .env" or "cp .env.example .env.local")
    if echo "$CMD" | grep -qE '(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|\.)\s+.*\.env' 2>/dev/null; then
      # Allow reading .env.example/.env.template
      if echo "$CMD" | grep -qE '\.(env\.example|env\.template|env\.sample)' 2>/dev/null; then
        exit 0
      fi
      block "Shell command reads .env file"
    fi
    # Also catch piping .env into something
    if echo "$CMD" | grep -qE '<\s*\.env|<\s*\S*\.env\.' 2>/dev/null; then
      block "Shell command reads .env file via redirect"
    fi

    # Block reading contents of ~/secrets/ and ~/.secrets/ files (ls/stat/file are OK)
    if echo "$CMD" | grep -qE '(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|\.)\s+.*~/\.?secrets' 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi
    if echo "$CMD" | grep -qE '(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|\.)\s+.*/Users/[^/]+/\.?secrets' 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi

    # 1Password CLI: block commands that extract secrets or mutate the vault.
    # Allowed: op item list, op vault list, op account list (metadata only).
    # For anything else, suggest the user run it manually.
    if echo "$CMD" | grep -qE '\bop\s+(read|inject|run)\b' 2>/dev/null; then
      block "op command extracts/injects secrets — suggest the user run it manually"
    fi
    if echo "$CMD" | grep -qE '\bop\s+item\s+(get|edit|delete|create)\b' 2>/dev/null; then
      block "op item command accesses/mutates vault — suggest the user run it manually"
    fi
    ;;
esac

exit 0
