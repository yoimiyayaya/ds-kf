@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  Balance Pet V3 launcher.
rem  ASCII only on purpose: cmd.exe parses batch files with the
rem  console code page, CJK text here would break the lines.
rem  Order: py launcher -> python on PATH -> python shipped with DSH.
rem  Every candidate must be able to "import tkinter".
rem ============================================================

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
    echo         Install Python 3.9+ and tick "Add python.exe to PATH",
    echo         then run this file again. See README.md for details.
    echo.
    pause
    exit /b 1
)

rem pythonw.exe = same interpreter without a console window
set "PYW=%PYEXE%"
for %%i in ("%PYEXE%") do if exist "%%~dpi\pythonw.exe" set "PYW=%%~dpi\pythonw.exe"

start "" "%PYW%" "%~dp0balance_pet.py"
exit /b 0
