@echo off
rem Starts the Chatisfying backend on this PC (see README, section "PC server"). Double-click this file.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed. Get it from python.org and tick "Add to PATH". & pause & exit /b 1)
if not exist .venv (
  echo First start: setting things up, this takes a minute...
  python -m venv .venv || (pause & exit /b 1)
  call .venv\Scripts\python -m pip install -r requirements.txt || (pause & exit /b 1)
)
if not exist .env.pc (
  echo The file .env.pc is missing. Copy .env.pc.example to .env.pc and fill it in.
  pause & exit /b 1
)
.venv\Scripts\python pc_agent.py
echo The PC server stopped.
pause
