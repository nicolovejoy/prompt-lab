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
# but only when every command on the line is one that never runs its arguments
# (only_inert_commands below: git commit, gh pr, grep, handoff.sh and the like).
# So a commit message that mentions a reader command is not a read, and a quoted
# .* is a pattern, not a file list. Three things inside quotes still count: the
# name of a secret file, a $(...) or backtick command, and a $VARIABLE. Any
# other command on the line, or shell syntax the hook does not model, gets the
# strict reading, where everything is a command.
#
# Known over-block: a quoted sentence that names a secret file still blocks when
# the same line also runs a reader (`git commit -m "... .env ..." | tail`). The
# name has to count there: `sed "r .env"` and `for f in ".env"; do cat $f` read
# it. Put the message in a heredoc, or run the reader on its own line.

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

# Rewrite the command so that quoted text a shell treats as data cannot be
# mistaken for commands. Data is everything in single quotes, and everything in
# double quotes except $(...), backticks and $VAR / ${...}.
#   mask_quoted code   data becomes spaces; quote marks and backticks are kept,
#                      so a quoted word is still visibly a word. Used to list
#                      the commands and to expand unquoted wildcards.
#   mask_quoted words  each shell word stays one word: quote marks are dropped
#                      and, inside data, spaces and shell operators become "_".
#                      A quoted sentence is then one long word that matches no
#                      command.
# A quoted span that crosses lines is joined into one line. Exit 3 for anything
# not modelled here: quotes or $( ) that do not balance, an unquoted backslash,
# $'...', a ${...} holding a command. Runs in the C locale: the command is
# walked byte by byte, and a byte of a multi-byte character is never syntax.
mask_quoted() {
  LC_ALL=C awk -v view="$1" -v sq="'" -v dq='"' '
    function push(s) { sp++; st[sp] = s; dep[sp] = 0 }
    function mark(c) { return (view == "words") ? "" : c }           # a quote mark
    function tick() { return (view == "words") ? " " : "`" }         # a backtick
    function data(c) {                                               # a data char
      if (view != "words") return " "
      return (c == sq || index(" \t|;&()<>`\"", c)) ? "_" : c
    }
    BEGIN { sp = 0; bad = 0; push("c") }   # c code, s single-quoted,
    {                                      # d double-quoted, p $( ) inside d,
      n = length($0); out = ""             # b backticks inside d
      for (i = 1; i <= n; i++) {
        ch = substr($0, i, 1); nx = substr($0, i + 1, 1); t = st[sp]
        if (t == "s") {
          if (ch == sq) { sp--; out = out mark(sq) } else out = out data(ch)
          continue
        }
        if (ch == "\\") {
          if (t == "d") { out = out data(" ") data(" "); i++; continue }
          if (i < n) bad = 1
          out = out " "; continue
        }
        if (t == "d") {
          if (ch == dq) { sp--; out = out mark(dq); continue }
          if (ch == "$" && nx == "(") { push("p"); out = out "$("; i++; continue }
          if (ch == "`") { push("b"); out = out tick(); continue }
          if (ch == "$" && nx == "{") {
            j = index(substr($0, i), "}"); seg = substr($0, i, j)
            if (j == 0 || index(seg, "$(") || index(seg, "`")) { bad = 1; j = n - i + 1 }
            out = out seg; i += j - 1; continue
          }
          if (ch == "$" && match(substr($0, i + 1), /^[A-Za-z_][A-Za-z0-9_]*/)) {
            out = out substr($0, i, RLENGTH + 1); i += RLENGTH; continue
          }
          out = out ((ch == "$") ? "$" : data(ch)); continue
        }
        if (ch == "$" && nx == sq) bad = 1
        if (ch == sq) { push("s"); out = out mark(sq); continue }
        if (ch == dq) { push("d"); out = out mark(dq); continue }
        if (ch == "`") { if (t == "b") sp--; out = out tick(); continue }
        if (t == "p") {
          if (ch == "(") dep[sp]++
          else if (ch == ")") {
            if (dep[sp] == 0) { sp--; out = out ")"; continue }
            dep[sp]--
          }
        }
        out = out ch
      }
      if (st[sp] == "s" || st[sp] == "d") printf "%s%s", out, data(" "); else print out
    }
    END { if (bad || sp != 1) exit 3 }
  '
}

# Is every command on the line one that never runs its arguments? Reads the
# output of `mask_quoted code`. Exit 0 = yes. This is an allow-list on purpose: a
# command missing from it only loses the lenient reading, it never gains one.
# Not listed, because they run a string: sh, eval, ssh, xargs, find, env, awk,
# python, node, sqlite3, op, and anything this list has not heard of.
only_inert_commands() {
  LC_ALL=C awk '
    function fail() { failed = 1; exit 1 }
    function endword(   c) {
      if (w == "") return
      c = w; w = ""
      if (c ~ /^#/) fail()                                  # a comment
      if (pos[d]) {
        if (c ~ /^[A-Za-z_][A-Za-z0-9_]*=/) return          # VAR=value prefix
        if (c in kw) return
        pos[d] = 0; sub(/^.*\//, "", c); cmd[d] = c; nw[d] = 1
        if (c != "git" && c != "gh" && !(c in ok)) fail()
        return
      }
      nw[d]++
      if (nw[d] == 2 && cmd[d] == "git" && !(c in gitok)) fail()
      if (nw[d] == 2 && cmd[d] == "gh" && !(c in ghok)) fail()
    }
    function endcmd() {
      endword()
      if ((cmd[d] == "git" || cmd[d] == "gh") && nw[d] == 1) fail()
      pos[d] = 1; nw[d] = 0; cmd[d] = ""
    }
    function open(kind) { endword(); d++; typ[d] = kind; pos[d] = 1; nw[d] = 0; cmd[d] = "" }
    BEGIN {
      d = 1; pos[1] = 1; nw[1] = 0; cmd[1] = ""; w = ""; failed = 0
      split("cd ls pwd echo printf true false test [ [[ for mkdir touch cp mv rm cat head tail wc sort uniq cut tr grep egrep fgrep rg sed jq date diff sleep basename dirname handoff.sh gc-write.sh gc-read.sh", a, " ")
      for (k in a) ok[a[k]] = 1
      split("add commit tag notes log show diff status grep push pull fetch checkout switch branch stash merge restore rev-parse cherry ls-files blame mv rm reset", g, " ")
      for (k in g) gitok[g[k]] = 1
      split("pr issue release run repo api workflow", h, " ")
      for (k in h) ghok[h[k]] = 1
      split("if then elif else do while until done fi ! { } time", b, " ")
      for (k in b) kw[b[k]] = 1
    }
    {
      n = length($0)
      for (i = 1; i <= n; i++) {
        ch = substr($0, i, 1)
        if (ch == " " || ch == "\t") { endword(); continue }
        # 2>&1 and &>file are redirects, not command separators
        if (ch == "&" && (substr($0, i - 1, 1) ~ /[<>]/ || substr($0, i + 1, 1) == ">")) { w = w ch; continue }
        if (ch == ";" || ch == "|" || ch == "&") { endcmd(); continue }
        if (ch == "(") { open("p"); continue }
        if (ch == ")") { endcmd(); if (typ[d] != "p") fail(); d--; continue }
        if (ch == "`") { if (typ[d] == "b") { endcmd(); d-- } else open("b"); continue }
        w = w ch
      }
      endcmd()
    }
    END { if (failed || d != 1) exit 1 }
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
# grep --include, rg -g, a git pathspec after --). There a quoted wildcard
# selects files, so it is tested against sample secret names instead of being
# read as pattern text.
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

# Does the command name a secret file? $1 is the whole line with quote marks
# turned into spaces, so a name counts wherever it is written; $2 is the view
# whose words are safe to expand as wildcards (see the Bash branch).
cmd_mentions_secret_file() {
  local flat="$1" code="$2" tok prev="" found=1
  # Names as written. No wildcard expansion: a quoted .* is a pattern, and
  # expanding it here would turn it into .env.
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

    # FLAT is the whole line with quote marks and backticks turned into
    # spaces. Names of secret files are always looked for in it.
    FLAT="$(printf '%s\n' "$CMD" | tr '"'"'"'`' '   ')"
    # The strict reading, and the default: everything is a command. Command
    # verbs (cat, op, env) are looked for in all of FLAT, and every word of it
    # may be expanded as a wildcard.
    VIEW="$FLAT"
    GLOBVIEW="$FLAT"
    # The lenient reading: quoted text is data. It needs syntax mask_quoted
    # models, nothing but inert commands, and none of the flags that make an
    # inert command run a program. Then verbs are looked for outside the data,
    # and only unquoted words are expanded.
    EXEC_FLAG='(^|[[:space:]])(--(upload-pack|receive-pack|exec|pre|compress-program|open-files-in-pager|ext-diff)|-O)'
    if MASKED="$(printf '%s\n' "$CMD" | mask_quoted code)" \
       && only_inert_commands <<<"$MASKED" \
       && ! grep -qE -- "$EXEC_FLAG" <<<"$MASKED" \
       && WORDS="$(printf '%s\n' "$CMD" | mask_quoted words)"; then
      VIEW="$WORDS"
      GLOBVIEW="$(printf '%s\n' "$MASKED" | tr '"'"'"'`' '   ')"
    fi

    # --- secret files on the command line ---
    # A reader verb + a secret-classified file name anywhere on the line = block.
    # Writers (cp, mv, touch, test -f, op inject -o) with no reader verb pass.
    READER='(^|[|;&(!]|\s)(cat|head|tail|less|more|bat|sed|awk|grep|rg|ag|source|xxd|strings|base64|od|hexdump|cut|tr|sort|uniq|wc|python3?|node|ruby|perl|\.)\s'
    READS=0
    if grep -qE "$READER" <<<"$VIEW" 2>/dev/null; then READS=1; fi
    if [ "$READS" -eq 1 ] && cmd_mentions_secret_file "$FLAT" "$GLOBVIEW"; then
      block "Shell command reads a secret file"
    fi
    # Redirect-in from a secret file: < .env, < .env.local, <.env
    for tok in $(printf '%s\n' "$VIEW" | grep -oE '<\s*[^ <>|;&)]+' | sed -E 's/^<\s*//' || true); do
      if is_secret_file "$tok"; then block "Shell command reads a secret file via redirect"; fi
    done

    # --- ~/secrets and ~/.secrets: contents never, listing OK ---
    if [ "$READS" -eq 1 ] && grep -qE "$READER"'.*(~|\$HOME|/Users/[^/]+)/\.?secrets' <<<"$VIEW" 2>/dev/null; then
      block "Shell command reads file in secrets dir — ask the user to handle it directly"
    fi

    # --- 1Password CLI ---
    # Still blocked, always: anything whose purpose is to PRINT a secret value.
    if grep -qE '\bop\s+read\b' <<<"$VIEW" 2>/dev/null; then
      block "op read prints a secret value — suggest the user run it manually"
    fi
    if grep -qE '\bop\s+item\s+(get|delete)\b' <<<"$VIEW" 2>/dev/null; then
      block "op item get/delete — suggest the user run it manually"
    fi
    if grep -qE '\bop\b.*--reveal' <<<"$VIEW" 2>/dev/null; then
      block "op --reveal prints secret values"
    fi
    if grep -qE '\bop\s+item\s+(create|edit)\b.*--format' <<<"$VIEW" 2>/dev/null; then
      block "op item create/edit with --format prints field values"
    fi
    # op inject: allowed only when writing to a file (-o / --out-file). Without
    # it, the materialized secrets go to stdout.
    if grep -qE '\bop\s+inject\b' <<<"$VIEW" 2>/dev/null; then
      if ! grep -qE '\bop\s+inject\b[^|;&]*(\s-o\s|--out-file[ =])' <<<"$VIEW" 2>/dev/null; then
        block "op inject without -o would print secrets — add -o <file>"
      fi
    fi
    # op run: secrets go into the child's environment, not the transcript. Block
    # only if the child command obviously dumps the environment.
    if grep -qE '\bop\s+run\b' <<<"$VIEW" 2>/dev/null; then
      CHILD="${VIEW#*op run}"
      CHILD="${CHILD#* -- }"
      if grep -qE '(^|[|;&(]|\s)(env|printenv)(\s|$)|\bexport\s+-p\b|\bdeclare\s+-[xp]\b|\becho\b[^|;&]*\$' <<<"$CHILD" 2>/dev/null; then
        block "op run child command would print environment variables"
      fi
    fi
    ;;
esac

exit 0
