@echo off
setlocal
title NFL Betting App

cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:8000/"
set "HEALTH_URL=http://127.0.0.1:8000/api/health"
set "PYTHON_EXE=C:\Users\victo\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Python could not be found at:
    echo %PYTHON_EXE%
    echo.
    echo Please ask Codex to update this launcher if Python was moved.
    pause
    exit /b 1
)

powershell.exe -NoProfile -Command "try { $response = Invoke-RestMethod -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($response.status -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>&1

if not errorlevel 1 (
    echo The betting app is already running.
    echo Opening %APP_URL%
    start "" "%APP_URL%"
    timeout /t 2 /nobreak >nul
    exit /b 0
)

echo Starting the NFL Betting App...
echo.
echo The browser will open automatically.
echo Keep this window open while using the app.
echo Press Ctrl+C or close this window to stop the server.
echo.

start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'"

"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo The betting app has stopped.
pause
