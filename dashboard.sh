#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q -r dashboard/requirements.txt
else
    source .venv/bin/activate
fi

python dashboard/server.py
