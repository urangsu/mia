@echo off
setlocal
py -3 "%~dp0RESTORE_DOM_V4.py" %*
if errorlevel 1 (
  echo [MIA DOM V4] Restore failed. See message above.
)
pause
