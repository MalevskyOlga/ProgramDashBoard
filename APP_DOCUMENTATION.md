# Flame & Gas Program Management Dashboard — Application Documentation

**Last updated:** 2026-05-01  
**Branch:** `portal`  
**Server port:** 5003

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [File Structure](#3-file-structure)
4. [Database Schema](#4-database-schema)
5. [Backend — server.py](#5-backend--serverpy)
6. [API Reference](#6-api-reference)
7. [Frontend — index.html (Overall Dashboard)](#7-frontend--indexhtml-overall-dashboard)
8. [Frontend — dashboard.html (Project Gantt)](#8-frontend--dashboardhtml-project-gantt)
9. [Frontend — disciplines.html (Resource Admin)](#9-frontend--disciplineshtml-resource-admin)
10. [Frontend — project_schematic.html](#10-frontend--project_schematichtml)
11. [Supporting Python Modules](#11-supporting-python-modules)
12. [Configuration — config.py](#12-configuration--configpy)
13. [Excel Import Schema](#13-excel-import-schema)
14. [Startup & Deployment](#14-startup--deployment)
15. [Key Business Logic](#15-key-business-logic)

---

## 1. Overview

A local Flask web application that serves as a **program management command center** for Flame & Gas product development. It provides:

- A **portfolio-level overview** (gate timeline, resource load, critical path, pipeline)
- **Individual project Gantt dashboards** for each imported project
- **Resource management** by discipline and by project
- **Risk register** per project and per pipeline project
- **F&G Pipeline** — categorized project roadmap with priorities

The application runs entirely on localhost (no internet connection required). Data is persisted in SQLite. Projects are imported from Excel (.xlsx) files using a fixed column schema.

---

## 2. Architecture

```
Browser (Chrome/Edge)
        │
        │  HTTP  (port 5003)
        ▼
Flask server  ─── server.py
        │
        ├── DatabaseManager  ─── database_manager.py
        │       └── SQLite  ─── database/dashboards.db
        │
        ├── ExcelParser  ─── excel_parser.py
        ├── ExcelExporter  ─── excel_exporter.py
        ├── GanttPptExporter  ─── gantt_ppt_exporter.py
        ├── PptExporter  ─── ppt_exporter.py
        └── RiskPptExporter  ─── risk_ppt_exporter.py

Templates (Jinja2 server-rendered, then all-JS client-side):
        ├── templates/index.html          ← Overall dashboard (port 5003/)
        ├── templates/dashboard.html      ← Single project Gantt
        ├── templates/disciplines.html    ← Resource team admin
        └── templates/project_schematic.html ← Schematic schedule view
```

**Data flow for a new project:**

1. User clicks "Import New Project from Excel" on the Projects tab
2. Browser uploads `.xlsx` to `POST /api/upload-excel`
3. `ExcelParser` reads project name, manager, and task rows
4. `DatabaseManager` upserts the project and tasks into SQLite
5. Browser renders the project card; user clicks to open its Gantt dashboard

---

## 3. File Structure

```
Program_Project Management overview/
│
├── server.py                    Main Flask application (~1680 lines)
├── config.py                    Configuration constants
├── database_manager.py          All DB read/write logic (~1690 lines)
├── excel_parser.py              Excel → task data parser
├── excel_exporter.py            Export tasks back to Excel
├── gantt_ppt_exporter.py        Export Gantt view to PowerPoint
├── ppt_exporter.py              Export schematic schedule to PowerPoint
├── risk_ppt_exporter.py         Export risk register to PowerPoint
│
├── templates/
│   ├── index.html               Overall portfolio dashboard (~5860 lines)
│   ├── dashboard.html           Individual project Gantt (~8090 lines)
│   ├── disciplines.html         Discipline/resource admin (~270 lines)
│   └── project_schematic.html   Schematic schedule view (~1000 lines)
│
├── database/
│   └── dashboards.db            SQLite database (all data)
│
├── exports/                     Generated .pptx files
├── logs/
│   ├── server.stdout.log
│   └── server.stderr.log
│
├── START_SERVER_PERSISTENT.bat  Start server as background process
├── STOP_SERVER.bat              Stop the background server
├── START_AGGREGATE_SERVER.bat   Start aggregate/portfolio server (port 5002)
├── requirements.txt             Python dependencies
└── Flame & Gas Project Priority List.xlsx  Source for pipeline import
```

---

## 4. Database Schema

Single SQLite file: `database/dashboards.db`

### 4.1 projects
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT UNIQUE | Project name (matches Excel cell C3) |
| manager | TEXT | Project manager name |
| program_manager | TEXT | Program manager (editable in dashboard) |
| excel_filename | TEXT | Original uploaded filename |
| last_imported | TIMESTAMP | Last Excel import time |
| is_deleted | INTEGER | Soft-delete flag (0/1) |
| created_at / updated_at | TIMESTAMP | |

### 4.2 tasks
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| project_id | INTEGER FK | → projects.id, CASCADE DELETE |
| reference_id | TEXT | Cell A value from Excel |
| name | TEXT | Task name |
| phase | TEXT | Gate section (e.g. "Gate 1", "Gate 2") |
| owner | TEXT | Owner name (matched to resource_teams) |
| start_date | DATE | ISO format |
| end_date | DATE | ISO format |
| status | TEXT | Planned / In Process / Completed / Cancelled |
| date_closed | DATE | Actual completion date |
| result | TEXT | Task result/notes |
| critical | INTEGER | 1 = on critical path |
| milestone | INTEGER | 1 = gate milestone task |
| tailed_out | INTEGER | 1 = task is a "tailed out" clone |
| is_rework_cause | INTEGER | 1 = rework trigger task |
| rework_original_due | TEXT | Original due before rework |
| cloned_from_phase | TEXT | Source phase for tailed-out clones |
| row_order | INTEGER | Display order |

### 4.3 gate_sign_offs
| Column | Type | Notes |
|--------|------|-------|
| project_name | TEXT | |
| gate_name | TEXT | "Gate 1" … "Gate 5", "Gate C/D" |
| gate_id | INTEGER | |
| sign_off_date | TEXT | Date gate was passed |
| rework_due_date | TEXT | Rework sign-off deadline |
| status | TEXT | "Passed" / "Passed with Rework" |
| UNIQUE(project_name, gate_name) | | |

### 4.4 gate_baselines
| Column | Type | Notes |
|--------|------|-------|
| project_name | TEXT | |
| gate_name | TEXT | |
| baseline_date | TEXT | Original planned gate date |
| UNIQUE(project_name, gate_name) | | |

### 4.5 gate_change_log
| Column | Type | Notes |
|--------|------|-------|
| project_name / gate_name | TEXT | |
| old_date / new_date | TEXT | Before and after |
| days_delayed | INTEGER | Positive = slip |
| triggered_by_task_id/name | | Which task caused the change |
| impact_description | TEXT | |

### 4.6 task_dependencies
| Column | Type | Notes |
|--------|------|-------|
| project_name | TEXT | |
| predecessor_id | INTEGER FK | → tasks.id |
| successor_id | INTEGER FK | → tasks.id |
| UNIQUE(predecessor_id, successor_id) | | |

### 4.7 resource_teams
| Column | Type | Notes |
|--------|------|-------|
| team_name | TEXT | Discipline name (e.g. "ATE", "Certifications") |
| owner_name | TEXT UNIQUE | Person's name as it appears in task Owner column |
| capacity_hrs_per_week | REAL | Default 37.5 |

### 4.8 risks
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| project_id | INTEGER | Nullable → Gantt project risks |
| pipeline_project_id | INTEGER | Nullable → pipeline project risks |
| title | TEXT | |
| category | TEXT | "Technical" / "Schedule" / "Resource" / "External" |
| probability | TEXT | "Low" / "Medium" / "High" |
| impact | TEXT | "Low" / "Medium" / "High" |
| owner | TEXT | |
| mitigation | TEXT | |
| status | TEXT | "Open" / "Closed" |
| due_date | TEXT | |
| strategy | TEXT | Mitigation strategy |
| schedule_impact | TEXT | |
| risk_type | TEXT | |
| outcome | TEXT | |
| date_closed | TEXT | |

### 4.9 priority_projects
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| priority | INTEGER | Order within category |
| name | TEXT | Project name |
| leader | TEXT | Project leader |
| process_type | TEXT | "NPD" / "Cert" / "OBS" / "N/A" |
| next_gate | TEXT | Next planned gate |
| launch_date | TEXT | Target launch date |
| objective | TEXT | "Growth" / "Maintain" / "Discontinue" |
| segment | TEXT | "Industrial" / "Suppression" / "All" |
| linked_dashboard | TEXT | Links to a projects.name ("\_\_none\_\_" = user deleted link) |
| always_staffed | INTEGER | 1 = show "Fully" for all disciplines regardless of task count |
| category | TEXT | "active_big" / "active_small" / "planned_hold" / "proposed" |

### 4.10 archived_projects
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name / completed_date | TEXT | |
| priority / leader / process_type / etc. | | Snapshot of priority_projects row |

---

## 5. Backend — server.py

### 5.1 Initialization
- Creates `Flask` app with `SECRET_KEY`, 16 MB upload limit, `TEMPLATES_AUTO_RELOAD`
- Instantiates `DatabaseManager` and calls `initialize_database()` on startup
- `@app.after_request` adds no-cache headers to all GET responses and logs every request

### 5.2 Priority table helpers (module-level)

| Function | Purpose |
|----------|---------|
| `_ensure_priority_tables()` | Creates/migrates priority_projects and archived_projects tables; sets `category='active_big'` on any NULL rows; returns open connection |
| `_seed_priority_from_excel(conn)` | Seeds priority_projects from the Excel file on first run (when table is empty) |
| `_build_priority_response(conn)` | Returns all priority_projects rows as `list[dict]`, ordered by priority/id |

### 5.3 Constants
- `_PRIORITY_ALLOWED_FIELDS` — set of column names that can be PATCHed/PUT on priority_projects
- `_PRIORITY_CATEGORIES` — `{'active_big', 'active_small', 'planned_hold', 'proposed'}`
- `config.PM_LOAD_PER_PROJECT` = 5 (task-equivalent PM overhead per managed project)

---

## 6. API Reference

### Page routes
| Route | Returns |
|-------|---------|
| `GET /` | `index.html` — overall portfolio dashboard |
| `GET /project/<name>` | `dashboard.html` — single project Gantt |
| `GET /project/<name>/schematic` | `project_schematic.html` — schedule schematic |
| `GET /disciplines` | `disciplines.html` — resource team admin |

### Project APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/projects` | All non-deleted projects |
| GET | `/api/stats` | Counts: projects, tasks, owners, risks |
| GET | `/api/project/<name>` | Single project detail |
| GET | `/api/project/<name>/tasks` | All tasks for project |
| GET | `/api/task/<id>` | Single task |
| PUT | `/api/task/<id>` | Update task fields |
| POST | `/api/project/<name>/task` | Create new task |
| DELETE | `/api/task/<id>` | Delete task |
| POST | `/api/upload-excel` | Import project from .xlsx |
| GET | `/api/project/<name>/export` | Download project as .xlsx |
| GET | `/api/project/<name>/export-ppt` | Export schematic schedule as .pptx |
| POST | `/api/project/<name>/export-gantt-ppt` | Export Gantt view as .pptx |
| POST | `/api/project/<name>/export-critical-path-ppt` | Export critical path as .pptx |
| PUT | `/api/project/<name>/rename` | Rename project |
| PUT | `/api/project/<name>/program_manager` | Update program manager |
| POST | `/api/project/<name>/soft-delete` | Soft-delete project |
| POST | `/api/project/<name>/restore` | Restore soft-deleted project |
| DELETE | `/api/project/<name>` | Permanently delete project |
| POST | `/api/open-file` | Open a file path in Windows Explorer |

### Portfolio overview APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/overall-gate-timeline` | Gate milestone dates for all projects |
| GET | `/api/overall-resource-load` | Resource load data (by discipline and by owner) |
| GET | `/api/overall-critical-path-overview` | Critical path tasks across all projects |

### Gate management APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/api/project/<name>/gate-baselines` | Read/write original gate dates |
| GET/POST | `/api/project/<name>/gate-change-log` | Read/write gate change history |
| DELETE | `/api/project/<name>/gate-change-log/<gate>` | Delete a gate change entry |
| GET/POST | `/api/project/<name>/gate-sign-offs` | Read/write gate sign-offs |
| DELETE | `/api/project/<name>/gate-sign-off/<gate>` | Remove a gate sign-off |

### Dependency APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/api/project/<name>/dependencies` | Read/write task dependencies |
| DELETE | `/api/dependency/<id>` | Remove single dependency |
| DELETE | `/api/project/<name>/dependencies/by-tasks` | Remove dependency by task pair |

### Risk APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/api/project/<name>/risks` | Gantt project risks |
| PATCH/PUT | `/api/risk/<id>` | Update a risk (PATCH = partial, PUT = full) |
| DELETE | `/api/risk/<id>` | Delete a risk |
| GET | `/api/risks/counts` | Open risk counts per project (for badges) |
| GET | `/api/risks/counts/pipeline` | Open risk counts per pipeline project |
| GET/POST | `/api/pipeline-project/<id>/risks` | Pipeline project risks |
| POST | `/api/project/<name>/risks/import` | Import risks from .xlsx |
| POST | `/api/pipeline-project/<id>/risks/import` | Import pipeline risks from .xlsx |
| GET | `/api/project/<name>/risks/export-ppt` | Export risks as .pptx |
| GET | `/api/pipeline-project/<id>/risks/export-ppt` | Export pipeline risks as .pptx |

### Pipeline (Priority projects) APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/priority-projects` | All priority projects (all categories) |
| POST | `/api/priority-projects` | Create new pipeline project |
| PUT | `/api/priority-projects/<id>` | Update one field (`{ field, value }`) |
| DELETE | `/api/priority-projects/<id>` | Delete pipeline project |
| POST | `/api/priority-projects/<id>/move` | Move up/down within category (`{ direction }`) |
| POST | `/api/priority-projects/<id>/complete` | Archive project |
| GET | `/api/archived-projects` | All archived pipeline projects |
| POST | `/api/archived-projects/<id>/restore` | Restore archived project |

### Resource / Discipline APIs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/resource-project-matrix` | By-Project resource load matrix (2-month window) |
| GET | `/api/discipline-resource-load` | By-Discipline heatmap data |
| GET/POST | `/api/v1/admin/resource-teams` | Read resource team map |
| POST | `/api/v1/admin/resource-teams/bulk` | Bulk save resource team map |
| GET | `/api/known-owners` | All distinct owner names across tasks |
| POST | `/api/rename-owner` | Rename owner across all tasks |

---

## 7. Frontend — index.html (Overall Dashboard)

Single-page app served at `/`. All data loaded via `fetch` after page load.

### 7.1 Tab structure

| Tab | `data-tab` | Content |
|-----|-----------|---------|
| Portfolio Schedule Overview | `schedule` | Gate timeline across all projects |
| F&G Pipeline | `pipeline` | Pipeline project list by category |
| Projects | `projects` | Gantt project cards + import |
| Overall Resource Load | `resources` | Discipline heatmap / By-Project matrix / Owner drilldowns |
| Critical Path | `critical` | Cross-project critical path overview |

Active tab is persisted to `localStorage` and restored on reload.

### 7.2 Portfolio Schedule Overview (tab: schedule)

**Data source:** `GET /api/overall-gate-timeline`

Renders a **horizontal timeline** showing all gate milestones across all projects. Each project has a row of gate markers (◆) positioned by date percentage within the visible date range.

**Gate color logic:**
- Green diamond = gate has a `gate_sign_off` with status "Passed"
- Blue/purple = "Passed with Rework"
- Gray = planned (future)
- Orange = rework sign-off pending

**Date range:** spans from earliest gate date to latest gate date across all projects, padded by ±1 month.

**Month header:** fiscal period labels (FY26 P01 format) above the timeline.

### 7.3 Overall Resource Load (tab: resources)

**Data source:** `GET /api/overall-resource-load`

Three view modes toggled by buttons:

#### By Discipline (default)
- Heatmap: rows = owners, columns = months
- Cell color: white → yellow → orange → red based on concurrent task days
- Summary cards: total owners, overloaded count, active tasks
- PM Overhead panel: shows PM load per project manager
- Drilldown: click owner → task list for that owner

#### By Project
- Matrix: rows = priority_projects (active_big only), columns = all disciplines
- 2-month rolling window from today
- Cell labels: **Fully** (1–30 tasks), **Partially** (31–35), **No** (36+), **N/A** (0), empty (no project)
- "Supporting Book-Build-Ship" always shows "Fully" (`always_staffed=1`)
- Frozen columns: # / Project / Leader on left, Total on right
- Frozen header row (discipline names)

#### By Owner
- Table: rows = owners, drilldown shows tasks with project/date/status

**`cellStatus(count, hasProject)`** — maps task count to label+color:
```
!hasProject → dark background, no label
count == 0  → N/A (gray)
1–30        → Fully (green)
31–35       → Partially (yellow)
36+         → No (red)
```

### 7.4 F&G Pipeline (tab: pipeline)

**Data source:** `GET /api/priority-projects`, `GET /api/archived-projects`, `GET /api/risks/counts`, `GET /api/risks/counts/pipeline`

**Category tabs:**
| Key | Label |
|-----|-------|
| `active_big` | 📊 Active Big (>80h) |
| `active_small` | 📋 Active Small (<80h) |
| `planned_hold` | ⏸ Planned & On Hold |
| `proposed` | 💡 Proposed |

Active category stored in `_activePipelineCategory`. All data held in `_allPriorityProjects`; tab switch filters client-side (no new API call).

**Priority reordering:** ▲/▼ buttons on each row call `POST /api/priority-projects/<id>/move` with `{ direction: 'up'|'down' }`. Server swaps priority values atomically within the same category. ▲ disabled on first row, ▼ disabled on last row.

**Inline editing:** All columns (name, leader, type, gate, date, objective, segment, category) are editable in-place. Text fields use `contenteditable`; dropdowns use `<select>` with `onchange → savePrioritySelect()` → `PUT /api/priority-projects/<id>`.

**Gantt linking:** Each pipeline project can be linked to a Gantt project dashboard. Options: import from Excel, link to existing, or remove link. The link is stored as `linked_dashboard` (project name). Sentinel value `__none__` means the user explicitly deleted the link (prevents auto-rematch).

**Risk badge:** shows open risk count from either the linked Gantt project's risks or the pipeline project's own risks. Click opens the risk panel.

**Completed projects:** moved to `archived_projects` table; shown in a collapsible section at the bottom. Can be restored.

### 7.5 Projects (tab: projects)

**Data source:** `GET /api/projects`

Renders a card grid of all imported Gantt projects. Each card shows:
- Project name, manager, program manager
- Gate progress indicator (colored gate badges)
- Open risk count badge
- Quick actions: Open Gantt, Reload Excel, Delete

**Import:** file picker → `POST /api/upload-excel` → card added immediately.

### 7.6 Critical Path (tab: critical)

**Data source:** `GET /api/overall-critical-path-overview`

Shows the critical path chain per project — tasks marked `critical=1` ordered chronologically. Displays as a flowing timeline with task bars.

### 7.7 Risk Panel (global)

A slide-in side panel (`openRiskPanel(projectName)` / `openPipelineRiskPanel(id, name)`) rendered in a fixed right-side container. Features:
- Add / edit / delete risks inline
- Import from Excel (`_parseRisksFromExcel`)
- Export to PowerPoint
- Fields: title, category, probability, impact, owner, status, due date, mitigation, strategy, schedule impact, risk type, outcome, date closed
- RPN (Risk Priority Number) = probability score × impact score, color-coded

---

## 8. Frontend — dashboard.html (Project Gantt)

Single-page Gantt dashboard for one project, served at `/project/<name>`.

### 8.1 Data loading

`loadFromAPI()` runs on page load:
1. `GET /api/project/<name>` — project metadata
2. `GET /api/project/<name>/tasks` — all tasks
3. `GET /api/project/<name>/dependencies` — task dependencies
4. `GET /api/project/<name>/gate-baselines` — baseline gate dates
5. `GET /api/project/<name>/gate-sign-offs` — gate pass status
6. `GET /api/known-owners` — owner autocomplete list

### 8.2 Task table

Columns: #, Task Name, Phase, Owner, Start, End, Status, Duration, Result, Actions

- **Phase grouping:** tasks grouped into Gate sections by their `phase` field. Rows within each phase are sorted by start date (or row_order on import).
- **Gate health indicator:** each phase header shows a colored dot (green/yellow/red) based on task completion percentage.
- **Status colors:** Planned (yellow bar), In Process (blue), Completed (green), Cancelled (gray).
- **Critical path:** critical tasks shown with red left border on their Gantt bar.
- **Milestones:** diamond marker on the Gantt bar.

### 8.3 Gantt bar rendering

`renderFlatTaskList()` renders both the task table rows and SVG Gantt bars side by side. Project start = earliest task start date. Each bar positioned by `ganttPixelOffset(date, projectStart, columnWidth)`.

Month/week grid rendered as SVG background. Today line rendered by `renderTodayLine()`.

### 8.4 Gate sign-offs

Gates can be signed off as "Passed" or "Passed with Rework":
- `openGateSignOff(taskId)` — opens modal with sign-off date and optional rework due date
- `saveGateSignOff()` — `POST /api/project/<name>/gate-sign-offs`
- Signed-off gates show a checkmark badge; rework gates show an orange badge

### 8.5 Gate baselines and change log

On first load, gate baselines are saved from the current milestone end dates. On subsequent loads, if a gate date changes, `gate_change_log` records the old → new date, days delayed, and the triggering task. The change log is viewable via the "Change Log" button.

**Cascade logic:** when a task end date is moved past a gate milestone, the user is prompted to also move the gate. If confirmed, downstream gates may cascade.

### 8.6 Task editing

Click any cell to edit inline. Click "Edit" button to open a full modal (`editTask(id)`):
- All fields editable
- Date validation: start ≤ end
- Owner autocomplete from known-owners list
- Dependency management: predecessor/successor task links
- Critical path toggle (manual override)
- "Tailed out" clone: creates a duplicate task in the next phase for rework tracking

`saveTask()` → `PUT /api/task/<id>` or `POST /api/project/<name>/task`

### 8.7 Critical path auto-computation

`autoMarkCriticalByGateDeadline()` computes the critical path automatically:
1. Finds the Gate 5 milestone date
2. Works backwards from Gate 5 through task dependencies
3. Marks tasks as `critical=1` if they are on the longest path to Gate 5
4. Manual overrides (uncritical flag) are preserved

### 8.8 Dependency map

`openDepMap()` renders an SVG graph of all task dependencies. Nodes colored by criticality. Click a node to highlight its ancestors/descendants.

### 8.9 Export options

| Export | Description |
|--------|-------------|
| Export to Excel | `GET /api/project/<name>/export` — downloads .xlsx |
| Export Schematic PPT | `GET /api/project/<name>/export-ppt` |
| Export Gantt PPT | `POST /api/project/<name>/export-gantt-ppt` |
| Export Critical Path PPT | `POST /api/project/<name>/export-critical-path-ppt` |

### 8.10 Filters and sorting

- **Owner filter:** multi-select checkbox dropdown; hides rows for unselected owners
- **Phase filter:** hide/show entire gate sections
- **Sort:** click column headers to sort by start date, end date, status, or name

### 8.11 Resource load view (per-project)

The dashboard includes an embedded resource load panel for the current project — shows task counts per owner per month.

---

## 9. Frontend — disciplines.html (Resource Admin)

Served at `/disciplines`.

Admin page for managing the **resource team map** — the mapping of owner names to disciplines.

### Features:
- Table of all owner → discipline mappings
- Inline editing: change discipline assignment
- Add new owner/discipline row
- Bulk save: `POST /api/v1/admin/resource-teams/bulk`
- Owner rename: `POST /api/rename-owner` — renames across all tasks in all projects
- Capacity (hours/week) per owner

### Data source:
- `GET /api/v1/admin/resource-teams` — reads current map
- `GET /api/known-owners` — all owner names from tasks (to show unassigned owners)

---

## 10. Frontend — project_schematic.html

Served at `/project/<name>/schematic`.

A **simplified visual schedule** (schematic view) for a single project, suitable for PowerPoint export. Shows tasks as horizontal bars on a monthly timeline, grouped by Gate phase, with milestone markers.

Primarily used as the source for `ppt_exporter.py`.

---

## 11. Supporting Python Modules

### excel_parser.py — `ExcelParser`
Reads project data from a `.xlsx` file:
- Row 3, col C → project name
- Row 5, col C → manager name
- Row 10 → column headers (validation)
- Rows 11+ → task data

Column map (from `config.py`):
```
A = reference_id, B = name, C = phase, D = owner
E = start_date,  F = status, G = end_date, H = date_closed, I = result
```

Auto-detects milestone rows (phase name = task name, e.g. "Gate 3") and sets `milestone=1`.

### excel_exporter.py — `ExcelExporter`
Exports current task data back to the same Excel format. Preserves column structure.

### gantt_ppt_exporter.py — `GanttPptExporter`
Generates a `.pptx` Gantt chart slide:
- Timeline header (months)
- Rows per task with colored bars
- Gate milestone markers
- Today line
- Critical path highlighted

### ppt_exporter.py — `PptExporter`
Generates a `.pptx` schematic schedule slide from `project_schematic.html` data.

### risk_ppt_exporter.py — `export_risks_to_pptx`
Generates a `.pptx` risk register table slide:
- One row per open risk
- Columns: title, category, probability, impact, RPN, owner, mitigation, status

### database_manager.py — `DatabaseManager`

Central data access layer. Key method groups:

| Group | Key methods |
|-------|-------------|
| Projects | `get_all_projects()`, `get_project_by_name()`, `delete_project()` |
| Tasks | `get_tasks_by_project()`, `update_task()`, `delete_task()` |
| Gates | `get_overall_gate_timeline()`, `get_gate_baselines()`, `get_gate_change_log()` |
| Resources | `get_overall_resource_load()` |
| Critical Path | `get_overall_critical_path_overview()` |
| Gate sign-offs | `get_gate_sign_offs()`, `delete_gate_sign_off()` |
| Dependencies | `get_dependencies_by_project()`, `delete_dependency()` |
| Risks | `get_risks()`, `update_risk()`, `get_risk_counts_all_projects()` |

`get_overall_resource_load()` is the most complex method (~320 lines): computes per-owner task concurrency, discipline grouping, PM overhead, and rolling month heatmap data.

---

## 12. Configuration — config.py

| Constant | Value | Purpose |
|----------|-------|---------|
| `SERVER_HOST` | `127.0.0.1` | Localhost only |
| `SERVER_PORT` | `5003` | Main app port |
| `DATABASE_PATH` | `database/dashboards.db` | SQLite file location |
| `PM_LOAD_PER_PROJECT` | `5` | PM task-equivalent overhead per project |
| `FULL_TIME_CAPACITY_HRS` | `37.5` | Standard full-time hours/week |
| `OVERLOAD_TASK_THRESHOLD` | `5` | Tasks at which owner is considered overloaded |
| `RESOURCE_LOAD_LOOKBACK_MONTHS` | `6` | How far back to show tasks in heatmap |
| `EXCEL_PROJECT_NAME_ROW` | `3` | Row number for project name in Excel |
| `EXCEL_DATA_START_ROW` | `11` | First data row in Excel |
| `PRIORITY_LIST_PATH` | `Flame & Gas Project Priority List.xlsx` | Pipeline seed file |
| `PRIORITY_LIST_SHEET` | `Mar26` | Sheet name for seeding |

---

## 13. Excel Import Schema

The `.xlsx` upload must follow this layout:

| Row | Column | Content |
|-----|--------|---------|
| 3 | C | Project name |
| 5 | C | Project manager name |
| 10 | A–I | Column headers (not imported, validated) |
| 11+ | A | Reference ID |
| 11+ | B | Task name |
| 11+ | C | Phase / Gate section |
| 11+ | D | Owner name |
| 11+ | E | Start date |
| 11+ | F | Status (Planned / In Process / Completed / Cancelled) |
| 11+ | G | End date |
| 11+ | H | Date closed |
| 11+ | I | Result / notes |

**Gate milestones** are auto-detected: a row where column C (phase) equals column B (task name) is treated as a gate milestone task (`milestone=1`).

**Re-import behavior:** if a project with the same name already exists, all its tasks are replaced. Gate baselines, sign-offs, and dependencies are preserved.

---

## 14. Startup & Deployment

### Start the server

Double-click `START_SERVER_PERSISTENT.bat` or run from terminal:
```bat
START_SERVER_PERSISTENT.bat
```
The server starts as a hidden background process on port **5003**. Logs written to `logs/server.stdout.log` and `logs/server.stderr.log`.

### Stop the server
```bat
STOP_SERVER.bat
```

### Manual start (development)
```bash
python server.py
```
Runs in foreground with live output. `DEBUG_MODE = False` (always) for stability.

### Access
Open browser: `http://localhost:5003`

### Requirements
```
flask
openpyxl
python-pptx
werkzeug
```
Install with: `pip install -r requirements.txt`

### Aggregate server (port 5002)
A separate `aggregate_server.py` / `START_AGGREGATE_SERVER.bat` runs a portfolio aggregation view on port 5002. It is a separate application.

---

## 15. Key Business Logic

### Gate health color
Each gate section header shows a health dot:
- **Green** = all tasks Completed or >80% complete
- **Yellow** = some tasks overdue or in progress
- **Red** = gate deadline exceeded / tasks seriously behind

### Portfolio gate timeline color
- Gate marker **green** = `gate_sign_offs` row exists with status "Passed"
- Gate marker **blue** = "Passed with Rework"
- Gate marker **gray** = no sign-off (planned/future)
- Gate marker **orange** = rework sign-off pending (rework_due_date set, not yet signed off)

### Resource load — By Discipline (heatmap)
- Counts concurrent task days per owner per calendar month
- PM overhead = 5 task-equivalent units per project managed
- Color scale: 0 days = white, 5+ = red

### Resource load — By Project (matrix)
- 2-month rolling window: tasks that overlap [today, today+2 months]
- Task count per discipline per project within that window
- Thresholds: 0 = N/A, 1–30 = Fully, 31–35 = Partially, 36+ = No
- `always_staffed=1` projects skip the count and always show "Fully"

### Critical path computation
1. Find Gate 5 milestone end date
2. For each task: if end date ≥ Gate 5 date AND task has no successors beyond Gate 5, it may be critical
3. Walk backwards through dependencies from Gate 5
4. Tasks on the longest path (by date) are marked `critical=1`
5. Manual "uncritical" overrides stored client-side in `localStorage`

### Priority move logic
`POST /api/priority-projects/<id>/move` with `{ direction: 'up'|'down' }`:
1. Fetches all projects in same category ordered by priority
2. Finds the target project and its neighbor
3. Swaps their priority values in a single transaction
4. Does NOT affect projects in other categories

### linked_dashboard sentinel
When a user links a pipeline project to a Gantt project, `linked_dashboard` stores the Gantt project name. When the user deletes that link, `linked_dashboard = '__none__'`. This sentinel prevents the system from auto-re-matching on next load. An empty/NULL value means "never linked" (auto-match allowed).

### Gate sign-off → portfolio green
A project's gate appears green on the portfolio timeline when:
- `gate_sign_offs` contains a row for that project + gate with `status = 'Passed'`
- **OR** the gate milestone task has `status = 'Completed'`

Both paths are checked in `get_overall_gate_timeline()`.
