# ============================================================
# work.zsh — iTerm2 per-project launcher
# ------------------------------------------------------------
# Pick any directory under ~/src (menu, argument, or tab
# completion) and open a new iTerm2 window with two panes,
# both cd'd into the project folder:
#   - top (~80% height)    : Claude Code
#   - bottom strip (~20%)  : one shell, cleared, ready to type
# The tab color is derived from the project name (same name ->
# same color, always), so no per-project config is needed.
#
# INSTALL:  synced across machines by prompt-lab. `./workflow/install.sh`
#           copies this to ~/.claude/shell/work.zsh and adds a source
#           line to ~/.zshrc (after compinit, so completion registers).
#           To edit: change this file, commit/push, then on each machine
#           `git pull` + `./workflow/install.sh`.
# USE:      `work`            -> shows a numbered menu
#           `work musicforge` -> opens that project directly
#           `work mus<TAB>`   -> completes from ~/src
#           Every `work` launch then asks which Claude model to use,
#           then which effort level (Enter keeps the default from
#           ~/.claude/settings.json, a number picks another) and
#           starts the session on /readup.
#           `work musicforge opus`      -> skips the model question.
#           `work musicforge opus high` -> skips both questions.
#           (The Codex launchers `cx` and `duet` were removed 2026-10-16
#           when Codex was retired.)
# ============================================================

WORK_SRC_DIR="$HOME/src"
WORK_COLS=150   # window size in terminal cells; iTerm2 clamps to screen
WORK_ROWS=100   # if larger than the display can fit (set high to fill screen height)
WORK_BOTTOM_PCT=20   # height of the bottom shell strip, as a percentage of WORK_ROWS


# --- 1. TAB COLOR HELPERS ----------------------------------
# Sets the current iTerm2 tab's color via iTerm2's proprietary
# escape sequence (one call each for red, green, blue).
iterm_tab_color() {
  printf '\033]6;1;bg;red;brightness;%d\a'   "$1"
  printf '\033]6;1;bg;green;brightness;%d\a' "$2"
  printf '\033]6;1;bg;blue;brightness;%d\a'  "$3"
}

# Optional: clear a tab's color back to default.
iterm_tab_color_reset() { printf '\033]6;1;bg;*;default\a'; }

# Show text as an iTerm2 badge — the faint watermark in the pane's
# top-right corner. Unlike the tab/window title, a badge can't be
# overwritten by programs running in the pane (Claude Code sets its
# own title, so the title alone doesn't reliably show the project).
iterm_badge() { printf '\033]1337;SetBadgeFormat=%s\a' "$(printf '%s' "$1" | base64)"; }

# Optional: remove the current pane's badge.
iterm_badge_reset() { printf '\033]1337;SetBadgeFormat=\a'; }

# Map a project name to a stable "R G B" color: hash the name
# to a hue (0-359), then convert HSV -> RGB at fixed
# saturation/brightness so every project gets a distinct but
# equally vivid color.
_work_color() {
  local hash=${$(printf '%s' "$1" | cksum)[(w)1]}   # first word = checksum
  local h=$(( hash % 360 ))
  local i=$(( h / 60 ))
  local -F f s v p q t R G B
  s=0.65; v=0.9
  f=$(( (h % 60) / 60.0 ))
  p=$(( v * (1 - s) ))
  q=$(( v * (1 - s * f) ))
  t=$(( v * (1 - s * (1 - f)) ))
  case $i in
    0) R=$v; G=$t; B=$p ;;
    1) R=$q; G=$v; B=$p ;;
    2) R=$p; G=$v; B=$t ;;
    3) R=$p; G=$q; B=$v ;;
    4) R=$t; G=$p; B=$v ;;
    5) R=$v; G=$p; B=$q ;;
  esac
  printf '%.0f %.0f %.0f' $(( R * 255 )) $(( G * 255 )) $(( B * 255 ))
}


# --- 2. THE LAUNCHER ---------------------------------------
work() { _work_launch "$@"; }
WORK_MODELS=(fable opus sonnet haiku)      # aliases the claude CLI accepts for --model
WORK_EFFORTS=(low medium high xhigh max)   # levels the claude CLI accepts for --effort

# Resolve a project name (argument or numbered menu) into REPLY.
_work_pick() {
  local name="${1%/}"   # tolerate a trailing slash from completion

  # If no project was named, show a numbered menu of ~/src dirs.
  if [[ -z "$name" ]]; then
    local options=($WORK_SRC_DIR/*(/N:t))
    echo "Pick a project:"
    select name in $options; do
      [[ -n "$name" ]] && break
    done
  fi

  if [[ ! -d "$WORK_SRC_DIR/$name" ]]; then
    echo "No such directory: $WORK_SRC_DIR/$name"
    return 1
  fi
  REPLY="$name"
}

# Read a top-level string key from ~/.claude/settings.json (no jq dependency).
_work_setting() {
  sed -n 's/^ *"'"$1"'": *"\([^"]*\)".*/\1/p' "$HOME/.claude/settings.json" 2>/dev/null | head -1
}

# Ask the user to pick one of a list, showing the current default first.
#   _work_choose <label> <default> <option>...
# Enter keeps the default; a number picks another. REPLY is empty when
# the default is kept, so claude keeps its own choice.
_work_choose() {
  local label="$1" default="$2"
  shift 2
  local others=(${@:#$default})
  local i
  echo "$label: [Enter] $default (current)"
  for i in {1..${#others}}; do
    echo "  $i) ${others[$i]}"
  done
  local choice
  REPLY=""
  while true; do
    read -r "choice?> " || return 1
    [[ -z "$choice" ]] && return 0
    if [[ "$choice" == <1-> && -n "${others[$choice]}" ]]; then
      REPLY="${others[$choice]}"
      return 0
    fi
    echo "Enter for $default, or a number 1-${#others}."
  done
}

# Resolve the Claude model for this session into REPLY.
#   _work_model [alias]   -> an argument skips the question.
# The default is the "model" key in ~/.claude/settings.json, falling
# back to the first of WORK_MODELS.
_work_model() {
  REPLY="$1"
  [[ -n "$REPLY" ]] && return 0
  local default=$(_work_setting model)
  [[ -z "$default" ]] && default="${WORK_MODELS[1]}"
  _work_choose Model "$default" $WORK_MODELS
}

# Resolve the effort level for this session into REPLY.
#   _work_effort [level]   -> an argument skips the question.
# The default is the top-level "effortLevel" key in ~/.claude/settings.json
# (per-model overrides under "modelSettings" are keyed by full model id,
# not alias, so they are not consulted), falling back to medium.
_work_effort() {
  REPLY="$1"
  [[ -n "$REPLY" ]] && return 0
  local default=$(_work_setting effortLevel)
  [[ -z "$default" ]] && default=medium
  _work_choose Effort "$default" $WORK_EFFORTS
}

# Build the pane commands for one checkout.
#   _work_cmds <project> <dir> [model] [effort]
# model / effort (optional) are passed as --model / --effort; the claude
# pane always opens on /readup so the session registers itself.
# Sets reply=(claude_pane_cmd shell_pane_cmd).
_work_cmds() {
  local name="$1" dir="$2" model="$3" effort="$4"
  local r g b
  read r g b <<< "$(_work_color "$name")"

  local title="${(U)name[1]}${name[2,-1]} -- Claude"
  # One scope per launch, so two windows never share a session row.
  local session_scope="claude-$(uuidgen)"
  # Quote shell arguments before passing commands as AppleScript argv.
  # Project names may contain spaces, quotes, or shell metacharacters.
  local title_cmd="printf '\\033]0;%s\\a' ${(q)title}"
  # The helper shell restores the project title at its prompt, then
  # clears so the pane opens on an empty screen.
  local shell_cmd="cd -- ${(q)dir} && precmd() { $title_cmd; } && precmd && clear"
  local agent_cmd="claude --name ${(q)title}"
  [[ -n "$model" ]] && agent_cmd+=" --model ${(q)model}"
  [[ -n "$effort" ]] && agent_cmd+=" --effort ${(q)effort}"
  agent_cmd+=" /readup"
  local top_cmd="$shell_cmd && export GC_SESSION_SCOPE=${(q)session_scope} && iterm_tab_color $r $g $b && iterm_badge ${(q)title} && clear && $agent_cmd"
  reply=("$top_cmd" "$shell_cmd")
}

_work_launch() {
  _work_pick "$1" || return 1
  local name="$REPLY"
  # NB: can't name this "path" — zsh ties that name to $PATH.
  local proj_dir="$WORK_SRC_DIR/$name"

  _work_model "$2" || return 1
  local model="$REPLY"
  _work_effort "$3" || return 1
  local effort="$REPLY"

  _work_cmds "$name" "$proj_dir" "$model" "$effort"
  local top_cmd="${reply[1]}" shell_cmd="${reply[2]}"
  local bottom_rows=$(( WORK_ROWS * WORK_BOTTOM_PCT / 100 ))

  osascript - "$top_cmd" "$shell_cmd" "$WORK_COLS" "$WORK_ROWS" "$bottom_rows" <<'APPLESCRIPT'
on run argv
  set topCommand to item 1 of argv
  set shellCommand to item 2 of argv
  set windowColumns to (item 3 of argv) as integer
  set windowRows to (item 4 of argv) as integer
  set bottomRows to (item 5 of argv) as integer
  tell application "iTerm"
    activate
    set w to (create window with default profile)
    tell w
      set s1 to current session
      tell s1
        set columns to windowColumns
        set rows to windowRows
        set s2 to (split horizontally with default profile)
      end tell
      tell s2 to set rows to bottomRows
      tell s1 to write text topCommand
      tell s2 to write text shellCommand
      tell s1 to select
    end tell
  end tell
end run
APPLESCRIPT
}



# --- 3. TAB COMPLETION -------------------------------------
# Complete `work <TAB>` with the directories in ~/src.
_work() { compadd -- $WORK_SRC_DIR/*(/N:t) }
if (( $+functions[compdef] )); then compdef _work work; fi

# ============================================================
# TWEAKS:
# - Top/bottom ratio: WORK_BOTTOM_PCT above (bigger = taller
#   bottom strip).
# - Window size: WORK_COLS / WORK_ROWS above (iTerm clamps to screen).
# - Side-by-side instead of stacked: change "split horizontally"
#   to "split vertically" in section 2.
# - A tab instead of a pane? Replace the split line with
#   `tell w to create tab with default profile`.
# - Agent command: edit agent_cmd in _work_cmds.
# - No project badge: drop the iterm_badge call from the s1 line
#   (or run iterm_badge_reset in a pane to clear it live).
# - Different color feel: tweak s (saturation) / v (brightness)
#   in _work_color.
# ============================================================
