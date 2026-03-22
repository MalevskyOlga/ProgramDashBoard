@echo off
setlocal
REM Overall Programs Dashboard - Persistent Server Startup
REM This script starts the server as a detached background process.

set "SCRIPT_DIR=%~dp0"
set "PORT=5001"
set "SERVER_URL=http://127.0.0.1:%PORT%"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "STDOUT_LOG=%LOG_DIR%\server.stdout.log"
set "STDERR_LOG=%LOG_DIR%\server.stderr.log"
set "PYTHON_EXE="

cd /d "%SCRIPT_DIR%"

if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

echo ========================================
echo   Overall Programs Dashboard
echo   Persistent Server Mode
echo ========================================
echo.

REM Check whether the server is already running
powershell -NoProfile -ExecutionPolicy Bypass -Command "$existing = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) | Select-Object -First 1; if ($existing) { Write-Host ('[INFO] Dashboard server is already running on PID ' + $existing.OwningProcess); exit 10 }; exit 0"
if errorlevel 10 (
    echo [INFO] Open http://localhost:%PORT%
    exit /b 0
)
if errorlevel 1 (
    echo [WARNING] Could not verify whether port %PORT% is already in use
    echo.
)

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.7+ from python.org
    pause
    exit /b 1
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Command python).Source"`) do set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
    set "PYTHON_EXE=python"
)

echo [INFO] Python found
echo [INFO] Using Python: %PYTHON_EXE%
echo.

REM Install dependencies if needed
echo [INFO] Checking dependencies...
"%PYTHON_EXE%" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [WARNING] Some dependencies may not have installed correctly
)

echo.
echo ========================================
echo   Server Configuration:
echo   - URL: http://localhost:%PORT%
echo   - Port: %PORT%
echo   - Mode: PERSISTENT BACKGROUND
echo   - Debug: OFF (Stable)
echo ========================================
echo.
echo [INFO] Starting server in background...

REM Launch a detached Python process and capture logs for diagnostics
powershell -NoProfile -ExecutionPolicy Bypass -Command "$proc = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'server.py' -WorkingDirectory '%SCRIPT_DIR%' -WindowStyle Hidden -RedirectStandardOutput '%STDOUT_LOG%' -RedirectStandardError '%STDERR_LOG%' -PassThru; Write-Host ('[INFO] Background server PID ' + $proc.Id)"
if errorlevel 1 (
    echo [ERROR] Failed to launch background server process
    pause
    exit /b 1
)

REM Wait for HTTP readiness
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(30); do { try { $response = Invoke-WebRequest -UseBasicParsing '%SERVER_URL%' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo [ERROR] Server did not become ready within 30 seconds
    echo [ERROR] Check logs:
    echo   %STDOUT_LOG%
    echo   %STDERR_LOG%
    pause
    exit /b 1
)

echo.
echo [INFO] Server is running in background
echo [INFO] URL: http://localhost:%PORT%
echo [INFO] Logs:
echo   %STDOUT_LOG%
echo   %STDERR_LOG%
echo [INFO] Use STOP_SERVER.bat to stop it
exit /b 0
