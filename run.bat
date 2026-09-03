@echo off
title Telegram Bot Bridge App
cd /d %~dp0

echo ===================================================
echo   Telegram Bot Bridge App Launcher
echo ===================================================
echo.

if not exist .env (
    echo [!] .env file not found. Copying .env.example to .env...
    copy .env.example .env
    echo [!] Please configure your TG_API_ID and TG_API_HASH in .env file first!
    pause
    exit /b
)

if not exist user_session.session (
    echo [*] No saved session found. Running session setup first...
    python setup_session.py
    if errorlevel 1 (
        echo [!] Session setup failed or cancelled.
        pause
        exit /b
    )
)

echo [*] Starting FastAPI Web Server...
start http://127.0.0.1:8000
python app.py

pause
