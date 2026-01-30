#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Claude workflow tools..."
echo ""

# Check dependencies
if ! command -v jq &> /dev/null; then
    echo "Error: jq required. Install with: brew install jq"
    exit 1
fi

if ! command -v sqlite3 &> /dev/null; then
    echo "Error: sqlite3 required"
    exit 1
fi

# Create directories
mkdir -p ~/.claude/commands ~/.claude/hooks

# Symlink commands
echo "Installing commands..."
for cmd in readup handoff prompts review; do
    ln -sf "$SCRIPT_DIR/workflow/commands/$cmd.md" ~/.claude/commands/
    echo "  /$(basename $cmd .md)"
done

# Symlink hook
echo "Installing hook..."
ln -sf "$SCRIPT_DIR/workflow/hooks/log-prompt.sh" ~/.claude/hooks/
echo "  log-prompt.sh"

# Add hook to settings.json
SETTINGS=~/.claude/settings.json
if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

echo "Configuring settings.json..."
HOOK_PATH="$SCRIPT_DIR/workflow/hooks/log-prompt.sh"
jq --arg hook "$HOOK_PATH" '.hooks.UserPromptSubmit = [{"hooks": [{"type": "command", "command": $hook, "timeout": 5000}]}]' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

# Create database if needed
if [ ! -f ~/.claude/prompt-history.db ]; then
    echo "Creating prompt-history.db..."
    sqlite3 ~/.claude/prompt-history.db <<'EOF'
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    project TEXT,
    prompt TEXT NOT NULL,
    outcome TEXT,
    utility INTEGER CHECK(utility BETWEEN 1 AND 5),
    tags TEXT,
    notes TEXT,
    session_id INTEGER REFERENCES sessions(id),
    context TEXT
);
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    summary TEXT,
    utility INTEGER CHECK(utility BETWEEN 1 AND 5)
);
CREATE TABLE commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER,
    hash TEXT NOT NULL,
    message TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);
CREATE INDEX idx_prompts_project ON prompts(project);
CREATE INDEX idx_prompts_utility ON prompts(utility);
CREATE INDEX idx_commits_prompt_id ON commits(prompt_id);
CREATE INDEX idx_sessions_project ON sessions(project);
EOF
    echo "  Created ~/.claude/prompt-history.db"
else
    echo "  Database already exists"
fi

# Offer CLAUDE.md template
if [ ! -f ~/.claude/CLAUDE.md ]; then
    echo ""
    read -p "Install CLAUDE.md template? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        cp "$SCRIPT_DIR/workflow/CLAUDE.md.template" ~/.claude/CLAUDE.md
        echo "  Installed ~/.claude/CLAUDE.md"
    fi
fi

echo ""
echo "Install complete!"
echo ""
echo "Commands installed:"
echo "  /readup   - Start a session, review last session's prompts"
echo "  /handoff  - End a session, update docs"
echo "  /prompts  - Query prompt history"
echo "  /review   - Summarize recent sessions (past N days)"
echo ""
echo "Prompts are auto-logged to ~/.claude/prompt-history.db"
echo "Run ./dashboard.sh to start the dashboard"
