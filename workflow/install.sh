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

echo "Installing Ground Control from: $REPO_DIR"
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
    cp "$cmd" "$COMMANDS_DIR/$name"
    echo "Copied command: $name → $COMMANDS_DIR/"
done

# --- launchd plists (macOS only) ---
if [[ "$OSTYPE" == darwin* ]] && command -v launchctl &>/dev/null; then
    mkdir -p "$LAUNCH_AGENTS"
    for plist in "$REPO_DIR/workflow/"*.plist; do
        name=$(basename "$plist")
        label="${name%.plist}"
        dest="$LAUNCH_AGENTS/$name"

        # Unload if already registered
        launchctl unload "$dest" 2>/dev/null || true

        # Substitute placeholders
        sed \
            -e "s|__REPO_DIR__|$REPO_DIR|g" \
            -e "s|__PYTHON3__|$PYTHON3|g" \
            "$plist" > "$dest"

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
