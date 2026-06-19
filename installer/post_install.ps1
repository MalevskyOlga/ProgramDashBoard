# post_install.ps1 - run by Inno Setup after files are copied
# Args: -InstallDir <path> -DataDir <path> -Port <number> -ServiceName <name>
param(
    [string]$InstallDir   = "C:\Program Files\OverallDashboard",
    [string]$DataDir      = "C:\ProgramData\OverallDashboard",
    [int]   $Port         = 8092,
    [string]$ServiceName  = "OverallDashboard",
    [string]$DbAction     = "replace",  # 'replace' (start fresh) or 'keep' (migrate existing data)
    [string]$FirstDivision = ""         # name for the first division (blank = vanilla/empty)
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

# Force UTF-8 for all Python invocations below. The service console can be a non-UTF-8
# code page (e.g. cp1255), where printing Unicode like the "OK" check mark crashes
# initialize_database() with UnicodeEncodeError and fails the install.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

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

# Helper: run the Python installer and return the process
function Invoke-PythonInstaller {
    if (-not (Test-Path $PythonInstaller)) {
        throw "Python installer not found at: $PythonInstaller"
    }
    $msiLog = Join-Path $LogDir "python-msi-install.log"
    $installArgs = "/quiet InstallAllUsers=1 PrependPath=0 Include_test=0 " +
                   "Include_launcher=0 Include_doc=0 Include_tcltk=0 " +
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

# Check if Python exists AND actually runs (file present doesn't mean install succeeded)
$pythonOK = $false
if (Test-Path $PythonExe) {
    $testOut = & $PythonExe -c "print('ok')" 2>&1
    $pythonOK = ($LASTEXITCODE -eq 0)
    if (-not $pythonOK) {
        Log "      python.exe exists but cannot run (exit $LASTEXITCODE): $testOut"
        Log "      Removing broken Python installation..."
        Remove-Item -Recurse -Force $PythonDir
    }
}

if (-not $pythonOK) {
    $proc = Invoke-PythonInstaller
    if (-not (Test-Path $PythonExe)) {
        throw "Python install finished (exit $($proc.ExitCode)) but python.exe not found at: $PythonExe"
    }
    # Final verification
    $testOut = & $PythonExe -c "print('ok')" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python installed but cannot run (exit $LASTEXITCODE - likely missing DLLs): $testOut"
    }
    Log "      Python installed and verified OK"
} else {
    Log "      Python already present and working, skipping"
}

# -- 3. Create venv and install dependencies (offline wheels) ------------------
Log "[3/7] Creating virtual environment at $VenvDir ..."
# Stop the service and wait for all file locks to be released
$existingSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingSvc -and $existingSvc.Status -ne 'Stopped') {
    Log "      Stopping service '$ServiceName'..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    # Poll until fully stopped (up to 30s)
    $waited = 0
    while ($waited -lt 30) {
        Start-Sleep -Seconds 1; $waited++
        $s = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $s -or $s.Status -eq 'Stopped') { break }
    }
    Log "      Service stopped after ${waited}s"
}
# Kill any Python processes still holding locks inside the venv
Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -like "$InstallDir*" } catch { $false }
} | ForEach-Object {
    Log "      Killing lingering process: $($_.Name) PID=$($_.Id)"
    $_ | Stop-Process -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
# Always remove a stale venv before recreating
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
# Per-install random Flask session signing key (preserve across upgrades if present).
$ExistingCfg = Join-Path $InstallDir 'config.py'
$SecretKey = $null
if (Test-Path $ExistingCfg) {
    $m = Select-String -Path $ExistingCfg -Pattern "^SECRET_KEY\s*=\s*'([^']+)'" -ErrorAction SilentlyContinue
    if ($m) { $SecretKey = $m.Matches[0].Groups[1].Value }
}
# Never reuse the dev placeholder key (it would let dev session cookies validate in prod
# and is shared/insecure). Force a fresh random key in that case.
if ($SecretKey -eq 'dev-only-insecure-secret-change-me') { $SecretKey = $null }
if (-not $SecretKey) {
    $SecretKey = ([System.Guid]::NewGuid().ToString('N') + [System.Guid]::NewGuid().ToString('N'))
}
# Server hostname for password-reset links emailed to users (must NOT be localhost,
# or recipients on other machines get an unreachable link). Prefer the machine FQDN.
try {
    $SrvHost = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
} catch {
    $SrvHost = $env:COMPUTERNAME
}
if (-not $SrvHost) { $SrvHost = 'localhost' }
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
    "CONTROL_DATABASE_PATH    = Path(r'$DataDirEsc') / 'control.db'",
    "DIVISIONS_DIR            = Path(r'$DataDirEsc') / 'divisions'",
    "EXCEL_OUTPUT_FOLDER      = Path(r'$DataDirEsc') / 'exports'",
    "ATTACHMENTS_DIR          = Path(r'$DataDirEsc') / 'attachments'",
    '',
    "SECRET_KEY = '$SecretKey'",
    'RESET_TOKEN_TTL_MINUTES = 60',
    '',
    "# Password-reset email via Emerson internal relay (unauthenticated, port 25, no TLS).",
    "# Set SMTP_HOST blank to disable email (admin-issued reset codes only).",
    "SMTP_HOST = 'INETMAIL.EMRSN.NET'",
    'SMTP_PORT = 25',
    'SMTP_USE_TLS = False',
    "SMTP_USER = ''",
    "SMTP_PASSWORD = ''",
    "SMTP_FROM = 'OverallDashboard-noreply@emerson.com'",
    "APP_BASE_URL = 'http://${SrvHost}:$Port'",
    '',
    'DB_TIMEOUT = 30',
    'RESOURCE_LOAD_LOOKBACK_MONTHS = 6',
    'PM_LOAD_PER_PROJECT = 5',
    'FULL_TIME_CAPACITY_HRS = 37.5',
    'OVERLOAD_TASK_THRESHOLD = 5',
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
    'EXCEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)',
    'CONTROL_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)',
    'DIVISIONS_DIR.mkdir(parents=True, exist_ok=True)',
    'ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)'
)
$cfgLines -join "`r`n" | Set-Content -Encoding UTF8 -Path (Join-Path $InstallDir 'config.py')
Log "      Config written (port $Port)"

# -- 5. Database: in multi-tenant mode dashboards.db is only a MIGRATION SOURCE --
# 'keep'    -> preserve an existing single-tenant dashboards.db so step 5c can migrate
#              its data into the first division.
# 'replace' -> back up and clear it, so the install starts empty (vanilla).
Log "[5/7] Database setup (action: $DbAction)..."
$TargetDb = Join-Path $DataDir "dashboards.db"
if ($DbAction -eq 'replace') {
    if (Test-Path $TargetDb) {
        $BackupName = "dashboards.db.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $TargetDb (Join-Path $DataDir $BackupName) -Force
        Remove-Item $TargetDb -Force
        Log "      Backed up and cleared existing single-tenant DB (starting fresh)."
    } else {
        Log "      No existing DB - starting fresh."
    }
} else {
    if (Test-Path $TargetDb) {
        Log "      Keeping existing single-tenant DB to migrate into the first division."
    } else {
        Log "      No existing DB found (nothing to migrate)."
    }
}

# -- 5b. Bootstrap control DB (users/divisions) + initial super-admin ----------
# Admin email is read from a file (handles any address safely) and used to seed the
# super-admin on a fresh install, or backfill an emailless admin on upgrade -- so the
# admin can self-serve a password reset via "Forgot your password?".
$adminEmail = ""
$adminEmailFile = Join-Path $DataDir 'admin_email.txt'
if (Test-Path $adminEmailFile) {
    # File may be empty (the installer skips the email page when an admin already
    # exists). Get-Content -Raw returns $null for an empty file, and .Trim() on $null
    # throws, so guard on truthiness before trimming.
    $rawEmail = Get-Content $adminEmailFile -Raw
    if ($rawEmail) { $adminEmail = $rawEmail.Trim() }
}
Log "      Bootstrapping control database... (admin email: '$adminEmail')"
# Build args as an array and only pass --admin-email when we actually have one.
# Windows PowerShell drops empty-string arguments to native exes, which would turn
# `--admin-email ""` into a bare `--admin-email` and break argparse. The script
# defaults the email to '' anyway, so omitting the flag is equivalent.
$bootstrapArgs = @((Join-Path $InstallDir "scripts\bootstrap_control.py"), '--admin-username', 'admin')
if ($adminEmail) { $bootstrapArgs += @('--admin-email', $adminEmail) }
$bootstrapOut = & $VenvPython @bootstrapArgs 2>&1
$bootstrapOut | ForEach-Object { Log "control: $_" }
Remove-Item $adminEmailFile -Force -ErrorAction SilentlyContinue
# If a fresh super-admin was created, persist its temp password where the operator can find it.
$adminLine = $bootstrapOut | Where-Object { $_ -match 'Password\s*:' } | Select-Object -First 1
if ($adminLine) {
    $credFile = Join-Path $DataDir "INITIAL_ADMIN_CREDENTIALS.txt"
    $dashUrl  = "http://${SrvHost}:$Port"
    @(
        "Overall Programs Dashboard - initial administrator account",
        "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "",
        "Open the dashboard:  $dashUrl",
        "  (on this machine you can also use http://localhost:$Port)",
        "",
        "Username : admin",
        ($adminLine.Trim()),
        "Email    : $(if ($adminEmail) { $adminEmail } else { '(none set)' })",
        "",
        "FIRST SIGN-IN:",
        "  1. Open the dashboard URL above and sign in with the username/password.",
        "  2. You'll be prompted to set your own password.",
        "",
        "FORGOT YOUR PASSWORD LATER?",
        $(if ($adminEmail) {
            "  Go to the login page, click 'Forgot your password?', and enter $adminEmail." } else {
            "  No email was set, so self-service reset is unavailable. Re-run the installer to set one." }),
        "",
        "After signing in, create your divisions and users from the Admin page.",
        "(Every user you create needs an email so they can self-reset too.)"
    ) -join "`r`n" | Set-Content -Encoding UTF8 -Path $credFile
    Log "      Initial admin credentials written -> $credFile"
}

# -- 5c. First-division setup: migrate existing data or create a named division
# The division name is read from a file written by the installer (handles '&'/spaces safely).
$divFile = Join-Path $DataDir 'first_division.txt'
if (Test-Path $divFile) {
    # File is empty when the operator left the division name blank ("start empty").
    # Get-Content -Raw returns $null for an empty file and .Trim() on $null throws,
    # so guard on truthiness before trimming.
    $rawDiv = Get-Content $divFile -Raw
    if ($rawDiv) { $FirstDivision = $rawDiv.Trim() }
}
Log "      First-division setup (name: '$FirstDivision')..."
# Same empty-arg guard as the admin email above: only pass --name when non-empty
# (the script treats a missing/blank name as a vanilla, empty start).
$divArgs = @((Join-Path $InstallDir "scripts\migrate_to_division.py"))
if ($FirstDivision) { $divArgs += @('--name', $FirstDivision) }
& $VenvPython @divArgs 2>&1 |
    ForEach-Object { Log "division: $_" }
Remove-Item $divFile -Force -ErrorAction SilentlyContinue

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

# Build WinSW XML - all double-quoted to avoid PS5.1 quirk with '<' in single-quoted strings
$xmlLines = @(
    "<service>",
    "  <id>$ServiceName</id>",
    "  <name>Overall Programs Dashboard</name>",
    "  <description>Web-based project dashboard (Flask, port $Port)</description>",
    "  <executable>$VenvPython</executable>",
    "  <arguments>server.py</arguments>",
    "  <workingdirectory>$InstallDir</workingdirectory>",
    "  <logpath>$LogDir</logpath>",
    "  <logmode>rotate</logmode>",
    "  <sizeThreshold>5120</sizeThreshold>",
    "  <startmode>Automatic</startmode>",
    "  <onfailure action=`"restart`" delay=`"5 sec`"/>",
    "  <onfailure action=`"restart`" delay=`"10 sec`"/>",
    "  <onfailure action=`"restart`" delay=`"20 sec`"/>",
    "</service>"
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
