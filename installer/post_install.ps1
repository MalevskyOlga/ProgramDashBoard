# post_install.ps1 - run by Inno Setup after files are copied
# Args: -InstallDir <path> -DataDir <path> -Port <number> -ServiceName <name>
param(
    [string]$InstallDir  = "C:\Program Files\OverallDashboard",
    [string]$DataDir     = "C:\ProgramData\OverallDashboard",
    [int]   $Port        = 8092,
    [string]$ServiceName = "OverallDashboard"
)

# -- Log to file from the very first line (before ErrorActionPreference) -------
$LogDir    = "C:\ProgramData\OverallDashboard\logs"
$null      = New-Item -ItemType Directory -Force -Path $LogDir
$LogFile   = Join-Path $LogDir "install-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}
Log "=== post_install.ps1 started ==="
Log "InstallDir=$InstallDir  DataDir=$DataDir  Port=$Port  ServiceName=$ServiceName"

$ErrorActionPreference = "Stop"
trap {
    Log "ERROR: $_"
    Log "=== FAILED ==="
    exit 1
}

$PythonInstaller = Join-Path $InstallDir "installer\python-installer.exe"
$PythonDir       = Join-Path $InstallDir "python"
$PythonExe       = Join-Path $PythonDir  "python.exe"
$VenvDir         = Join-Path $InstallDir ".venv"
$WinSwExe        = Join-Path $InstallDir "nssm\WinSW.exe"
$WheelsDir       = Join-Path $InstallDir "installer\wheels"

# -- 1. Create data & log directories -----------------------------------------
New-Item -ItemType Directory -Force -Path $DataDir                  | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "exports") | Out-Null
Log "[1/7] Data directory ready: $DataDir"

# -- 2. Install Python app-local -----------------------------------------------
Log "[2/7] Installing Python to $PythonDir ..."

# Helper: remove any Python 3.14 MSI components left by previous (partial) installs.
# Without this, the bundle migrates JustForMe→AllUsers and then uninstalls the
# JustForMe packages — wiping the same files it just installed (same TargetDir).
function Invoke-PythonPreclean {
    # Convert a product code GUID to the squished form used by Windows Installer registry
    function Convert-GuidToSquished([string]$Guid) {
        $g = $Guid.ToUpper() -replace '[{}-]', ''
        if ($g.Length -ne 32) { return $null }
        # Segments 1-3: reverse byte pairs; segments 4-5: reverse individual chars
        $s1 = -join ($g[6],$g[7],$g[4],$g[5],$g[2],$g[3],$g[0],$g[1])
        $s2 = -join ($g[10],$g[11],$g[8],$g[9])
        $s3 = -join ($g[14],$g[15],$g[12],$g[13])
        $s4 = -join ($g[19],$g[18],$g[17],$g[16])
        $s5 = -join ($g[31],$g[30],$g[29],$g[28],$g[27],$g[26],$g[25],$g[24],$g[23],$g[22],$g[21],$g[20])
        return $s1 + $s2 + $s3 + $s4 + $s5
    }

    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )
    $found = 0
    foreach ($regPath in $regPaths) {
        if (-not (Test-Path $regPath)) { continue }
        Get-ChildItem $regPath -ErrorAction SilentlyContinue | ForEach-Object {
            $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
            if ($props.DisplayName -match "Python 3\.14") {
                $productCode = $_.PSChildName
                $keyPath     = $_.PSPath
                Log "      Pre-removing: $($props.DisplayName) ($productCode)"
                # MSIFASTINSTALL=7: skip rollback/file-check so uninstall succeeds even with missing files
                $p = Start-Process "msiexec.exe" -ArgumentList "/x `"$productCode`" /quiet /norestart MSIFASTINSTALL=7" -Wait -PassThru
                Log "      msiexec /x exit: $($p.ExitCode)"
                # If msiexec still failed, force-remove registry entries so the WiX bundle
                # doesn't see this package as "Present" on the next run
                if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 1605) {
                    Log "      Force-removing registry entries for: $productCode"
                    Remove-Item $keyPath -Recurse -Force -ErrorAction SilentlyContinue
                    $squished = Convert-GuidToSquished $productCode
                    if ($squished) {
                        @(
                            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\S-1-5-18\Products\$squished",
                            "HKLM:\SOFTWARE\Classes\Installer\Products\$squished"
                        ) | ForEach-Object {
                            if (Test-Path $_) {
                                Remove-Item $_ -Recurse -Force -ErrorAction SilentlyContinue
                                Log "      Removed MSI tracking key: $_"
                            }
                        }
                    }
                }
                $found++
            }
        }
    }

    # Clear Python 3.14 package cache — stale "cached: Complete" entries cause the WiX
    # bundle planner to skip lib_AllUsers (execute: None, uncache: Yes) instead of installing it
    $packageCache = Join-Path $env:ProgramData "Package Cache"
    if (Test-Path $packageCache) {
        Get-ChildItem $packageCache -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $hasPyMsi = Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match "^(core|exe|lib|pip|dev|tcltk|test|doc|launcher)\.msi$" }
            if ($hasPyMsi) {
                Log "      Clearing package cache: $($_.FullName)"
                Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                $found++
            }
        }
        $unverified = Join-Path $packageCache ".unverified"
        if (Test-Path $unverified) {
            Remove-Item $unverified -Recurse -Force -ErrorAction SilentlyContinue
            Log "      Cleared .unverified package cache"
        }
    }

    if ($found -eq 0) {
        Log "      No existing Python 3.14 components found, nothing to pre-clean"
    } else {
        Log "      Pre-clean removed $found Python 3.14 component(s)"
    }
}

# Helper: run the Python installer and return the process
function Invoke-PythonInstaller {
    if (-not (Test-Path $PythonInstaller)) {
        throw "Python installer not found at: $PythonInstaller"
    }
    $msiLog = Join-Path $LogDir "python-msi-install.log"
    $installArgs = "/quiet InstallAllUsers=1 PrependPath=0 Include_test=0 " +
                   "Include_launcher=0 Include_doc=0 Include_tcltk=0 Include_dev=0 " +
                   "TargetDir=`"$PythonDir`" " +
                   "/log `"$msiLog`""
    Log "      Running: $PythonInstaller $installArgs"
    Log "      MSI log will be written to: $msiLog"
    $p = Start-Process -FilePath $PythonInstaller -ArgumentList $installArgs -Wait -PassThru
    Log "      Python installer exit code: $($p.ExitCode)"
    # Exit 1618 = another MSI in progress; wait and retry once
    if ($p.ExitCode -eq 1618) {
        Log "      Exit 1618 - waiting 20s then retrying..."
        Start-Sleep -Seconds 20
        $p = Start-Process -FilePath $PythonInstaller -ArgumentList $installArgs -Wait -PassThru
        Log "      Python installer retry exit code: $($p.ExitCode)"
    }
    # Exit 1603 = fatal MSI error (antivirus, policy, missing prereq)
    if ($p.ExitCode -eq 1603) {
        if (Test-Path $msiLog) {
            $tail = Get-Content $msiLog -ErrorAction SilentlyContinue | Select-Object -Last 20
            Log "      MSI log tail: $($tail -join ' | ')"
        }
        throw "Python installer failed with exit 1603 (fatal MSI error). " +
              "Possible causes: antivirus blocking, Group Policy restriction, or missing VC++ redistributable. " +
              "Check MSI log: $msiLog"
    }
    return $p
}

# Helper: test python.exe without letting stderr trigger $ErrorActionPreference = Stop
function Test-PythonOK {
    $savedPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & $PythonExe -c "print('ok')" 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedPref
    return [PSCustomObject]@{ OK = ($code -eq 0); ExitCode = $code; Output = "$out" }
}

# Check if Python exists AND actually runs (file present doesn't mean install succeeded)
$pythonOK = $false
if (Test-Path $PythonExe) {
    $result = Test-PythonOK
    $pythonOK = $result.OK
    if (-not $pythonOK) {
        Log "      python.exe exists but cannot run (exit $($result.ExitCode)): $($result.Output)"
        Log "      Removing broken Python installation..."
        Remove-Item -Recurse -Force $PythonDir -ErrorAction SilentlyContinue
    }
}

if (-not $pythonOK) {
    Invoke-PythonPreclean
    $proc = Invoke-PythonInstaller
    if (-not (Test-Path $PythonExe)) {
        throw "Python install finished (exit $($proc.ExitCode)) but python.exe not found at: $PythonExe"
    }
    # Final verification
    $result = Test-PythonOK
    if (-not $result.OK) {
        throw "Python installed but cannot run (exit $($result.ExitCode) - likely missing DLLs): $($result.Output)"
    }
    Log "      Python installed and verified OK"
} else {
    Log "      Python already present and working, skipping"
}

# -- 3. Create venv and install dependencies (offline wheels) ------------------
Log "[3/7] Creating virtual environment at $VenvDir ..."
# Stop the service first — running Python locks DLL files inside the venv
$existingSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingSvc -and $existingSvc.Status -ne 'Stopped') {
    Log "      Stopping service '$ServiceName' to release file locks..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
}
# Always remove a stale venv (e.g. from a previous failed install) before recreating
if (Test-Path $VenvDir) {
    Log "      Removing existing venv for clean reinstall..."
    Remove-Item -Recurse -Force $VenvDir
}
& $PythonExe -m venv $VenvDir
if ($LASTEXITCODE -ne 0) { throw "venv creation failed (exit $LASTEXITCODE)" }
Log "      Venv created OK"

Log "      Installing dependencies from bundled wheels..."
if (-not (Test-Path $WheelsDir)) { throw "Wheels folder not found: $WheelsDir" }
$reqFile   = Join-Path $InstallDir "requirements.txt"
$pipLog    = Join-Path $LogDir "pip-install.log"
& "$VenvDir\Scripts\pip.exe" install --no-index --find-links "$WheelsDir" -r "$reqFile" --log "$pipLog" 2>&1 | ForEach-Object { Log "pip: $_" }
if ($LASTEXITCODE -ne 0) {
    Log "      pip failed - full output in: $pipLog"
    throw "pip install failed (exit $LASTEXITCODE) - see $pipLog"
}
Log "      Dependencies installed OK"

$VenvPython = "$VenvDir\Scripts\python.exe"

# -- 4. Write production config.py ---------------------------------------------
Log "[4/7] Writing production config..."
$InstallDirEsc = $InstallDir -replace '\\','\\'
$DataDirEsc    = $DataDir    -replace '\\','\\'
$cfgLines = @(
    '# Production configuration - generated by installer. Do not edit manually.',
    'import os',
    'from pathlib import Path',
    '',
    "SERVER_HOST  = '0.0.0.0'",
    "SERVER_PORT  = $Port",
    'DEBUG_MODE   = False',
    '',
    "BASE_DIR                 = Path(r'$InstallDirEsc')",
    "DATABASE_PATH            = Path(r'$DataDirEsc') / 'dashboards.db'",
    "PORTFOLIO_DATABASE_PATH  = Path(r'$DataDirEsc') / 'portfolio.db'",
    "EXCEL_OUTPUT_FOLDER      = Path(r'$DataDirEsc') / 'exports'",
    '',
    'DB_TIMEOUT = 30',
    '',
    'EXCEL_PROJECT_NAME_ROW = 3',
    "EXCEL_PROJECT_NAME_COL = 'C'",
    'EXCEL_MANAGER_ROW      = 5',
    "EXCEL_MANAGER_COL      = 'C'",
    'EXCEL_HEADER_ROW       = 10',
    'EXCEL_DATA_START_ROW   = 11',
    '',
    'EXCEL_COLUMNS = {',
    "    'reference_id': 'A',",
    "    'name':         'B',",
    "    'phase':        'C',",
    "    'owner':        'D',",
    "    'start_date':   'E',",
    "    'status':       'F',",
    "    'end_date':     'G',",
    "    'date_closed':  'H',",
    "    'result':       'I',",
    '}',
    '',
    'DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)',
    'EXCEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)'
)
$cfgLines -join "`r`n" | Set-Content -Encoding UTF8 -Path (Join-Path $InstallDir 'config.py')
Log "      Config written (port $Port)"

# -- 5. Verify database and seed resource_teams --------------------------------
Log "[5/7] Checking database..."
$dbPath     = Join-Path $DataDir "dashboards.db"
$seedDbPath = Join-Path $InstallDir "installer\seed_dashboards.db"
if (Test-Path $dbPath) {
    Log "      DB found ($([math]::Round((Get-Item $dbPath).Length/1MB,2)) MB)"
} else {
    Log "      WARNING: DB not found - will be created on first start"
}

# Seed resource_teams from the bundled DB if the table is empty (fresh install or upgrade)
if ((Test-Path $dbPath) -and (Test-Path $seedDbPath)) {
    $seedFile = Join-Path $env:TEMP "dashboard_seed.py"
    @'
import sqlite3, sys
db_path, seed_path = sys.argv[1], sys.argv[2]
dst = sqlite3.connect(db_path)
src = sqlite3.connect(seed_path)
dst.execute("""CREATE TABLE IF NOT EXISTS resource_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    owner_name TEXT NOT NULL UNIQUE,
    capacity_hrs_per_week REAL NOT NULL DEFAULT 37.5)""")
count = dst.execute("SELECT COUNT(*) FROM resource_teams").fetchone()[0]
if count == 0:
    rows = src.execute("SELECT owner_name, team_name, capacity_hrs_per_week FROM resource_teams").fetchall()
    for row in rows:
        dst.execute("INSERT OR IGNORE INTO resource_teams (owner_name, team_name, capacity_hrs_per_week) VALUES (?,?,?)", row)
    dst.commit()
    print(f"Seeded {len(rows)} resource_teams rows")
else:
    print(f"resource_teams already has {count} rows, skipping seed")
src.close(); dst.close()
'@ | Set-Content -Encoding UTF8 -Path $seedFile
    try {
        $seedOut = & $VenvPython $seedFile $dbPath $seedDbPath 2>&1 | Out-String
        Log "      DB seed: $seedOut"
    } catch {
        Log "      DB seed warning (non-fatal): $_"
    } finally {
        Remove-Item $seedFile -ErrorAction SilentlyContinue
    }
}

# -- 6. Register Windows service via WinSW ------------------------------------
Log "[6/7] Registering Windows service '$ServiceName'..."

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Log "      Stopping existing service..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    sc.exe delete $ServiceName | Out-Null
    # Wait for service to be fully deleted (up to 15s)
    $waited = 0
    while ((Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) -and $waited -lt 15) {
        Start-Sleep -Seconds 1; $waited++
    }
    Log "      Old service removed (waited ${waited}s)"
}

$xmlPath      = Join-Path $InstallDir "nssm\$ServiceName.xml"
$winswService = Join-Path $InstallDir "nssm\$ServiceName.exe"

# Build XML via array join - avoids here-string PS5.1 parsing issues
$xmlLines = @(
    '<service>',
    "  <id>$ServiceName</id>",
    '  <name>Overall Programs Dashboard</name>',
    "  <description>Web-based project dashboard (Flask, port $Port)</description>",
    "  <executable>$VenvPython</executable>",
    '  <arguments>server.py</arguments>',
    "  <workingdirectory>$InstallDir</workingdirectory>",
    "  <logpath>$LogDir</logpath>",
    '  <logmode>rotate</logmode>',
    '  <sizeThreshold>5120</sizeThreshold>',
    '  <startmode>Automatic</startmode>',
    '  <onfailure action="restart" delay="5 sec"/>',
    '  <onfailure action="restart" delay="10 sec"/>',
    '  <onfailure action="restart" delay="20 sec"/>',
    '</service>'
)
$xmlLines -join "`r`n" | Set-Content -Encoding UTF8 -Path $xmlPath
Copy-Item $WinSwExe $winswService -Force

Log "      Running WinSW install..."
$out = & $winswService install 2>&1
Log "      WinSW output: $out  (exit $LASTEXITCODE)"
if ($LASTEXITCODE -ne 0) { throw "WinSW install failed (exit $LASTEXITCODE)" }

# -- 7. Open firewall & register backup task -----------------------------------
Log "[7/7] Firewall + backup task..."
$ruleName = "Overall Programs Dashboard (port $Port)"
Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP `
    -LocalPort $Port -Action Allow -Profile Domain,Private | Out-Null

$backupScript = Join-Path $InstallDir "installer\backup_db.ps1"
$taskName     = "OverallDashboard_NightlyBackup"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`" -DataDir `"$DataDir`" -BackupRoot `"$DataDir\backups`""
$trigger   = New-ScheduledTaskTrigger -Daily -At "01:00"
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal | Out-Null

# -- Start service -------------------------------------------------------------
Log "Starting service..."
& $winswService start 2>&1 | ForEach-Object { Log "WinSW start: $_" }
Start-Sleep -Seconds 5

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Log "========================================="
    Log "  Installation complete!"
    Log "  Dashboard: http://localhost:$Port"
    Log "  Logs:      $LogDir"
    Log "  Log file:  $LogFile"
    Log "========================================="
    Log "=== SUCCESS ==="
} else {
    $status = if ($svc) { $svc.Status } else { "not found" }
    throw "Service did not start (status: $status). Check $LogDir for WinSW logs."
}
