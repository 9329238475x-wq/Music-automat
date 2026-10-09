@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Music-Automat Studio Hub (PC + Mobile Remote Access)
cd /d "%~dp0"

echo ======================================================================
echo       🎧 MUSIC-AUTOMAT STUDIO HUB (PC + MOBILE REMOTE ACCESS)
echo ======================================================================
echo.
echo [1/2] Opening Local Studio Dashboard at http://localhost:8000/ ...
start "Music-Automat Browser" cmd /c "timeout /t 2 >nul & start http://localhost:8000/"

echo [2/2] Starting Server on 0.0.0.0:8000 (Local PC + Mobile Phone + Cloudflare Tunnel)...
echo.
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000

pause
