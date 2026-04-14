@echo off
REM Overall Programs Dashboard - Stop Persistent Server

set "SCRIPT_DIR=%~dp0"
set "NO_PAUSE="

if /I "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
)

echo ========================================
echo   Overall Programs Dashboard
echo   Stop Server
echo ========================================
echo.
echo [INFO] Stopping server on port 5003...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$connections=@(Get-NetTCPConnection -LocalPort 5003 -State Listen -ErrorAction SilentlyContinue); $listenerPid=@(); foreach ($connection in $connections) { if ($connection.OwningProcess -and -not ($listenerPid -contains $connection.OwningProcess)) { $listenerPid += $connection.OwningProcess } }; $launcherPid=@(); $serverPid=@(); foreach ($proc in @(Get-CimInstance Win32_Process)) { if ($proc.Name -eq 'cmd.exe' -and $proc.CommandLine -match 'START_SERVER_PERSISTENT\.bat.*--child' -and -not ($launcherPid -contains $proc.ProcessId)) { $launcherPid += $proc.ProcessId }; if ($proc.Name -in @('python.exe','pythonw.exe') -and $proc.CommandLine -match '(server|unified_server)\.py' -and -not ($serverPid -contains $proc.ProcessId)) { $serverPid += $proc.ProcessId } }; $allPids=@($listenerPid + $launcherPid + $serverPid | Select-Object -Unique); if (-not $allPids) { Write-Host '[INFO] No running dashboard server was found.'; exit 0 }; foreach ($procId in $allPids) { Write-Host ('[INFO] Stopping PID ' + $procId); Stop-Process -Id $procId -Force }"

if errorlevel 1 (
    echo [ERROR] Failed to stop one or more processes
    if not defined NO_PAUSE pause
    exit /b 1
)

echo.
echo [INFO] Dashboard server stopped
if not defined NO_PAUSE pause
