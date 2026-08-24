@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://python.org and re-run this file.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo First-time setup: creating Python environment...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    ".venv\Scripts\python.exe" -m playwright install chromium
)

if not exist "template.xlsx" (
    echo.
    echo NOTE: template.xlsx not found. Excel export won't work until you add
    echo your own blank spreadsheet template as template.xlsx in this folder.
    echo Everything else will still run fine.
    echo.
)

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js/npm was not found. Install it from https://nodejs.org and re-run this file.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo First-time setup: installing frontend dependencies...
    pushd frontend
    call npm install
    popd
)

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start.ps1"
