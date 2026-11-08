# Project Management Tool — Full Documentation

**Version:** 1.3.14 (installer) · **Date:** 2026-11-08 · **Branch:** `portal`
**Audience:** developers, administrators, and programme/project managers who use the tool.

This document describes what the tool does, how it is built, where each feature lives in the code, and how to run, configure, test and release it.

---

## 1. Purpose

The tool manages a portfolio of programmes/projects for one or more **divisions** (for example *Flame & Gas* and *Measurement Solutions*). It provides:

- a **portfolio view** of all projects, gates and critical path (Overall Program Dashboard);
- a **priority pipeline** of projects to be started, held, or completed;
- a **resource-load** view of who is working on what, and when;
- a **detailed Gantt / task dashboard** per project (tasks, sub-tasks, dependencies, gates, sign-offs, baselines, risks, comments, attachments);
- **exports** to PowerPoint, Excel and standalone HTML;
- **multi-division administration** with role-based access.

---

## 2. Architecture

| Layer | Files | Notes |
|---|---|---|
| Web server | `server.py` (Flask, ~100 routes) | Single app; serves HTML pages and JSON APIs. Port **5003** in development (`config.py`), **8092** in production (installer default). Bound to `127.0.0.1`. |
| Data access | `database_manager.py` | SQLite access for one division's data (projects, tasks, gates, dependencies, risks, comments, attachments, archive). |
| Tenancy / auth | `tenancy.py` | Control database (`control.db`: divisions, users, password-reset tokens). Resolves each logged-in user's division database. |
| Pages | `templates/index.html` (Overall Program Dashboard), `templates/dashboard.html` (project Gantt/task dashboard), `templates/disciplines.html`, `templates/admin.html`, `templates/manage_users.html`, `templates/project_schematic.html`, login/password templates | Server-rendered shells with large inline JavaScript. |
| Exporters | `ppt_exporter.py`, `portfolio_ppt_exporter.py`, `gantt_ppt_exporter.py`, `risk_ppt_exporter.py`, `resource_ppt_exporter.py`, `excel_exporter.py`, `risk_excel_exporter.py` | python-pptx / openpyxl based. |
| Import | `excel_parser.py`, `risk` import in `server.py` | Reads project Gantt Excel files and risk-register Excel files. |
| Email | `mailer.py` | SMTP for password-reset emails; falls back to a super-admin-issued code when SMTP is not set. |
| Migrations | `db_migrate.py`, `migrations/*.sql` | Numbered SQL migrations, tracked in `schema_migrations`. |
| Portfolio aggregate | `aggregate_server.py`, `aggregate_app.py`, `aggregate_db.py`, `aggregate_repository.py`, `aggregate_config.py` | Separate small app on port **5002** with its own portfolio database (`portfolio.db`). Shipped in the installer. |
| Installer / service | `installer/setup.iss` (Inno Setup), `installer/post_install.ps1`, `installer/pre_uninstall.ps1`, `installer/backup_db.ps1`, WinSW service wrapper | Installs Python dependencies from `installer/wheels`, writes `config.py`, registers the Windows service. |

### 2.1 Data storage

| Item | Location (dev) | Location (production) |
|---|---|---|
| Control database | `database/control.db` | `<DataDir>\control.db` |
| Division databases | `database/divisions/<key>.db` | `<DataDir>\divisions\<key>.db` |
| Attachments | `database/attachments/` | `ATTACHMENTS_DIR` |
| Exports | `exports/` | `EXCEL_OUTPUT_FOLDER` |
| Logs | `logs/` | `C:\ProgramData\OverallDashboard\logs\` |
| Initial admin password | — | `<DataDir>\INITIAL_ADMIN_CREDENTIALS.txt` (fresh install) |

Each division has its own database, so divisions are fully separated. A fresh install creates an empty control database with one `admin` super-admin, zero divisions and zero data.

---

## 3. Running the tool

### 3.1 Development

```powershell
cd "<project folder>"
python server.py          # http://localhost:5003
```

- Dev seed of division #1 from legacy data: `python scripts/seed_first_division.py`.
- Log output goes to the console (or the file you redirect to).

### 3.2 Production (installed)

1. Copy `OverallDashboardSetup_<version>.exe` to the server.
2. Right-click → **Run as administrator**.
3. Wizard: install directory (default `C:\Program Files\OverallDashboard`), port (default `8092`), and — on an upgrade only — database handling: *Keep production database* (runs migrations) or *Replace with bundled database* (backs up first).
4. The service `OverallDashboard` starts automatically. Open `http://<server>:<port>`.

### 3.3 Configuration

All settings live in `config.py` (generated at install time by `installer/post_install.ps1`).

| Constant | Purpose |
|---|---|
| `SERVER_HOST`, `SERVER_PORT` | Bind address and port (dev 5003). |
| `DEBUG_MODE` | Must stay `False`. |
| `CONTROL_DATABASE_PATH`, `DIVISIONS_DIR`, `DATABASE_PATH`, `PORTFOLIO_DATABASE_PATH` | Database locations. |
| `SECRET_KEY` | Flask session key. **Development default — must be changed for production.** |
| `RESET_TOKEN_TTL_MINUTES` | Password-reset link/code lifetime (60). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Reset e-mail. Blank host disables e-mail. |
| `APP_BASE_URL` | Base URL used in reset links. |
| `EXCEL_OUTPUT_FOLDER`, `ATTACHMENTS_DIR` | Output and attachment folders. |
| `DB_TIMEOUT` | SQLite busy timeout (30 s). |
| `PM_LOAD_PER_PROJECT` | Task-equivalent weight per managed project for PM overhead (5). |
| `FULL_TIME_CAPACITY_HRS` | Baseline weekly hours (37.5). |
| `OVERLOAD_TASK_THRESHOLD` | Concurrent tasks at which an owner counts as overloaded (5). |
| `RESOURCE_LOAD_LOOKBACK_MONTHS` | Tasks that ended more than this many months ago are excluded from load (6). |
| `EXCEL_*` | Cell positions and column letters for the Gantt Excel import (see §11). |

**Rule:** every new constant added to `config.py` must also be added to the `$cfgLines` array in `installer/post_install.ps1`, otherwise production fails with `AttributeError`.

---

## 4. Users, roles and access

| Role | Scope | Can do |
|---|---|---|
| `superadmin` | All divisions | Everything, including `/admin` (divisions, users, roles, backup download) and the division switcher in the header. |
| `division_admin` | One division | Manage users of their own division at `/manage-users` (create, enable/disable, reset code, move between `user` and `viewer`). |
| `user` | One division | Full read/write on the division's projects and pipeline. |
| `viewer` | One division | Read-only. Any POST/PUT/DELETE/PATCH is refused by the server, and write controls are hidden in the UI. |

**Authentication**

- Login at `/login`; logout at `/logout`.
- `require_login` (a `before_request` gate in `server.py`) protects every page and API except the public login and reset endpoints.
- Users with `must_change_password` are sent to `/change-password` after login.
- Self-service password reset: `/forgot-password` sends an e-mailed link; if SMTP is not configured, a super-admin issues a code from `/admin`; the user enters it at `/reset-password`.

**Division switching:** superadmins choose a division in the header drop-down (`POST /admin/switch-division`). Every page and export then uses that division's database. Export file names carry the division name.

---

## 5. Overall Program Dashboard (`/`, `templates/index.html`)

The home page shows the whole portfolio for the logged-in division.

### 5.1 Header

- **📤 Export HTML** — downloads a standalone, offline copy of the dashboard named `Overall Program Dashboard - <Division> - <YYYY-MM-DD>.html`. The copy contains all four tabs, the pipeline and the resource data, and is read-only.
- Division switcher (superadmin only), user name, Admin / Manage Users / Sign out links.

### 5.2 Tabs

| Tab | Content |
|---|---|
| **Portfolio Schedule Overview** | Gate timeline for every project (done, passed with rework, planned, rework sign-off, today line). Export to PPT. |
| **Pipeline** | Priority project list (§6). |
| **Overall Resource Load** | Owner workload and monthly views (§7). |
| **Critical Path** | Projects ordered by Gate 5 / next gate, with critical-task counts and delays. Uses a manually set Gate 5 date when one is entered in the project header. |
| *Projects* | Present in the page but hidden on purpose. |

### 5.3 Other items

- Force Refresh (clears cache and reloads).
- The active tab is remembered in the browser.
- Projects with the **Completed** status are moved to the archive (§6.4).

---

## 6. Pipeline (priority projects)

Pipeline data is stored in `priority_projects` (division database) and archived projects in `archived_projects`.

### 6.1 Table

Columns: `#` (priority), Project Name, Leader, Type (NPD / N/A / Cert / OBS / EWR / Applications), Next Gate (N/A, Gate 1–5, Gate C/D), Target Date, Objective (Growth / Maintain / Discontinue), Segment (Industrial / Suppression / All), Category, Risk, Actions.

### 6.2 Categories (tabs)

Active Big (> 80 h), Active Small (< 80 h), Planned & On Hold, Proposed. Changing a project's category moves it to that tab.

### 6.3 Editing

- Name, leader, target date and the drop-downs are editable inline (click the cell; Enter saves; Esc reverts).
- **Edit** button opens a dialog with all the fields above; only changed fields are saved.
- Drag a row to reorder, or use ▲ / ▼.
- Each row can link to a Gantt dashboard, import a Gantt from Excel, or start from an NPD template (the ⬇ menu).
- Risk badge opens that project's risk panel (§9).

### 6.4 Complete and archive

- **✓ Mark Complete** moves the project to **Completed Projects** (archive section). **↩ Undo** restores it.
- Pipeline completion is gated on open Gantt tasks.

---

## 7. Overall Resource Load (Overall Program Dashboard tab)

Source: `/api/overall-resource-load` (owners and their tasks, with working days, concurrent load, delays, status lag), `/api/discipline-resource-load`, `/api/resource-project-matrix`.

### 7.1 Summary

- **Health tile (RAG):** Healthy / At Risk / Critical, from the share of delayed owners and the number of overloaded owners.
- **Four tiles:** on track, delayed, overloaded, all owners.
- **Quick-access bar (main views):** 📊 Load chart · 🏢 By Discipline · 🌡️ Load heatmap · 📦 By Project · 🏷️ Discipline map (opens `/disciplines`).
- **▸ More views (collapsible):** Juggling 2+ today · Delayed owners · Active today · ⚠ Status lag · 📋 Effort matrix. The group opens automatically when one of its views is active.

### 7.2 Views

- **Owners table:** top 10 owners, "more owners" toggle, filters per column, project list per owner.
- **Load chart:** owners ranked by effective concurrent load against the overload threshold.
- **Load heatmap (monthly):** overlapping tasks per owner per month (completed/cancelled tasks ignored), coloured by share of the busiest cell.
- **By Discipline:** tasks per discipline per month, against owner count; mapping is maintained in `/disciplines`.
- **By Project:** priority projects × disciplines with staffing coverage (Fully / Partially / No / N/A; "always staffed" projects show Fully).
- **Owner detail:** click an owner name to see all their tasks (project, phase, task, dates, status, working days, delay flag). Individual tasks and "all tasks" can be ticked for the PowerPoint builder.
- **Effort matrix:** the view is labelled "Effort matrix" but currently shows the working-day sections (the `task-matrix` mode is not reached from the buttons).

### 7.3 PowerPoint builder

A bar above the quick-access buttons:

- Tick sections: 📊 Load chart, 🌡️ Monthly load heatmap, 🏢 By discipline, 📦 By project.
- Tick tasks on an owner's page (single tasks or all of them).
- **⬇ Export PPT** posts the selection to `POST /api/resource-load/export-ppt`, which builds `Resource Load - <Division> - <date>.pptx`:
  - title slide with the contents;
  - load chart (native PowerPoint chart; overloaded owners in red);
  - heatmap and discipline tables (paged by rows and months);
  - project matrix table (paged by disciplines and rows);
  - one or more task slides per owner (delayed tasks highlighted).
- Ticks are kept in the open page only.

---

## 8. Project dashboard (Gantt) (`/project/<name>`, `templates/dashboard.html`)

One page per project. The header shows the project name, **Project Manager**, **Program Manager**, **Start**, and **Expected End (Gate 5)**. An **Edit** button opens a dialog for the three editable fields; a Gate 5 date entered here also drives the overall Critical Path view. Viewers do not see the Edit button.

### 8.1 Toolbar

- **➕ Add New Task** (editors only).
- **Detailed / High Level** view switch. High Level shows critical path and milestones (macro tasks only).
- **Collapse macro tasks / Overall open tasks** switch (default: open). Collapse hides every macro task's sub-tasks; the caret on each macro task still opens or closes that task.
- Zoom: Monthly, Quarterly, Yearly, Fit All.
- Status filters, owner / phase / department filters, critical-path and tailed-out filters.
- Export menu: Gantt PPT, critical path PPT, Excel export, and **Export HTML (Share)** (a standalone copy of the project page).

### 8.2 Task list (left)

Columns: `#` (row number), Task name (with ⭐ milestone, 🔴 critical, 🚫 tailed out, comment and attachment badges), Owner, Department, Start, Duration (days), End, Status, Predecessors, Actions.

- **Row numbers:** top-level tasks are numbered 1, 2, 3…; sub-tasks are 2.1, 2.2… under their macro task.
- **Sub-tasks / macro tasks:** a macro task has a caret (▾ / ▸). Sub-tasks cannot exceed their parent's dates (enforced in the UI and on the server).
- **Row selection:** click a row to select it. A bar at the bottom shows the selection and offers **↑ Add task above** and **↓ Add task below**. Esc or ✕ clears it.
- **+ beside the number:** a small gray "+" next to each top-level number adds a task after that row.
- **Edit ✏️ / dependencies 🔗 / rework ⚠ / gate sign-off 🔏** buttons per row. Double-click a bar to edit.
- Dates are editable in place (click the Start/End cell).

### 8.3 Add / Edit Task window

Opens as a panel on the **left** edge (the page stays visible and clickable). Fields: name, owner, phase, status, start (entered), due, duration, critical, milestone, tailed out, predecessors (dependency picker), overlap/blocking notices. Has a ✕ close button. Delete is available when editing.

When the window is opened from a row (above / below / "+"), the new task takes that row's phase and is placed by the server:

- The anchor's whole block (macro task plus its sub-tasks) stays together.
- The new task goes directly before or after that block.
- All tasks of the project are renumbered (`row_order` = 10, 20, 30…).

### 8.4 Gantt chart (right)

- Tasks grouped by phase; gate milestones group the phases.
- Bars coloured by status; critical tasks in red; float bars show buffer to the next gate.
- Within a phase the list is sorted by start date by default. Clicking a column header sorts by that column.
- Dependency arrows (predecessor → successor) and a dependency map view.
- Today line.

### 8.5 Gates, sign-offs and baselines

- **Gate milestones** are tasks whose name contains "Gate". Each gate has a sign-off: **Passed**, **Passed with Rework** (with a rework due date and a rework sign-off date later), recorded in `gate_sign_offs`.
- **Rework cause** marks (⚠) identify tasks that caused rework; those tasks are excluded from cascades.
- **Gate baselines** store the planned gate dates; the **gate change log** records every gate date change with a reason. Entries can be deleted with a reason.
- Moving a gate deadline asks for confirmation and can move subsequent gates.

### 8.6 Date changes, cascade and what-if

- Changing a task's due date runs a **cascade preview**: dependent successor tasks that would move are listed and, on confirmation, saved together with any gate moves.
- A new task whose dates push past a gate deadline triggers a gate-deadline dialog.
- **Overlap / blocked** detection flags tasks that start before a predecessor ends or whose predecessor is overdue. A "suggest dates" popup proposes new dates.
- **What-if mode:** date changes are applied in memory only and can be discarded (a snapshot of the tasks is kept).
- **Critical path** is recomputed after cascades; tasks past a gate deadline are marked critical.

### 8.7 Comments and attachments

- Each task has a comment log (open and resolved entries, resolve/reopen).
- Attachments: files (stored under `ATTACHMENTS_DIR`) and links; download and delete.
- The attachment and comment badges appear on the task row.

### 8.8 Risks

Each project has its own risk register (panel opened from the project header or the pipeline Risk badge): add, edit, delete, import from Excel, export to Excel, export to PowerPoint. Risk fields: title, category, probability, impact, owner, mitigation, status, due date.

### 8.9 Exports and other pages

- **Excel export** of the task list.
- **Gantt PPT** (`/api/project/<name>/export-gantt-ppt`) and **Critical Path PPT** (`/export-critical-path-ppt`).
- **Project schematic** page (`/project/<name>/schematic`) with a standalone PPT (`ppt_exporter.py`).
- **Open file** helper (`/api/open-file`) for linked files.

---

## 9. Disciplines map (`/disciplines`)

- Resource teams and disciplines are kept in `resource_teams` and `disciplines`.
- Owners are mapped to disciplines (owner autocomplete from known owners).
- The map feeds the **By Discipline** view and the discipline load in the overall resource tab.
- Admin API: `/api/v1/admin/resource-teams`, `/api/v1/admin/disciplines`.

---

## 10. Administration

- **`/admin`** (superadmin): create and enable/disable divisions; create users and assign role/division; reset codes; **Download backup** (zip of the control database and every division database, taken with SQLite's backup API).
- **`/manage-users`** (division admin): manage users of their own division.
- The backup contains password hashes — store the file securely.

---

## 11. Data import and export formats

### 11.1 Project Gantt Excel import (`/api/upload-excel`)

Read from the sheet defined in `config.py`:

| Item | Cell |
|---|---|
| Project name | `C3` |
| Manager | `C5` |
| Header row | 10 |
| First data row | 11 |

Task columns: A reference ID, B name, C phase, D owner, E start, F status, G end, H date closed, I result, J parent reference (blank = top-level). Sub-tasks are linked to their parent by reference ID.

### 11.2 Risk register Excel

Layout "Risk Input" (read back by `_parse_risks_from_excel()` in `server.py`). The exporter writes the same layout, so an exported file can be edited and re-imported. Duplicate detection is applied on import.

### 11.3 Exports

| Export | Route / module |
|---|---|
| Overall dashboard standalone HTML | client-side (`exportOverallDashboardHTML`) |
| Resource load PPT | `POST /api/resource-load/export-ppt` · `resource_ppt_exporter.py` |
| Portfolio schedule PPT | `GET /api/portfolio-schedule/export-ppt` · `portfolio_ppt_exporter.py` |
| Project Gantt PPT | `POST /api/project/<name>/export-gantt-ppt` · `gantt_ppt_exporter.py` |
| Critical path PPT | `POST /api/project/<name>/export-critical-path-ppt` |
| Project schematic PPT | `/api/project/<name>/export-ppt` · `ppt_exporter.py` |
| Project Excel | `/api/project/<name>/export` · `excel_exporter.py` |
| Risks (project / pipeline) | `/risks/export-ppt`, `/risks/export-excel` · `risk_ppt_exporter.py`, `risk_excel_exporter.py` |

---

## 12. Data model

All tables are created by `CREATE TABLE IF NOT EXISTS` on start-up; schema changes are added as migrations (§13).

### 12.1 Division database

| Table | Key columns |
|---|---|
| `projects` | id, name (unique), manager, excel_filename, last_imported, **program_manager**, **gate_5_date**, `is_deleted` / soft-delete fields |
| `tasks` | id, project_id, reference_id, name, phase, owner, start_date, end_date, status, date_closed, result, critical, milestone, tailed_out, **is_rework_cause**, **rework_original_due**, **cloned_from_phase**, **parent_id** (sub-task link), **row_order**, created_at, updated_at |
| `task_dependencies` | project_id, predecessor_id, successor_id |
| `gate_sign_offs` | project_name, gate_name, gate_id, sign_off_date, rework_due_date, **rework_sign_off_date**, status |
| `gate_baselines` | project_name, gate_name, planned dates |
| `gate_change_log` | project_name, gate_name, old/new date, reason, timestamp |
| `resource_teams` | team definitions and capacity |
| `disciplines` | discipline ↔ owner mapping |
| `task_comments` | task_id, text, state (open / resolved), timestamps |
| `task_attachments` | task_id, file or link attachment, original and stored names (see migration `003_task_attachments.sql`) |
| `risks_new` | project_id or pipeline_project_id, title, category, probability, impact, owner, mitigation, status, due_date |
| `priority_projects` | priority, name, leader, process_type, next_gate, launch_date, objective, segment, **category**, linked dashboard |
| `archived_projects` | archived project name, completed date |
| `schema_migrations` | applied migration names |

### 12.2 Control database

| Table | Key columns |
|---|---|
| `divisions` | id, key (unique), name, db_filename, is_active |
| `users` | id, username (unique), email, password_hash, role, division_id, is_active, must_change_password |
| `password_resets` | user_id, token_hash, code, expires_at, used_at |

---

## 13. Database migrations

Migrations are numbered SQL files in `migrations/`, applied by `db_migrate.py` at server start (development) and during installation (production). Applied names are recorded in `schema_migrations`; applied migrations never run again.

| File | Purpose |
|---|---|
| `001_disciplines.sql` | Disciplines table |
| `002_task_comments.sql` | Task comments |
| `003_task_attachments.sql` | Task attachments |
| `004_task_parent.sql` | Sub-task parent link |

Procedure for a schema change: change the dev database, add `migrations/NNN_short_description.sql` (next number), commit it.

Some earlier columns are added with `ALTER TABLE … ADD COLUMN` inside `database_manager.py` (guarded by `try/except`).

---

## 14. API reference (summary)

All JSON endpoints are scoped to the logged-in user's division. Write endpoints are refused for viewers.

**Projects and Gantt**
- `GET /api/projects`, `GET /api/project/<name>`, `GET /api/project/<name>/tasks`
- `GET|PUT|DELETE /api/task/<id>`, `POST /api/project/<name>/task` (accepts `insert_after_task_id` / `insert_before_task_id`), `DELETE /api/task/<id>`
- `PUT /api/project/<name>/program_manager | project_manager | gate_5_date | rename`
- `POST /api/project/<name>/soft-delete`, `POST /api/project/<name>/restore`, `DELETE /api/project/<name>`
- `GET|POST /api/project/<name>/dependencies`, `DELETE /api/dependency/<id>`, `DELETE /api/project/<name>/dependencies/by-tasks`
- `GET|POST /api/project/<name>/gate-sign-offs`, `DELETE /api/project/<name>/gate-sign-off/<gate>`
- `GET|POST /api/project/<name>/gate-baselines`
- `GET|POST|DELETE /api/project/<name>/gate-change-log`
- `GET|POST /api/task/<id>/comments`, `PUT /api/comment/<id>/state`
- `GET|POST /api/task/<id>/attachments`, `…/attachments/link`, `…/attachments/file`, `GET …/download`, `DELETE /api/attachment/<id>`

**Overall dashboard and resource load**
- `GET /api/stats`, `GET /api/overall-gate-timeline`, `GET /api/overall-critical-path-overview`
- `GET /api/overall-resource-load`, `GET /api/discipline-resource-load`, `GET /api/resource-project-matrix`
- `GET /api/known-owners`, `POST /api/rename-owner`
- `POST /api/resource-load/export-ppt`, `GET /api/portfolio-schedule/export-ppt`

**Pipeline**
- `GET|POST /api/priority-projects`, `PUT|DELETE /api/priority-projects/<id>`
- `POST /api/priority-projects/<id>/move | complete`, `POST /api/priority-projects/reorder`
- `GET /api/archived-projects`, `POST /api/archived-projects/<id>/restore`

**Risks**
- `GET|POST /api/project/<name>/risks`, `GET|POST /api/pipeline-project/<id>/risks`
- `PUT|PATCH|DELETE /api/risk/<id>`, `GET /api/risks/counts`, `GET /api/risks/counts/pipeline`
- Import / export endpoints under `…/risks/import`, `…/risks/export-ppt`, `…/risks/export-excel`

**Import, exports and misc.**
- `POST /api/upload-excel`, `POST /api/open-file`
- `GET /api/project/<name>/export`, `…/export-ppt`, `…/export-gantt-ppt`, `…/export-critical-path-ppt`

**Admin**
- `/admin/*` (divisions, users, switch division, backup), `/manage-users/*`
- `/api/v1/admin/resource-teams*`, `/api/v1/admin/disciplines*`

**Pages:** `/`, `/project/<name>`, `/project/<name>/schematic`, `/disciplines`, `/admin`, `/manage-users`, `/login`, `/logout`, `/change-password`, `/forgot-password`, `/reset-password`.

---

## 15. Build, release and deployment

### 15.1 Release steps

1. Bump `#define AppVersion` in `installer/setup.iss` (the installer file name is derived from it).
2. Build from the `installer` folder:
   ```powershell
   Remove-Item "Output\OverallDashboardSetup_<version>.exe" -Force -ErrorAction SilentlyContinue
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "setup.iss"
   ```
3. Test on a target machine (install, upgrade with *Keep production database*).
4. Copy the installer to the distribution folder.

**Rebuild the installer** after any change to `server.py`, `templates/`, `config.py`, `db_migrate.py`, `installer/post_install.ps1`, `installer/setup.iss` or `migrations/`.

**New Python modules** imported by `server.py` or `aggregate_app.py` must be listed in the `[Files]` section of `installer/setup.iss`, for example:
```
Source: "{#SrcRoot}\new_module.py"; DestDir: "{app}"; Flags: ignoreversion
```

### 15.2 Version history (installer)

1.3.5 → 1.3.13 (earlier releases), **1.3.14** (current): resource-load PowerPoint builder; resource quick-access "More views"; admin backup; Gantt task insert above/below, "+" beside row numbers, row action bar, macro/sub-task toggle, close button on the task window; project header Edit dialog; manual Gate 5 date drives the critical-path view; left-side task window.

---

## 16. Testing and quality

- `gantt_tests.py` — checks on the Gantt page's HTML (for example that the export controls exist).
- There is no automated browser test suite. UI changes are verified manually in the browser; server changes are checked with the Flask test client (`app.test_client()`) and by running the changed database functions against a **copy** of the division database.
- Syntax checks used during development: `python -m py_compile <file>` for Python, and `node --check` on the inline `<script>` blocks of the templates (Jinja tags stripped first).

---

## 17. Security notes

- `SECRET_KEY` in `config.py` is a development value; set a strong key for production.
- The server binds to `127.0.0.1`; expose it only through the approved server/proxy setup.
- Passwords are stored as hashes; reset codes and tokens are stored hashed (`token_hash`) and expire.
- The backup download contains password hashes and all division data — restrict who can download it and where the file is stored.
- Viewer accounts are blocked from every write method on the server, not just in the UI.
- Attachments are stored on disk under `ATTACHMENTS_DIR`; deleting an attachment or task removes the file.

---

## 18. Known limitations and open items

- The **Projects** tab on the Overall dashboard is hidden on purpose; the standalone HTML export also hides it.
- The **Effort matrix** button shows the working-day view; a true task-matrix mode exists in code (`task-matrix`) but no button uses it.
- Within a phase, the Gantt list is sorted by start date by default, so a task added above or below a row appears by its start date. Its row number follows the row above or below it.
- Some tasks rely on the date-based and overlap logic in the browser; large projects may take a moment to re-render.
- `CLAUDE.md` still mentions the installer version 1.3.10 in examples; the current version is in `installer/setup.iss`.
- The installer must be rebuilt for production after each change to server code or templates.

---

## 19. Glossary

| Term | Meaning |
|---|---|
| Division | A business unit with its own database, users and projects. |
| Programme / Project | A project record with a Gantt (tasks) and optional gates. |
| Macro task | A top-level task that can have sub-tasks (numbered 1, 2, 3…). |
| Sub-task | A task under a macro task (numbered 2.1, 2.2…). |
| Gate | A milestone task whose name contains "Gate" (Gate 1–5 …), signed off as Passed or Passed with Rework. |
| Gate 5 date (Expected End) | The project's expected end; manual value if entered, otherwise the Gate 5 milestone. |
| Rework cause | A task marked as the cause of rework; excluded from cascades. |
| Cascade | Shifting dependent tasks and gates when a predecessor's date changes. |
| Baseline | Stored planned gate dates for comparison. |
| Pipeline | The prioritised list of projects that are not yet in the Gantt portfolio view. |
| Overloaded owner | An owner whose effective concurrent load reaches the overload threshold. |
| Tailed out | A task flagged 🚫 and left out of the critical-path calculation; a filter can show or hide these. |
