@echo off
cd /d "%~dp0"
py -u FastmarketsCollector_v3_5_3.py --verify-db
pause
