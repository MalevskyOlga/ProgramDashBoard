# Claude Code — Project Instructions

## Architecture
- Flask app (`server.py`) on port 5003 (dev) / 8092 (production)
- Windows Service via WinSW; installed by Inno Setup 6
- Active dev branch: `portal`

### Multi-division (multi-tenant)
- The portal is multi-tenant: each division has its **own** SQLite data DB under
  `database/divisions/<key>.db` (dev) / `<DataDir>\divisions\<key>.db` (prod).
- A **control DB** (`database/control.db` dev / `<DataDir>\control.db` prod) holds
  `users`, `divisions`, `password_resets`. Managed in `tenancy.py`.
- Login (`/login`) puts the user's division in the session; the module-global
  `db_manager` in `server.py` is a `LocalProxy` that resolves to the logged-in
  user's division `DatabaseManager` per request — existing routes are unchanged.
- Roles: `superadmin` (manages all divisions/users via `/admin`, division switcher in
  header) and `user` (one division). Auth gate is `@app.before_request require_login`.
- Self-service password reset: `/forgot-password` emails a link (`mailer.py`, SMTP_*
  in config); if `SMTP_HOST` is blank, super-admin issues a code from `/admin`.
- Fresh install = vanilla: empty control DB + one `admin` super-admin (temp password
  written to `<DataDir>\INITIAL_ADMIN_CREDENTIALS.txt`), zero divisions, zero data.
- Dev seed of division #1 from legacy data: `python scripts/seed_first_division.py`.

## Rebuilding the installer
Run from the project root (PowerShell):
```powershell
Remove-Item "installer\Output\OverallDashboardSetup_1.3.3.exe" -Force -ErrorAction SilentlyContinue
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\setup.iss"
```
Output: `installer\Output\OverallDashboardSetup_1.3.3.exe`

**When to rebuild:** any change to `server.py`, `templates/`, `config.py`, `db_migrate.py`,
`installer/post_install.ps1`, `installer/setup.iss`, or `migrations/`.

## Running the installer on a target machine
1. Copy `installer\Output\OverallDashboardSetup_1.3.3.exe` to the target machine
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
