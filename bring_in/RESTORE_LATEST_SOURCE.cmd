@echo off
setlocal
cd /d "%~dp0" || exit /b 1
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install company-approved Python 3.10+ first.
  pause
  exit /b 1
)
py -3 "%~dp0RESTORE_LATEST_SOURCE.py" "%~dp0MIA_SOURCE_CURRENT.txt" --verify-only
if errorlevel 1 goto failed
py -3 "%~dp0RESTORE_LATEST_SOURCE.py" "%~dp0MIA_SOURCE_CURRENT.txt" --output "%~dp0MIA_Collector_Update"
if errorlevel 1 goto failed
echo.
echo Keep your old data and Excel files. Use the NEW folder printed above.
echo Create a dedicated .venv in the new folder and install requirements-desktop.txt.
echo See MIA_COMPANY_SETUP_GUIDE_KO.txt before running RUN_GUI.cmd.
echo Company Windows collection still needs validation.
pause
exit /b 0
:failed
set "result=%errorlevel%"
echo Restore stopped. Existing folders and data were not overwritten. Read the error above.
pause
exit /b %result%
