#!/bin/bash
# Dev mode: backend with auto-reload + Vite dev server, in separate Terminal
# windows. Frontend proxies /api/* to the backend (see frontend/vite.config.ts).
# macOS equivalent of dev.ps1.
set -e
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting backend (FastAPI, auto-reload) on http://localhost:8000 ..."
osascript -e "tell application \"Terminal\" to do script \"cd '$root' && PNL_DEV=1 .venv/bin/python -m uvicorn backend.main:app --port 8000 --reload\""

echo "Starting frontend (Vite dev server) on http://localhost:5173 ..."
osascript -e "tell application \"Terminal\" to do script \"cd '$root/frontend' && npm run dev\""

echo ""
echo "Both started in separate Terminal windows. Open http://localhost:5173 once they're up."
