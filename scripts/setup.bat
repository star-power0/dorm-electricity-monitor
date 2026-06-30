@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv" (
  py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e .

if not exist "desktop\node_modules" (
  cd desktop
  npm install
  cd ..
)

echo Setup completed.
echo Edit config.json and run scripts\run_desktop_dev.bat or use scripts\run.bat.
