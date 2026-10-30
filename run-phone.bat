@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo.
echo Telefonda oching (shu Wi-Fi tarmogida):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo    http://%%b:8000
echo.
echo Windows ruxsat so'rasa: "Private networks" ni belgilang.
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
