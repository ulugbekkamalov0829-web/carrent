@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo CarRent: http://localhost:8000
start "" http://localhost:8000
python -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend --port 8000
pause
