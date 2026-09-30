@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Create a desktop shortcut for Balance Pet V3.
rem  ASCII only; the real work is done by make_shortcut.ps1.
rem ============================================================

where powershell >nul 2>nul
if errorlevel 1 (
    echo [ERROR] powershell.exe not found. Create the shortcut by hand:
    echo         right click the .vbs launcher -^> Send to -^> Desktop
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1"
echo.
pause
