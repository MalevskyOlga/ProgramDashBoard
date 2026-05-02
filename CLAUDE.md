# Claude Code — Project Instructions

## Architecture
- Flask app (`server.py`) on port 5003 (dev) / 8092 (production)
- SQLite database at `database/dashboards.db` (dev) / `C:\ProgramData\OverallDashboard\dashboards.db` (production)
- Windows Service via WinSW; installed by Inno Setup 6
- Active dev branch: `portal`

## Rebuilding the installer
Run from the project root (PowerShell):
```powershell
Remove-Item "installer\Output\OverallDashboardSetup_1.1.0.exe" -Force -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
```
Output: `installer\Output\OverallDashboardSetup_1.1.0.exe`

**When to rebuild:** any change to `server.py`, `templates/`, `config.py`, `db_migrate.py`,
`installer/post_install.ps1`, `installer/setup.iss`, or `migrations/`.

## Running the installer on a target machine
1. Copy `installer\Output\OverallDashboardSetup_1.1.0.exe` to the target machine
2. Right-click → **Run as administrator**
3. Wizard steps:
   - **Install directory** — default `C:\Program Files\OverallDashboard`
   - **Port** — default `8092`
   - **Database** *(upgrade only)*: "Keep production database" (preserves data, runs migrations) or "Replace with bundled database" (backs up first, then overwrites)
4. After install: service starts automatically, dashboard at `http://<server>:<port>`
5. Logs at `C:\ProgramData\OverallDashboard\logs\`

## Adding a Python module
Every `.py` file imported by `server.py` or `aggregate_app.py` must be listed in
`installer/setup.iss` [Files] section. Check with:
```
grep "from .* import\|^import " server.py aggregate_app.py
```
Then add a line like:
```
Source: "{#SrcRoot}\new_module.py"; DestDir: "{app}"; Flags: ignoreversion
```

## Database migrations
When you change the DB schema (add column, create table, etc.):
1. Make the change in the dev DB (`database/dashboards.db`)
2. Create `migrations/NNN_short_description.sql` (next sequential number):
   ```sql
   ALTER TABLE tasks ADD COLUMN my_field TEXT DEFAULT '';
   ```
3. Commit the `.sql` file — `db_migrate.py` runs it automatically on server startup (dev)
   and during installation (production). Already-applied migrations are never re-run.

Migration runner: `db_migrate.py` — tracks applied migrations in `schema_migrations` table.

## Config constants
`post_install.ps1` generates `config.py` at install time. Any new constant added to
`config.py` must also be added to the `$cfgLines` array in `post_install.ps1`, otherwise
production will crash with `AttributeError: module 'config' has no attribute '...'`.

## Version bump
Update `#define AppVersion` in `installer/setup.iss` before distributing a new installer.
