# Daily-use mode: builds the frontend (if needed) and runs one backend
# process that serves both the built frontend and the API from the same
# origin -- no CORS, no second process, no second port. This is the
# script to run day-to-day; use dev.ps1 instead while actively developing.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "frontend\dist"

Set-Location $root

if (-not (Test-Path $dist)) {
    Write-Host "No frontend build found -- building now (this only happens once, or after frontend changes)..."
    Push-Location "$root\frontend"
    npm run build
    Pop-Location
}

Write-Host "Starting server on http://localhost:8000 ..."
Start-Process "http://localhost:8000"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
