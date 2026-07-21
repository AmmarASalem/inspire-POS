@echo off
rem Starts the Inspire POS server (if not already running) and opens it
rem full-screen in a kiosk browser window. Safe to run repeatedly: if the
rem server is already up, it just (re)opens the browser.

setlocal EnableDelayedExpansion

set "APPDIR=%~dp0..\.."
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"

set "PYTHONW=%APPDIR%\venv\Scripts\pythonw.exe"
set "URL=http://127.0.0.1:5000/"
set "PROFILE=%APPDIR%\deploy\windows\kiosk-profile"

if not exist "%PYTHONW%" (
    echo Could not find %PYTHONW%
    echo Run the one-time setup first ^(see CLAUDE.md, "Running it on the Windows till machine"^).
    pause
    exit /b 1
)

call :is_up
if "%UP%"=="0" (
    pushd "%APPDIR%"
    start "Inspire POS server" /min "%PYTHONW%" -c "import database; database.init_db(); from app import app; app.run(host='127.0.0.1', port=5000)"
    popd
)

set /a tries=0
:waitloop
call :is_up
if "%UP%"=="1" goto :launchbrowser
set /a tries+=1
if %tries% GEQ 40 (
    echo The server did not respond within 20 seconds.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto :waitloop

:launchbrowser
set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if not exist "%BROWSER%" (
    echo Could not find Chrome or Edge. Install one of them, or open %URL% manually.
    pause
    exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

start "" "%BROWSER%" --kiosk "%URL%" --user-data-dir="%PROFILE%" --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-infobars
exit /b 0

:is_up
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (set "UP=0") else (set "UP=1")
goto :eof
