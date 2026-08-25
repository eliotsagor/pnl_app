#!/bin/bash
# Daily-use mode: builds the frontend (if needed) and runs one backend
# process that serves both the built frontend and the API from the same
# origin -- no CORS, no second process, no second port. This is the
# script to run day-to-day; use dev.sh instead while actively developing.
# macOS/Linux equivalent of start.ps1.
set -e
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [ ! -d "frontend/dist" ]; then
    echo "No frontend build found -- building now (this only happens once, or after frontend changes)..."
    (cd frontend && npm run build)
fi

echo "Starting server on http://localhost:8000 ..."
( sleep 1 && open "http://localhost:8000" ) &

.venv/bin/python -m uvicorn backend.main:app --port 8000 2>&1 | tee server.log
