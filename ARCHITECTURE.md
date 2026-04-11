# Pipeline Portal & Dashboard — Architecture & Implementation Reference

## How to Start the Server

```bash
cd "C:\Users\omalevsky\OneDrive - Emerson\Documents\AI Projects\Program_Project Management overview"
python unified_server.py
```

The server starts on **http://localhost:5003**

| URL | Destination |
|-----|-------------|
| `http://localhost:5003/` | Redirects → `/portal` |
| `http://localhost:5003/portal` | Pipeline Portal homepage |
| `http://localhost:5003/dashboard` | Programs Dashboard homepage |

To stop: find the PID and kill it:
```powershell
Get-NetTCPConnection -LocalPort 5003 -State Listen | Select-Object -ExpandProperty OwningProcess
Stop-Process -Id <PID> -Force
```

---

## Overview

This repo hosts **two Flask applications** served from a single unified process on port 5003:

| App | URL prefix | Description |
|-----|-----------|-------------|
| **Pipeline Portal** | `/portal/...` | Flame & Gas product pipeline — priority board, resource overview, Gantt charts, card projects |
| **Programs Dashboard** | `/dashboard/...` | Per-project Gantt dashboard — task editing, discipline resource tracking |

Both apps share a single SQLite database (`database/dashboards.db`).

The entry point is **`unified_server.py`** — it mounts both apps as Flask Blueprints.

> **Note:** The old standalone `Pipeline Portal/` folder (separate Flask app on port 5003) is **obsolete** and can be deleted. All code now lives here.

---

## Directory Structure

```
Program_Project Management overview/      ← git repo root
├── unified_server.py                     # Entry point — mounts both apps
├── server.py                             # Dashboard Blueprint registration
├── database_manager.py                   # Dashboard DB queries
├── config.py                             # Shared config (port, paths, disciplines)
├── excel_parser.py                       # Dashboard Excel parser
├── excel_exporter.py                     # Dashboard Excel export
├── ppt_exporter.py                       # Dashboard PowerPoint export
│
├── portal/                               # Portal package
│   ├── __init__.py
│   ├── routes.py                         # Portal Blueprint registration + all routes
│   ├── database_manager.py               # Portal DB queries
│   ├── excel_parser.py                   # Gantt Excel parser
│   ├── priority_parser.py                # Priority List Excel parser
│   └── ppt_exporter.py                   # Portal PowerPoint export
│
├── templates/
│   ├── dashboard/                        # Dashboard templates
│   │   ├── dashboard.html
│   │   ├── disciplines.html
│   │   ├── index.html
│   │   └── project_schematic.html
│   └── portal/                           # Portal templates
│       ├── index.html                    # Portfolio homepage (Priority Board, Resources, Schedule, Projects)
│       ├── project_detail.html           # Single project — card view
│       ├── gantt.html                    # Single project — Gantt timeline view
│       └── settings.html                 # Discipline mapping configuration
│
├── database/
│   └── dashboards.db                     # Shared SQLite database
├── exports/                              # Excel/PPT download output
└── logs/                                 # server.log
```

---

## Blueprint Architecture

`unified_server.py` calls two registration functions:

```python
from server import register_dashboard
from portal.routes import register_portal

register_dashboard(app)   # mounts /dashboard/... page routes + /api/... dashboard API
register_portal(app)      # mounts /portal/... page routes + /api/... portal API
```

**URL prefix strategy:**
- Page routes use prefixes: `/portal/...` and `/dashboard/...`
- API routes have **no prefix** — they stay at `/api/...` so no JavaScript changes were needed

```python
# server.py
def register_dashboard(app):
    app.register_blueprint(dashboard_pages, url_prefix='/dashboard')
    app.register_blueprint(dashboard_api)   # no prefix

# portal/routes.py
def register_portal(app):
    db.initialize_database()
    app.register_blueprint(portal_pages, url_prefix='/portal')
    app.register_blueprint(portal_api)      # no prefix
```

Portal's API routes are a **superset** of Dashboard's. Where routes conflict, the Portal version is used (Dashboard's conflicting routes are removed from `server.py`).

---

## Shared Database Architecture

**Database path:** `database/dashboards.db`

Both apps read and write this single file.

### Tables owned by Dashboard (reused by Portal, never modified)

| Table | Description |
|-------|-------------|
| `projects` | Gantt project master (name, manager, excel_filename) |
| `tasks` | Individual tasks within each gantt project |
| `resource_teams` | Owner → discipline mapping (`team_name` = discipline name) |

### Tables added by Portal (portal-only)

| Table | Description |
|-------|-------------|
| `portfolio_projects` | Top-level project registry for the pipeline |
| `project_resources` | Per-project × discipline resource coverage/demand |
| `card_data` | Card-view metadata (start/end dates, owner, description) |
| `action_items` | Action items per project |
| `risks` | Risk register per project |
| `certifications` | Certification tracking per project |
| `updates_log` | Activity feed / update history |
| `priority_history` | Audit trail of priority reordering |
| `monthly_snapshots` | Monthly portfolio snapshots (stored as JSON) |
| `task_dependencies` | Task predecessor/successor pairs |
| `gate_baselines` | Baseline dates for gate milestones |
| `gate_change_log` | Gate date change history with days-delayed |
| `gate_sign_offs` | Gate sign-off records with rework dates |

### Key Relationship

```
portfolio_projects.project_id  →  projects.id
```

`portfolio_projects` holds the FK pointing to `projects`. The `projects` table is untouched — no new columns added. Projects with `management_type = 'gantt'` have a non-null `project_id`; card projects have `project_id = NULL`.

---

## Project Management Types

Every project in `portfolio_projects` has a `management_type` field:

| Type | Description | Template |
|------|-------------|----------|
| `card` | Lightweight status card — action items, risks, certs, updates | `portal/project_detail.html` |
| `gantt` | Full Gantt timeline linked to a `projects` row | `portal/gantt.html` |

---

## Portal Route Reference (portal/routes.py)

### Page Routes (prefix: `/portal`)

| Route | Description |
|-------|-------------|
| `GET /portal/` | Homepage — Priority Board, Resources, Schedule, Projects tabs |
| `GET /portal/project/<id>` | Project detail — card or gantt view |
| `GET /portal/settings` | Discipline mapping settings |

### Portfolio Projects API

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/portfolio/projects` | List all projects (sorted by priority) |
| POST | `/api/portfolio/projects` | Create project + init resource rows |
| PATCH | `/api/portfolio/projects/<pid>` | Update project fields |
| DELETE | `/api/portfolio/projects/<pid>` | Delete project |
| POST | `/api/portfolio/projects/<pid>/set-type` | Switch management type |

### Priority Management

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/portfolio/reorder` | Drag-reorder priorities |
| POST | `/api/portfolio/import-preview` | Parse Excel priority list, return diff |
| POST | `/api/portfolio/import-apply` | Apply approved changes |

### Gantt Task API

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/gantt/import` | Upload Gantt Excel → creates/updates project + tasks |
| GET | `/api/project/<name>/tasks` | List all tasks (plain array) |
| GET | `/api/project/<name>/dependencies` | List task dependencies |
| POST | `/api/project/<name>/task` | Create task |
| PUT | `/api/project/<name>/task/<id>` | Update task |
| DELETE | `/api/project/<name>/task/<id>` | Delete task |
| POST | `/api/project/<name>/dependencies` | Add dependency |
| DELETE | `/api/project/<name>/dependencies/<id>` | Remove dependency |

### Gate Tracking

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/project/<name>/gate-baselines` | Gate baseline dates |
| GET | `/api/project/<name>/gate-sign-offs` | Gate sign-off records |
| GET | `/api/project/<name>/gate-change-log` | Gate delay history |

### Card-View Data

| Method | Route | Description |
|--------|-------|-------------|
| GET/PUT | `/api/portfolio/projects/<pid>/card` | Card metadata |
| GET/POST/PATCH/DELETE | `/api/portfolio/projects/<pid>/actions` | Action items |
| GET/POST/PATCH/DELETE | `/api/portfolio/projects/<pid>/risks` | Risks |
| GET/POST/PATCH/DELETE | `/api/portfolio/projects/<pid>/certs` | Certifications |
| GET/POST/DELETE | `/api/portfolio/projects/<pid>/updates` | Activity feed |

### Resource Management

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/portfolio/projects/<pid>/resources` | Per-discipline resource grid |
| PUT | `/api/portfolio/projects/<pid>/resources` | Set manual overrides |
| POST | `/api/portfolio/projects/<pid>/resources/recompute` | Clear overrides, recompute |

### Portfolio Aggregation

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/portfolio/overview` | Resource contention matrix |
| GET | `/api/portfolio/gate-timeline` | All gates across all gantt projects |
| GET/POST | `/api/portfolio/snapshots` | List / create monthly snapshots |
| GET | `/api/portfolio/snapshots/<id>` | Single snapshot |

### Slide Export

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/portfolio/projects/<pid>/generate-slide` | Generate PowerPoint status slide |

---

## Homepage Tabs (portal/index.html)

| Tab | Content |
|-----|---------|
| **Priority Board** | Drag-reorderable table — Mgmt type, gate, launch, objective, status |
| **Resource Overview** | Grid: projects × disciplines — coverage and demand days |
| **Portfolio Schedule** | Visual Gantt across all projects — gate timelines 2025–2029 |
| **Projects** | Card grid — "View Gantt →" (gantt) or CARD badge per project |

---

## Resource Computation Logic

When tasks are imported or updated for a gantt project, `compute_and_store_gantt_resources()` runs:

**Coverage** (per discipline):
- `Fully` — All tasks for this discipline have an owner assigned
- `Partially` — Some tasks are missing an owner
- `No` — No tasks have an owner
- `N/A` — No tasks assigned to this discipline at all

**Demand** (working days in next 60 days):
- Sum of working-day durations of tasks belonging to each owner/discipline
- Thresholds (from config): Large > 16 days, Medium 5–16, Small < 5

**Manual override:** If a resource row is flagged `is_manual_override = 1`, automatic recomputation skips it.

**Discipline mapping:** `resource_teams` table maps `owner_name → team_name` (team_name IS the discipline). Values used directly — no translation layer.

---

## Gantt Import Flow

When a Gantt Excel file is uploaded via `POST /api/gantt/import`:

1. `ExcelParser.parse_excel_file()` reads the file
   - Row 3 col C = project name
   - Row 5 col C = project manager
   - Row 10 = headers, rows 11+ = tasks
   - Gates detected by regex `Gate \d+` → `milestone = 1`
2. `create_or_update_gantt_project()` finds or creates a `projects` row, links via `portfolio_projects.project_id`
3. `insert_tasks_bulk()` replaces all existing tasks
4. `_auto_detect_dependencies()` creates finish-to-start edges for task pairs with ≤ 2 day gap
5. `set_gate_baseline()` records baseline dates for all milestone tasks
6. `update_portfolio_project()` sets `management_type = 'gantt'`
7. `compute_and_store_gantt_resources()` recomputes coverage/demand

---

## Configuration (config.py)

```python
SERVER_PORT = 5003
DATABASE_PATH = BASE_DIR / 'database' / 'dashboards.db'
EXCEL_OUTPUT_FOLDER = BASE_DIR / 'exports'
LOG_FOLDER = BASE_DIR / 'logs'

# Excel column layout
EXCEL_PROJECT_NAME_ROW = 3   # col C
EXCEL_MANAGER_ROW = 5        # col C
EXCEL_HEADER_ROW = 10
EXCEL_DATA_START_ROW = 11

# Resource demand thresholds (working days)
DEMAND_LARGE_DAYS  = 16    # > 16 → Large
DEMAND_MEDIUM_DAYS =  5    # 5-16 → Medium
                           # < 5  → Small

# 15 disciplines (must match Excel and priority list column order)
DISCIPLINES = [
    'Proj. Mgmt', 'Optics', 'EE', 'ME', 'SW DEV', 'R&D QA',
    'Sderot Cert.', 'RSK Cert.', 'ATE', 'NPD & Main.',
    'FCT', 'RSK Ops', 'Sderot', 'RSK', 'Product Mgmt',
]
```

---

## Excel Priority List Import (portal/priority_parser.py)

Parses the Flame & Gas Project Priority List Excel workbook:

- Auto-selects the latest dated sheet (e.g., `Mar26 > Feb26`)
- Sections detected by header keywords: Active Big Projects / Small Projects / On Hold / Proposed
- **Big projects** columns: A–H = metadata, J–X = coverage per discipline, AA–AM = demand per discipline
- Demand labels converted to working-day midpoints: Large=24, Medium=10, Small=2.5, N/A=0
- Import preview shows diff (new / changed) vs. existing DB before applying

---

## PowerPoint Export (portal/ppt_exporter.py)

`generate_project_slide()` produces a single-slide summary including:
- Project header (name, priority, leader, process type)
- Gantt task timeline grid (phases, owners, dates, status) — gantt projects only
- Risks (impact/probability)
- Certifications table
- Action items list
- Resource availability grid (color-coded by coverage)
- Recent updates activity feed

Styling follows Emerson brand palette (navy / blue / green / orange / red).

---

## Linked Projects

Two gantt projects from the Dashboard are linked to Portal portfolio projects:

| Portfolio Project | Portfolio ID | Gantt Project | `projects.id` |
|-------------------|-------------|---------------|----------------|
| 628MP and 628EC Size 4 sensors 925/926 | 7 | 628MP-F31, Nevada Nano Low Power Combustible Sensor | 2 |
| 926 Point Gas Transmitter | 9 | Saturn Project | 7 |

---

## Template Caching Note

Flask non-debug mode caches Jinja2 templates in memory. `TEMPLATES_AUTO_RELOAD = True` is set in `unified_server.py` so template changes take effect on browser refresh — but only if the running process picked up this config.

If templates are not updating:
1. Get PID: `Get-NetTCPConnection -LocalPort 5003 -State Listen | Select-Object -ExpandProperty OwningProcess`
2. Kill it: `Stop-Process -Id <PID> -Force`
3. Start fresh: `python unified_server.py`

---

## Summary Stats

| Item | Count |
|------|-------|
| Flask Blueprints | 4 (dashboard_pages, dashboard_api, portal_pages, portal_api) |
| Portal Flask routes | 50+ |
| Python files | 10 |
| HTML templates | 8 (4 dashboard + 4 portal) |
| Database tables (portal-owned) | 13 |
| Database tables (shared/reused) | 3 |
| Disciplines | 15 |
| Server port | 5003 |
