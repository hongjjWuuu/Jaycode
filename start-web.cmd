@echo off
cd /d "%~dp0web"
where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Install Node.js 18+ first.
  exit /b 1
)
npm run dev -- --host 127.0.0.1 --port 5173
