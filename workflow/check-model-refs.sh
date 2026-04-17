#!/usr/bin/env bash
# Check for deprecated Anthropic model references across ~/src projects.
# Skips node_modules, .venv, .next, .git, __pycache__, and binary files.

MODEL="${1:-claude-sonnet-4-20250514}"

grep -r --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' --include='*.json' --include='*.md' --include='*.yaml' --include='*.yml' --include='*.toml' \
  --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.next --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=dist --exclude-dir=build \
  "$MODEL" ~/src/

exit_code=$?
if [ $exit_code -eq 1 ]; then
  echo "No first-party references to $MODEL found."
fi
