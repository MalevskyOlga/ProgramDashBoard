# backup_db.ps1
# Safe online backup of dashboards.db and portfolio.db
# Scheduled by the installer to run nightly at 01:00
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File backup_db.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File backup_db.ps1 -BackupRoot "\\fileserver\backups\dashboard"
#
param(
    [string]$DataDir    = "C:\ProgramData\OverallDashboard",
    [string]$BackupRoot = "C:\ProgramData\OverallDashboard\backups",
    [int]   $KeepDays   = 30,
    [int]   $KeepWeeks  = 4
)

$ErrorActionPreference = "Stop"
$PythonExe = "C:\Program Files\OverallDashboard\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }

$Stamp      = Get-Date -Format "yyyyMMdd_HHmm"
$DayOfWeek  = (Get-Date).DayOfWeek   # use Sunday as weekly snapshot

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

# ── SQLite online backup (safe while server is running) ───────────────────────
function Backup-SqliteDb {
    param([string]$SrcPath, [string]$DestPath)

    if (-not (Test-Path $SrcPath)) {
        Write-Host "  SKIP: $SrcPath not found"
        return $false
    }

    $script = @"
import sqlite3, sys
src_path = sys.argv[1]
dst_path = sys.argv[2]
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
src.backup(dst)
dst.close()
src.close()
print('OK')
"@
    $tmp = [System.IO.Path]::GetTempFileName() + ".py"
    $script | Set-Content -Encoding UTF8 -Path $tmp
    $result = & $PythonExe $tmp $SrcPath $DestPath 2>&1
    Remove-Item $tmp -Force
    return ($result -eq "OK")
}

# ── Back up each database ─────────────────────────────────────────────────────
$databases = @("dashboards.db", "portfolio.db")
$errors = @()

foreach ($dbName in $databases) {
    $src      = Join-Path $DataDir $dbName
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($dbName)

    # Daily backup
    $dailyDir = Join-Path $BackupRoot "daily"
    New-Item -ItemType Directory -Force -Path $dailyDir | Out-Null
    $dailyDest = Join-Path $dailyDir "${baseName}_${Stamp}.db"

    Write-Host "Backing up $dbName → $dailyDest"
    $ok = Backup-SqliteDb -SrcPath $src -DestPath $dailyDest
    if ($ok) {
        $sizeMB = [math]::Round((Get-Item $dailyDest).Length / 1MB, 2)
        Write-Host "  ✓ $sizeMB MB"
    } else {
        Write-Host "  ✗ Backup failed for $dbName"
        $errors += $dbName
        continue
    }

    # Weekly backup (every Sunday)
    if ($DayOfWeek -eq "Sunday") {
        $weeklyDir = Join-Path $BackupRoot "weekly"
        New-Item -ItemType Directory -Force -Path $weeklyDir | Out-Null
        $weeklyDest = Join-Path $weeklyDir "${baseName}_weekly_${Stamp}.db"
        Copy-Item $dailyDest $weeklyDest
        Write-Host "  ✓ Weekly snapshot saved"
    }
}

# ── Prune old backups ─────────────────────────────────────────────────────────
$cutoffDaily  = (Get-Date).AddDays(-$KeepDays)
$cutoffWeekly = (Get-Date).AddDays(-($KeepWeeks * 7))

$dailyDir  = Join-Path $BackupRoot "daily"
$weeklyDir = Join-Path $BackupRoot "weekly"

if (Test-Path $dailyDir) {
    $pruned = Get-ChildItem $dailyDir -Filter "*.db" |
              Where-Object { $_.LastWriteTime -lt $cutoffDaily } |
              ForEach-Object { Remove-Item $_.FullName -Force; $_.Name }
    if ($pruned) { Write-Host "Pruned $($pruned.Count) old daily backup(s)" }
}

if (Test-Path $weeklyDir) {
    $pruned = Get-ChildItem $weeklyDir -Filter "*.db" |
              Where-Object { $_.LastWriteTime -lt $cutoffWeekly } |
              ForEach-Object { Remove-Item $_.FullName -Force; $_.Name }
    if ($pruned) { Write-Host "Pruned $($pruned.Count) old weekly backup(s)" }
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
if ($errors.Count -eq 0) {
    Write-Host "Backup complete -- $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    Write-Host "   Daily backups kept: $KeepDays days"
    Write-Host "   Weekly backups kept: $KeepWeeks weeks"
    Write-Host "   Location: $BackupRoot"
    exit 0
} else {
    Write-Host "WARNING: Backup completed with errors: $($errors -join ', ')"
    exit 1
}
