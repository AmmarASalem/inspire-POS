@echo off
rem Diagnostic only -- NOT part of the normal deploy flow.
rem Runs the POS server in the FOREGROUND using python.exe (not pythonw.exe),
rem so a startup error prints here instead of vanishing into a windowless
rem pythonw process. Use this once to find out why start_inspire.bat isn't
rem bringing the server up, then go back to the normal Startup/.vbs setup.

setlocal EnableDelayedExpansion

set "APPDIR=%~dp0..\.."
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"

set "PYTHON=%APPDIR%\venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Could not find %PYTHON%
    echo Run the one-time setup first ^(see CLAUDE.md, "Running it on the Windows till machine"^).
    pause
    exit /b 1
)

pushd "%APPDIR%"
echo Starting server in the foreground -- Ctrl+C to stop.
echo If startup fails, the real error prints below.
echo.
"%PYTHON%" -c "import database; database.init_db(); from app import app; app.run(host='127.0.0.1', port=5000)"
popd

echo.
echo Server process exited.
pause
