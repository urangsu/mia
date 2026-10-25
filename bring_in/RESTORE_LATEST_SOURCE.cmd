@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install company-approved Python 3.10+ first.
  pause
  exit /b 1
)
py -3 "%~dp0RESTORE_LATEST_SOURCE.py" --verify-only
if errorlevel 1 goto finished
py -3 "%~dp0RESTORE_LATEST_SOURCE.py"
echo.
echo Keep your old data and Excel files. Use the NEW folder printed above.
echo Install in that folder: py -m pip install -r requirements-desktop.txt
echo Then run RUN_GUI.cmd. Company Windows collection still needs validation.
:finished
pause
