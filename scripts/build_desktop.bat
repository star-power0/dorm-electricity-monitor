@echo off
setlocal
cd /d "%~dp0\..\desktop"

if not exist "node_modules" (
  call npm install
)

call npm run dist
