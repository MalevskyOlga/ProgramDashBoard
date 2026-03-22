@echo off
setlocal
REM Programme Portfolio Aggregation Dashboard - Persistent Server Startup

set "SCRIPT_DIR=%~dp0"
set "PORT=5002"
set "SERVER_URL=http://127.0.0.1:%PORT%"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "STDOUT_LOG=%LOG_DIR%\aggregate.stdout.log"
set "STDERR_LOG=%LOG_DIR%\aggregate.stderr.log"
set "PYTHON_EXE="

cd /d "%SCRIPT_DIR%"

if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

echo ========================================
echo   Programme Portfolio Aggregation Dashboard
echo   Persistent Server Mode
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$existing = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) | Select-Object -First 1; if ($existing) { Write-Host ('[INFO] Aggregate server is already running on PID ' + $existing.OwningProcess); exit 10 }; exit 0"
if errorlevel 10 (
    echo [INFO] Open http://localhost:%PORT%
    exit /b 0
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
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
echo [INFO] Checking dependencies...
"%PYTHON_EXE%" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [WARNING] Some dependencies may not have installed correctly
)

echo.
echo [INFO] Starting aggregate server in background...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$proc = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'aggregate_server.py' -WorkingDirectory '%SCRIPT_DIR%' -WindowStyle Hidden -RedirectStandardOutput '%STDOUT_LOG%' -RedirectStandardError '%STDERR_LOG%' -PassThru; Write-Host ('[INFO] Background aggregate server PID ' + $proc.Id)"
if errorlevel 1 (
    echo [ERROR] Failed to launch aggregate server
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(30); do { try { $response = Invoke-WebRequest -UseBasicParsing '%SERVER_URL%/health' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo [ERROR] Aggregate server did not become ready within 30 seconds
    echo [ERROR] Check logs:
    echo   %STDOUT_LOG%
    echo   %STDERR_LOG%
    pause
    exit /b 1
)

echo.
echo [INFO] Aggregate server is running in background
echo [INFO] URL: http://localhost:%PORT%
echo [INFO] Logs:
echo   %STDOUT_LOG%
echo   %STDERR_LOG%
exit /b 0
