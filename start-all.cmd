@echo off
cd /d "%~dp0"
echo Starting Jaycode at http://127.0.0.1:8100/
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
