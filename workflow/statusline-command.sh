#!/bin/sh
input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // empty')

used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
duration_ms=$(echo "$input" | jq -r '.cost.total_duration_ms // empty')
in_tok=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
out_tok=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
now=$(TZ=America/Los_Angeles date "+%-I:%M%p PST" | tr '[:upper:]' '[:lower:]')


# Format duration as Xm or Xh Ym
if [ -n "$duration_ms" ] && [ "$duration_ms" != "null" ]; then
  total_sec=$((duration_ms / 1000))
  mins=$((total_sec / 60))
  if [ "$mins" -ge 60 ]; then
    hrs=$((mins / 60))
    rem=$((mins % 60))
    dur_fmt="${hrs}h${rem}m"
  else
    dur_fmt="${mins}m"
  fi
else
  dur_fmt=""
fi

# Color context percentage: green < 50%, orange 50-69%, red >= 70%
ORANGE='\033[38;5;208m'
RED='\033[31m'
RESET='\033[0m'

context_fmt=""
if [ -n "$used" ] && [ "$(echo "$used > 0" | bc 2>/dev/null)" = "1" ]; then
  pct=$(printf '%.0f' "$used")
  if [ "$pct" -ge 70 ]; then
    context_fmt=$(printf '%b' "${RED}context is ${pct}%% full${RESET}")
  elif [ "$pct" -ge 50 ]; then
    context_fmt=$(printf '%b' "${ORANGE}context is ${pct}%% full${RESET}")
  else
    context_fmt="context is ${pct}% full"
  fi
fi

# Format token counts as Xk with in/out proportion
tok_fmt=""
total_tok=$((in_tok + out_tok))
if [ "$total_tok" -gt 0 ]; then
  in_k=$((in_tok / 1000))
  out_k=$((out_tok / 1000))
  in_pct=$((in_tok * 100 / total_tok))
  out_pct=$((100 - in_pct))
  tok_fmt="${in_k}k in/${out_k}k out (${in_pct}/${out_pct}%)"
fi

# Assemble
parts=""
[ -n "$model" ] && parts="$model"

[ -n "$tok_fmt" ] && parts="$parts · $tok_fmt"
[ -n "$context_fmt" ] && parts="$parts · $context_fmt"
[ -n "$dur_fmt" ] && parts="$parts · $dur_fmt"
parts="$parts · $now"

printf '%b' "$parts"
