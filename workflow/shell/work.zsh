# ============================================================
# work.zsh — iTerm2 per-project launcher
# ------------------------------------------------------------
# Pick any directory under ~/src (menu, argument, or tab
# completion) and open a new iTerm2 window with three panes,
# all cd'd into the project folder:
#   - top (full width, ~80% height) : Claude Code or Codex
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
#           `cx prompt-lab` -> same layout, running Codex
#           `duet prompt-lab` -> four panes: Claude | Codex on top,
#                              a shell under each; Codex runs in
#                              ~/src/<project>-codex when that clone exists
# ============================================================

WORK_SRC_DIR="$HOME/src"
WORK_COLS=200   # window size in terminal cells; iTerm2 clamps to screen
WORK_ROWS=100   # if larger than the display can fit (set high to fill screen height)


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
work() { _work_launch claude "$@"; }
cx() { _work_launch codex "$@"; }
duet() { _work_duet "$@"; }

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

# Build the pane commands for one agent in one checkout.
#   _work_cmds <agent> <project> <dir> [window_title]
# window_title (optional) replaces the per-agent title in the title bar;
# the badge keeps naming the agent so each pane stays identifiable.
# Sets reply=(agent_pane_cmd shell_pane_cmd).
_work_cmds() {
  local agent="$1" name="$2" dir="$3" window_title="$4"
  local r g b
  read r g b <<< "$(_work_color "$name")"

  local agent_label="Claude"
  [[ "$agent" == codex ]] && agent_label="Codex"
  local title="${(U)name[1]}${name[2,-1]} -- $agent_label"
  # One scope per agent pane, so two agents never share a session row.
  local session_scope="${agent}-$(uuidgen)"
  # Quote shell arguments before passing commands as AppleScript argv.
  # Project names may contain spaces, quotes, or shell metacharacters.
  local title_cmd="printf '\\033]0;%s\\a' ${(q)${window_title:-$title}}"
  # Each helper shell restores the project/agent title at its prompt.
  local shell_cmd="cd -- ${(q)dir} && precmd() { $title_cmd; } && precmd"
  local agent_cmd="claude --name ${(q)title}"
  [[ "$agent" == codex ]] && agent_cmd="codex"
  local top_cmd="$shell_cmd && export GC_SESSION_SCOPE=${(q)session_scope} && iterm_tab_color $r $g $b && iterm_badge ${(q)title} && clear && $agent_cmd"
  reply=("$top_cmd" "$shell_cmd")
}

_work_launch() {
  local agent="$1"
  shift
  _work_pick "$1" || return 1
  local name="$REPLY"
  # NB: can't name this "path" — zsh ties that name to $PATH.
  local proj_dir="$WORK_SRC_DIR/$name"

  _work_cmds "$agent" "$name" "$proj_dir"
  local top_cmd="${reply[1]}" shell_cmd="${reply[2]}"
  local bottom_rows=$(( WORK_ROWS * 15 / 100 ))

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
      tell s2
        set s3 to (split vertically with default profile)
        set rows to bottomRows
      end tell
      tell s1 to write text topCommand
      tell s2 to write text shellCommand
      tell s3 to write text shellCommand
      tell s1 to select
    end tell
  end tell
end run
APPLESCRIPT
}

# duet: Claude and Codex side by side, one column per checkout.
#   left  : Claude + shell in ~/src/<project>
#   right : Codex  + shell in ~/src/<project>-codex (the Codex clone;
#           falls back to the main checkout if the clone doesn't exist)
_work_duet() {
  _work_pick "$1" || return 1
  local name="$REPLY"
  local proj_dir="$WORK_SRC_DIR/$name"
  local codex_dir="$WORK_SRC_DIR/$name-codex"
  if [[ ! -d "$codex_dir" ]]; then
    echo "No Codex clone at $codex_dir; Codex opens in the main checkout."
    echo "Create one: git clone \"\$(git -C ${(q)proj_dir} remote get-url origin)\" ${(q)codex_dir}"
    codex_dir="$proj_dir"
  fi

  local duet_title="${(U)name[1]}${name[2,-1]} -- DUET: Claude + Codex"
  _work_cmds claude "$name" "$proj_dir" "$duet_title"
  local claude_cmd="${reply[1]}" claude_shell="${reply[2]}"
  _work_cmds codex "$name" "$codex_dir" "$duet_title"
  local codex_cmd="${reply[1]}" codex_shell="${reply[2]}"
  local bottom_rows=$(( WORK_ROWS * 15 / 100 ))

  osascript - "$claude_cmd" "$claude_shell" "$codex_cmd" "$codex_shell" "$WORK_COLS" "$WORK_ROWS" "$bottom_rows" <<'APPLESCRIPT'
on run argv
  set claudeCommand to item 1 of argv
  set claudeShell to item 2 of argv
  set codexCommand to item 3 of argv
  set codexShell to item 4 of argv
  set windowColumns to (item 5 of argv) as integer
  set windowRows to (item 6 of argv) as integer
  set bottomRows to (item 7 of argv) as integer
  tell application "iTerm"
    activate
    set w to (create window with default profile)
    tell w
      set s1 to current session
      tell s1
        set columns to windowColumns
        set rows to windowRows
        -- Rows first: one bottom strip, so both shells get the same height.
        set s2 to (split horizontally with default profile)
      end tell
      tell s2 to set rows to bottomRows
      -- Then halve each row; equal halves keep the column divider aligned.
      tell s1 to set s3 to (split vertically with default profile)
      tell s2 to set s4 to (split vertically with default profile)
      tell s1 to write text claudeCommand
      tell s2 to write text claudeShell
      tell s3 to write text codexCommand
      tell s4 to write text codexShell
      tell s1 to select
    end tell
  end tell
end run
APPLESCRIPT
}


# --- 3. TAB COMPLETION -------------------------------------
# Complete `work <TAB>` with the directories in ~/src.
_work() { compadd -- $WORK_SRC_DIR/*(/N:t) }
if (( $+functions[compdef] )); then compdef _work work cx duet; fi

# ============================================================
# TWEAKS:
# - Top/bottom ratio: change the `* 15 / 100` in bottom_rows
#   (bigger percentage = taller bottom strip).
# - Window size: WORK_COLS / WORK_ROWS above (iTerm clamps to screen).
# - Swap pane layout: change "split vertically" <-> "split
#   horizontally" in section 2 to rearrange the splits.
# - Two tabs instead of panes? Replace the split lines with
#   `tell w to create tab with default profile`.
# - Agent command: edit agent_cmd in _work_cmds.
# - No project badge: drop the iterm_badge call from the s1 line
#   (or run iterm_badge_reset in a pane to clear it live).
# - Different color feel: tweak s (saturation) / v (brightness)
#   in _work_color.
# ============================================================
