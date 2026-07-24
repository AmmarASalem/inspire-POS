@echo off
rem Runs backup_inspire_db.py once. Meant to be triggered on a schedule by
rem Windows Task Scheduler (daily), not the Startup folder — see CLAUDE.md.

set "APPDIR=%~dp0..\.."
for %%I in ("%APPDIR%") do set "APPDIR=%%~fI"

"%APPDIR%\venv\Scripts\python.exe" "%~dp0backup_inspire_db.py"
