@echo off
chcp 65001 >nul
cd /d "%~dp0"
py FastmarketsCollector_v3_5_2.py --export-only
pause
