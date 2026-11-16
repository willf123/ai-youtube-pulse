@echo off
REM Launcher for Windows Task Scheduler. Logs go to .tmp\logs\
cd /d "%~dp0"
if not exist ".tmp\logs" mkdir ".tmp\logs"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set D=%%i
".venv\Scripts\python.exe" tools\run_weekly.py >> ".tmp\logs\run_%D%.log" 2>&1
