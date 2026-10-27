@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -u "%~dp0MIA_Collector.py" %*
) else (
  py -3 -u "%~dp0MIA_Collector.py" %*
)
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
