@echo off
REM Overall Programs Dashboard - Persistent Server Startup
REM This script starts the server in a way that won't crash when code changes

echo ========================================
echo   Overall Programs Dashboard
echo   Persistent Server Mode
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.7+ from python.org
    pause
    exit /b 1
)

echo [INFO] Python found
echo.

REM Change to the script's directory so relative paths work
cd /d "%~dp0"

REM Install dependencies if needed
echo [INFO] Checking dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [WARNING] Some dependencies may not have installed correctly
)

echo.
echo ========================================
echo   Server Configuration:
echo   - URL: http://localhost:5001
echo   - Port: 5001
echo   - Mode: PERSISTENT (No Auto-Reload)
echo   - Debug: OFF (Stable)
echo ========================================
echo.
echo [INFO] Starting server...
echo [INFO] Keep this window OPEN while using
echo [INFO] Press Ctrl+C to stop the server
echo.
echo ========================================
echo.

REM Start server with persistent mode (no auto-reload, no debug)
python server.py

REM If server stops
echo.
echo [INFO] Server stopped
pause
