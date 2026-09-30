@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Balance Pet V3 self-check (ASCII only, see launcher notes).
rem  Prints Python / tkinter / artwork / config / API status and
rem  keeps the window open so you can actually read it.
rem  chcp 65001 matches the UTF-8 text that balance_pet.py prints.
rem ============================================================

chcp 65001 >nul

set "PYEXE="

for /f "delims=" %%i in ('py -3 -c "import tkinter,sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"

if not defined PYEXE (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYEXE (
            "%%i" -c "import tkinter" >nul 2>nul
            if not errorlevel 1 set "PYEXE=%%i"
        )
    )
)

if not defined PYEXE if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYEXE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if not defined PYEXE (
    echo [ERROR] No Python interpreter with tkinter was found.
    echo         Install Python 3.9+ and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo interpreter: %PYEXE%
echo.
"%PYEXE%" "%~dp0balance_pet.py" --check --pause
