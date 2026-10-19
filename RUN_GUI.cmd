@echo off
cd /d "%~dp0"
py -u FastmarketsCollector_v3_7.py
if errorlevel 1 pause
