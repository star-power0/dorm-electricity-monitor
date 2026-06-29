@echo off
setlocal
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
python -m dorm_electricity_monitor.bridge get-state
