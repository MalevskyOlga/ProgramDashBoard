# Overall Programs Dashboard — Developer Guide

## Installation

### Prerequisites
- Windows 10/11 (64-bit)
- Admin rights on the target machine
- No internet access required (all dependencies bundled)

### Running the installer
1. Copy `installer\Output\OverallDashboardSetup_1.1.0.exe` to the target machine
2. Right-click → **Run as administrator**
3. Follow the wizard:
   - **Install directory** — default: `C:\Program Files\OverallDashboard`
   - **Port** — default: `8092`; change if another service uses it
   - **Database** *(upgrade only, not shown on fresh install)*:
     - **Keep production database** — your live data is preserved; any schema changes are applied automatically
     - **Replace with bundled database** — a timestamped backup (`dashboards.db.bak.YYYYMMDD-HHmmss`) is created in `C:\ProgramData\OverallDashboard\` before replacing
4. The installer installs Python, creates a virtualenv, registers a Windows Service, and opens a firewall rule
5. Access the dashboard at `http://<server-name>:<port>`

### After installation
- Service name: `OverallDashboard` (auto-starts, restarts on failure)
- Logs: `C:\ProgramData\OverallDashboard\logs\`
- Data: `C:\ProgramData\OverallDashboard\dashboards.db`
- Exports: `C:\ProgramData\OverallDashboard\exports\`

### Uninstalling
Use **Add or Remove Programs** → *Overall Programs Dashboard*. The data directory
(`C:\ProgramData\OverallDashboard`) is intentionally preserved on uninstall.

---

## Building the installer (developer)

### Requirements
- Inno Setup 6 installed at `C:\Program Files (x86)\Inno Setup 6\`
- All Python wheels present in `installer\wheels\`
- Python installer at `installer\python-installer.exe`
- WinSW at `installer\nssm\WinSW.exe`

### Build command (PowerShell)
```powershell
Remove-Item "installer\Output\OverallDashboardSetup_1.1.0.exe" -Force -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
```

### Before releasing a new version
1. Update `#define AppVersion` in `installer\setup.iss`
2. Update `OutputBaseFilename` if needed
3. Rebuild, test install on a clean machine

---

## Database migrations

Migrations keep production databases in sync when the schema changes. They are plain SQL
files in the `migrations/` folder, applied automatically on server startup and during
installation.

### When to write a migration
Any time you change the database schema: adding a column, creating a table, adding an index,
changing a default value.

**Do not** write migrations for data-only changes (inserting/updating rows) — those belong
in the dev DB and are deployed via the installer's "Replace with bundled database" option.

### How to write a migration

1. **Name the file** with the next sequential number:
   ```
   migrations/001_add_risk_strategy.sql
   migrations/002_add_outcome_column.sql
   ```

2. **Write safe SQL** — assume the production DB may not have the column yet:
   ```sql
   -- Add strategy field to risks table
   ALTER TABLE risks ADD COLUMN strategy TEXT DEFAULT 'mitigate';
   ```

3. **Commit the file** — `db_migrate.py` will apply it automatically:
   - On server startup (dev environment)
   - During installation (post_install.ps1 calls `db_migrate.py` after deploying the DB)

4. **Verify** — check the `schema_migrations` table in the DB to confirm it was applied:
   ```sql
   SELECT * FROM schema_migrations ORDER BY applied_at;
   ```

### How migrations work
- `db_migrate.py` creates a `schema_migrations` table in the DB on first run
- It scans `migrations/*.sql` files in alphabetical order
- Files already recorded in `schema_migrations` are skipped
- New files are applied with `executescript()` (supports multiple statements) and recorded

### Adding a new config constant
If you add a constant to `config.py`, also add it to the `$cfgLines` array in
`installer\post_install.ps1`. The installer generates `config.py` from scratch — if a
constant is missing there, the production server will crash with `AttributeError`.

---

## Project structure

```
server.py                 Main Flask app (port 5003 dev / 8092 production)
config.py                 Configuration (paths, ports, constants)
database_manager.py       SQLite access layer
db_migrate.py             Migration runner
migrations/               SQL migration files (NNN_description.sql)
database/dashboards.db    Dev database (source of truth for fresh installs)
templates/                Jinja2 HTML templates
installer/
  setup.iss               Inno Setup build script
  post_install.ps1        Post-install script (venv, config, service, migrations)
  pre_uninstall.ps1       Pre-uninstall script (stops service)
  backup_db.ps1           Nightly backup scheduled task script
  wheels/                 Offline pip wheels
  Output/                 Built installer (git-ignored)
```
