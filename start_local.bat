@echo off
setlocal enabledelayedexpansion
title Music-Automat Local Hub
cd /d "%~dp0"

echo ========================================================
echo       🎧 Starting Music-Automat Channel Hub Server
echo ========================================================
echo.
echo [1/2] Launching browser at http://localhost:8000/ ...
start "Music-Automat Browser" cmd /c "timeout /t 2 >nul & start http://localhost:8000/"

echo [2/2] Starting local authentication server...
python -m uvicorn src.server:app --host 127.0.0.1 --port 8000

pause
