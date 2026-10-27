@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] py.exe Python Launcher not found. Install approved Python 3.
  pause
  exit /b 2
)
py -3 "%~dp0RESTORE_MIA_FROM_TXT.py" %*
set "rc=%errorlevel%"
echo.
pause
exit /b %rc%
