@echo off
title CopyRight-Work Pipeline - DJ JAY LAL BARBASPUR
color 0b
cd /d "%~dp0.."

echo ========================================================
echo   CopyRight-Work Pipeline - DJ JAY LAL BARBASPUR
echo ========================================================
echo.
echo [1] Full Run (Scan + Download + Cut + Watermark + Upload)
echo [2] Process Only (No Upload to YouTube)
echo [3] Scan Only (Check latest 2hr+ videos)
echo.
set /p choice="Enter choice (1/2/3) [default: 1]: "

if "%choice%"=="2" (
    python CopyRight-Work\pipeline.py --skip-upload
) else if "%choice%"=="3" (
    python CopyRight-Work\pipeline.py --scan-only
) else (
    python CopyRight-Work\pipeline.py
)

echo.
echo Pipeline finished.
pause

