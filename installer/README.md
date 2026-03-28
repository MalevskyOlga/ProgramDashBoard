# Building the Installer

## Prerequisites (dev machine only)

1. **Inno Setup 6** — https://jrsoftware.org/isdl.php  
2. **WinSW** — https://github.com/winsw/winsw/releases  
   Download `WinSW-x64.exe` → rename to `WinSW.exe` → place at `installer\nssm\WinSW.exe`
3. **`.venv` built** — run once from the repo root:
   ```bat
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

## Build the installer

```bat
cd installer
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" setup.iss
```

Output: `installer\Output\OverallDashboardSetup_1.0.0.exe`

## Deploy to production

1. Copy `OverallDashboardSetup_1.0.0.exe` to the server
2. Run as Administrator — the wizard will ask for install path and port
3. The installer will:
   - Copy all app files + bundled Python venv to `C:\Program Files\OverallDashboard\`
   - Create data folder at `C:\ProgramData\OverallDashboard\`
   - Write production `config.py` with the chosen port
   - Initialise the database
   - Register `OverallDashboard` as a Windows Service (auto-start)
   - Open the firewall port

## Upgrading

Run the new installer over the existing installation.  
**The database at `C:\ProgramData\OverallDashboard\dashboards.db` is never touched by the installer.**  
After copying files, any pending schema migrations will be applied automatically.

## Uninstalling

Control Panel → Programs → Overall Programs Dashboard → Uninstall.  
The service is stopped and removed. Data files in `C:\ProgramData\OverallDashboard\` are **preserved**.

## Bumping the version

Edit `setup.iss` line:
```
#define AppVersion "1.0.1"
```
