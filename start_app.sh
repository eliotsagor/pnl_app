#!/bin/bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python was not found. Install it from https://python.org and re-run this file."
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "First-time setup: creating Python environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m playwright install chromium
fi

if [ ! -f "template.xlsx" ]; then
    echo ""
    echo "NOTE: template.xlsx not found. Excel export won't work until you add"
    echo "your own blank spreadsheet template as template.xlsx in this folder."
    echo "Everything else will still run fine."
    echo ""
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js/npm was not found. Install it from https://nodejs.org and re-run this file."
    exit 1
fi

if [ ! -d "frontend/node_modules" ]; then
    echo "First-time setup: installing frontend dependencies..."
    (cd frontend && npm install)
fi

exec ./scripts/start.sh
