# pre_uninstall.ps1 — run by Inno Setup before files are removed
param(
    [string]$ServiceName = "OverallDashboard",
    [int]   $Port        = 8092
)

$winswService = Join-Path $PSScriptRoot "..\nssm\$ServiceName.exe"
if (Test-Path $winswService) {
    & $winswService stop    | Out-Null
    & $winswService uninstall | Out-Null
} else {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
}

# Remove firewall rule
Remove-NetFirewallRule -DisplayName "Overall Programs Dashboard (port $Port)" -ErrorAction SilentlyContinue

Write-Host "Service removed. Data files in C:\ProgramData\OverallDashboard are preserved."
