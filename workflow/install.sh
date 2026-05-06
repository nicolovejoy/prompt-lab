#!/bin/bash
# Ground Control install script
# Copies slash commands, hooks config snippet, and launchd plists to the right places.
# Run from anywhere — detects repo location automatically.

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PYTHON3="$VENV_DIR/bin/python3"
COMMANDS_DIR="$HOME/.claude/commands"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

FORCE=0
for arg in "$@"; do
    case "$arg" in
        -f|--force) FORCE=1 ;;
        -h|--help)
            echo "Usage: $0 [--force]"
            echo "  --force  overwrite existing files without backing them up"
            exit 0
            ;;
    esac
done

# install_file SRC DEST LABEL
# Copies SRC to DEST. If DEST exists and differs, backs it up to
# DEST.bak.YYYYMMDD-HHMMSS first (unless --force was passed).
install_file() {
    local src="$1" dest="$2" label="$3"
    if [ -f "$dest" ] && ! cmp -s "$src" "$dest"; then
        if [ "$FORCE" = "1" ]; then
            echo "Overwriting (--force): $label"
        else
            local backup="$dest.bak.$(date +%Y%m%d-%H%M%S)"
            echo "WARN: $label differs from installed version"
            echo "  → backing up existing to $backup"
            cp "$dest" "$backup"
        fi
    fi
    cp "$src" "$dest"
}

echo "Installing Ground Control from: $REPO_DIR"
[ "$FORCE" = "1" ] && echo "(--force: existing files will be overwritten without backup)"
echo ""

# --- Python venv ---
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q anthropic python-dotenv
echo "Venv ready: $PYTHON3"
echo ""

# --- Slash commands ---
mkdir -p "$COMMANDS_DIR"
for cmd in "$REPO_DIR/workflow/commands/"*.md; do
    name=$(basename "$cmd")
    install_file "$cmd" "$COMMANDS_DIR/$name" "command $name"
    echo "Copied command: $name → $COMMANDS_DIR/"
done

# --- launchd plists (macOS only) ---
if [[ "$OSTYPE" == darwin* ]] && command -v launchctl &>/dev/null; then
    mkdir -p "$LAUNCH_AGENTS"
    for plist in "$REPO_DIR/workflow/"*.plist; do
        name=$(basename "$plist")
        label="${name%.plist}"
        dest="$LAUNCH_AGENTS/$name"

        # Render plist with placeholder substitution to a temp file so we can
        # diff against the existing dest before clobbering.
        rendered=$(mktemp -t "gc-plist.XXXXXX")
        sed \
            -e "s|__REPO_DIR__|$REPO_DIR|g" \
            -e "s|__PYTHON3__|$PYTHON3|g" \
            "$plist" > "$rendered"

        # Only unload if the dest exists and the agent is currently loaded.
        if [ -f "$dest" ] && launchctl list "$label" &>/dev/null; then
            launchctl unload "$dest" 2>/dev/null || true
        fi

        install_file "$rendered" "$dest" "plist $name"
        rm -f "$rendered"

        launchctl load "$dest"
        echo "Loaded plist: $name"
    done
else
    echo "Skipping launchd plists (not macOS or launchctl not found)"
fi

# --- settings.json instructions ---
echo ""
echo "────────────────────────────────────────────────────"
echo "Manual step: add these to ~/.claude/settings.json"
echo "────────────────────────────────────────────────────"
cat <<EOF
{
  "permissions": {
    "allow": ["Bash(sqlite3 ~/.claude/prompt-history.db *)"]
  },
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{"type": "command", "command": "$REPO_DIR/workflow/hooks/log-prompt.sh", "timeout": 5000}]
    }],
    "Stop": [{
      "hooks": [{"type": "command", "command": "$REPO_DIR/workflow/hooks/session-stop.sh", "timeout": 5000}]
    }]
  }
}
EOF

echo ""
echo "Done. Restart Claude Code for hook changes to take effect."
