# ============================================================
# work.zsh — iTerm2 per-project launcher
# ------------------------------------------------------------
# Pick any directory under ~/src (menu, argument, or tab
# completion) and open a new iTerm2 window with three panes,
# all cd'd into the project folder:
#   - top (full width, ~80% height) : Claude Code
#   - bottom left/right (~20%)       : two shells
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
# ============================================================

WORK_SRC_DIR="$HOME/src"
WORK_COLS=200   # window size in terminal cells; iTerm2 clamps to screen
WORK_ROWS=55    # if larger than the display can fit


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
work() {
  local name="${1%/}"   # tolerate a trailing slash from completion

  # If no project was named, show a numbered menu of ~/src dirs.
  if [[ -z "$name" ]]; then
    local options=($WORK_SRC_DIR/*(/N:t))
    echo "Pick a project:"
    select name in $options; do
      [[ -n "$name" ]] && break
    done
  fi

  # NB: can't name this "path" — zsh ties that name to $PATH.
  local proj_dir="$WORK_SRC_DIR/$name"
  if [[ ! -d "$proj_dir" ]]; then
    echo "No such directory: $proj_dir"
    return 1
  fi

  local r g b
  read r g b <<< "$(_work_color "$name")"

  # Bottom strip gets ~1/5 of the rows; the top Claude pane keeps
  # the rest (~80%). "Close to 80/20 is fine" — the knob is the / 5.
  local bottom_rows=$(( WORK_ROWS / 5 ))

  # Drive iTerm2 with AppleScript. The zsh variables above
  # ($proj_dir, $r, $g, $b, $bottom_rows) are substituted into
  # the script text.
  osascript <<EOF
tell application "iTerm"
  activate
  set w to (create window with default profile)
  tell w
    set s1 to current session
    tell s1
      set columns to $WORK_COLS
      set rows to $WORK_ROWS
      set s2 to (split horizontally with default profile) -- bottom strip
    end tell
    tell s2
      set s3 to (split vertically with default profile)   -- bottom-right
      set rows to $bottom_rows                             -- shrink to ~20%
    end tell

    -- top pane (full width): cd, color the tab, then launch Claude
    tell s1 to write text "cd '$proj_dir' && iterm_tab_color $r $g $b && clear && claude"
    -- the two bottom shells: just cd into the project
    tell s2 to write text "cd '$proj_dir'"
    tell s3 to write text "cd '$proj_dir'"

    tell s1 to select   -- leave focus on the Claude pane
  end tell
end tell
EOF
}


# --- 3. TAB COMPLETION -------------------------------------
# Complete `work <TAB>` with the directories in ~/src.
_work() { compadd -- $WORK_SRC_DIR/*(/N:t) }
if (( $+functions[compdef] )); then compdef _work work; fi

# ============================================================
# TWEAKS:
# - Top/bottom ratio: change the `/ 5` in bottom_rows (smaller
#   divisor = taller bottom strip).
# - Window size: WORK_COLS / WORK_ROWS above (iTerm clamps to screen).
# - Swap pane layout: change "split vertically" <-> "split
#   horizontally" in section 2 to rearrange the splits.
# - Two tabs instead of panes? Replace the split lines with
#   `tell w to create tab with default profile`.
# - Run something other than claude: edit the s1 write line.
# - Different color feel: tweak s (saturation) / v (brightness)
#   in _work_color.
# ============================================================
