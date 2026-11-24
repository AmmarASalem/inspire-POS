@echo off
rem Run this on a Windows machine WITH internet -- not on the till.
rem
rem Downloads every dependency in requirements.txt as .whl files into
rem deploy\windows\wheels\, so they can be carried to the offline till on the
rem USB stick and installed there with no network. Pillow and pywin32 are
rem compiled wheels, so copying the repo alone is not enough.
rem
rem IMPORTANT: wheels are specific to the Python version and architecture.
rem Download them with the SAME Python major.minor and same 32/64-bit as the
rem till has (start_inspire_debug.bat prints the till's version). Optionally
rem pass a version to target another one, e.g.:
rem
rem     fetch_offline_wheels.bat 312
rem
setlocal EnableDelayedExpansion

set "APPDIR=%~dp0..\.."
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"

set "WHEELDIR=%APPDIR%\deploy\windows\wheels"
set "REQS=%APPDIR%\requirements.txt"
set "PYVER=%~1"

where py >nul 2>&1 && (set "PY=py") || (set "PY=python")

echo Downloading wheels into %WHEELDIR%
%PY% --version
echo.

if "%PYVER%"=="" (
    %PY% -m pip download -r "%REQS%" -d "%WHEELDIR%"
) else (
    rem --python-version needs --only-binary, since pip cannot build a source
    rem package for an interpreter it is not running under.
    echo Targeting Python %PYVER%, 64-bit Windows.
    %PY% -m pip download -r "%REQS%" -d "%WHEELDIR%" --only-binary=:all: --python-version %PYVER% --platform win_amd64
)

if errorlevel 1 (
    echo.
    echo Download FAILED -- nothing was written, or only part of it was.
    pause
    exit /b 1
)

echo.
echo Done. Now copy the whole repo folder ^(including deploy\windows\wheels^)
echo to the till, and run deploy\windows\setup_till.bat there.
pause
