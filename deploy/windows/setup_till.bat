@echo off
rem One-time setup on the till machine: creates venv\ and installs the
rem dependencies. Run this ONCE per till (or after wiping venv\), then use the
rem Startup-folder shortcut to start_inspire_silent.vbs as normal.
rem
rem venv\ is gitignored and a virtualenv is not portable between machines, so
rem copying the repo folder across never brings a working one with it -- this
rem step is what people miss, and the symptom is the launcher doing nothing.
rem
rem Works offline if deploy\windows\wheels\ has been populated first by running
rem fetch_offline_wheels.bat on an internet-connected machine. The till has no
rem internet, so on a real till that is the only path that works.

setlocal EnableDelayedExpansion

set "APPDIR=%~dp0..\.."
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"

set "WHEELDIR=%APPDIR%\deploy\windows\wheels"
set "VENVPY=%APPDIR%\venv\Scripts\python.exe"

echo ===============================================================
echo  Inspire POS -- one-time till setup
echo  App folder: %APPDIR%
echo ===============================================================
echo.

where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed.
    echo.
    echo Install it from python.org, ticking "Add Python to PATH" in the
    echo installer, then run this script again. On an older Windows 10 build
    echo the newest installer may refuse to run -- use Python 3.12 in that case.
    pause
    exit /b 1
)
echo Using Python:
%PY% --version
echo.

if exist "%VENVPY%" (
    echo venv already exists at %APPDIR%\venv -- reusing it.
) else (
    echo Creating venv...
    pushd "%APPDIR%"
    %PY% -m venv venv
    popd
    if not exist "%VENVPY%" (
        echo.
        echo FAILED to create the venv. The error above is the reason.
        pause
        exit /b 1
    )
)
echo.

if exist "%WHEELDIR%\*.whl" (
    echo Installing from local wheels -- no internet needed.
    "%VENVPY%" -m pip install --no-index --find-links="%WHEELDIR%" -r "%APPDIR%\requirements.txt"
) else (
    echo No wheels in %WHEELDIR%, installing from the internet instead.
    echo (If this machine is the offline till, stop: run fetch_offline_wheels.bat
    echo  on a connected machine and bring the wheels folder over on the USB stick.)
    "%VENVPY%" -m pip install -r "%APPDIR%\requirements.txt"
)

if errorlevel 1 (
    echo.
    echo Install FAILED. If it says "no matching distribution", the wheels were
    echo downloaded for a different Python version or architecture than the one
    echo above -- re-run fetch_offline_wheels.bat against a matching Python.
    pause
    exit /b 1
)
echo.

echo Verifying...
"%VENVPY%" -c "import flask, PIL, escpos; print('    OK -- Flask, Pillow and python-escpos all import')"
if errorlevel 1 (
    echo    Something is still missing -- see the error above.
    pause
    exit /b 1
)

echo.
echo ===============================================================
echo  Setup complete. Next:
echo    1. Double-click deploy\windows\start_inspire.bat to check it comes up.
echo    2. Win+R -^> shell:startup -^> put a shortcut to
echo       deploy\windows\start_inspire_silent.vbs there (auto-start on boot).
echo ===============================================================
pause
