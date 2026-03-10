# Create Desktop Shortcut for Overall Programs Dashboard
$TargetPath = "C:\Users\omalevsky\OneDrive - Emerson\Documents\AI Projects\Overall programs dashboard\START_SERVER_PERSISTENT.bat"
$ShortcutPath = "$env:USERPROFILE\Desktop\Overall Programs Dashboard.lnk"
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = "C:\Users\omalevsky\OneDrive - Emerson\Documents\AI Projects\Overall programs dashboard"
$Shortcut.Description = "Start Overall Programs Dashboard (Port 5001)"
$Shortcut.IconLocation = "imageres.dll,3"
$Shortcut.Save()

Write-Host "✓ Desktop shortcut created: Overall Programs Dashboard"
Write-Host "  Location: $ShortcutPath"
Write-Host "  Target: $TargetPath"
