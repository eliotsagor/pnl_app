# Dev mode: backend with auto-reload + Vite dev server, in separate windows.
# Frontend proxies /api/* to the backend (see frontend/vite.config.ts).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Starting backend (FastAPI, auto-reload) on http://localhost:8000 ..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; `$env:PNL_DEV='1'; .\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000 --reload"
)

Write-Host "Starting frontend (Vite dev server) on http://localhost:5173 ..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root\frontend'; npm run dev"
)

Write-Host "`nBoth started in separate windows. Open http://localhost:5173 once they're up."
