#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r dashboard/requirements.txt

# Regenerate .env.local from 1Password (prompts Touch ID)
if [ -f .env.tpl ] && command -v op &> /dev/null; then
    op inject -i .env.tpl -o .env.local
fi

python dashboard/server.py
