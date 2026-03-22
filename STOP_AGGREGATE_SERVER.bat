@echo off
REM Programme Portfolio Aggregation Dashboard - Stop Persistent Server

set "NO_PAUSE="

if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
)

echo ========================================
echo   Programme Portfolio Aggregation Dashboard
echo   Stop Server
echo ========================================
echo.
echo [INFO] Stopping aggregate server on port 5002...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$connections=@(Get-NetTCPConnection -LocalPort 5002 -State Listen -ErrorAction SilentlyContinue); $listenerPid=@(); foreach ($connection in $connections) { if ($connection.OwningProcess -and -not ($listenerPid -contains $connection.OwningProcess)) { $listenerPid += $connection.OwningProcess } }; $serverPid=@(); foreach ($proc in @(Get-CimInstance Win32_Process)) { if ($proc.Name -in @('python.exe','pythonw.exe') -and $proc.CommandLine -match 'aggregate_server\.py' -and -not ($serverPid -contains $proc.ProcessId)) { $serverPid += $proc.ProcessId } }; $allPids=@($listenerPid + $serverPid | Select-Object -Unique); if (-not $allPids) { Write-Host '[INFO] No running aggregate server was found.'; exit 0 }; foreach ($procId in $allPids) { Write-Host ('[INFO] Stopping PID ' + $procId); try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch { Write-Host ('[INFO] PID ' + $procId + ' already exited or was not accessible') } }"

if errorlevel 1 (
    echo [ERROR] Failed to stop one or more aggregate server processes
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo [INFO] Aggregate server stopped
if not defined NO_PAUSE pause
