# Overall Programs Dashboard — Current Status

**Last updated:** 2026-04-15  
**Branch:** `portal`  
**Port:** 5003  
**URL:** http://localhost:5003  
**DB:** `database/dashboards.db`

---

## How to Start / Stop

```
START_SERVER_PERSISTENT.bat   — start in background (auto-checks if already running)
STOP_SERVER.bat               — stop all server.py processes on port 5003
```

A Windows Task Scheduler task (`OverallProgramsDashboard`) auto-starts `server.py` at login.  
Logs are written to `logs/server.stdout.log` and `logs/server.stderr.log`.

---

## Dashboard Tabs

| Tab | What it shows |
|-----|--------------|
| Portfolio Schedule Overview | Gate timeline across all projects, resource load, critical path |
| Overall Resource Load | Owner workload, task counts, delay visibility |
| Projects | Priority project list + Gantt management (see below) |
| Critical Path | Key path to Gate 5 per project, gantt-style board |

---

## Projects Tab — Priority List

The Projects tab shows the Flame & Gas Active Big Projects priority table (18 rows, seeded from `Flame & Gas Project Priority List.xlsx`).

### Columns
| Column | Type | Notes |
|--------|------|-------|
| # | number | Priority rank |
| Project Name | editable text | Click to edit in-place |
| Leader | editable text | |
| Type | dropdown | NPD / N/A / Cert / OBS |
| Next Gate | dropdown | N/A / Gate 1–5 / Gate C/D |
| Target Date | editable text | |
| Objective | dropdown | Growth / Maintain / Discontinue |
| Segment | dropdown | Industrial / Suppression / All |
| Gantt | link / button | See Gantt management below |

### Gantt Management per Row

Each priority row can have one linked Gantt project dashboard.

**When no Gantt is linked:** shows `📥 Add Gantt ▾` button (hidden until row hover).  
Clicking opens a dropdown:
- `📥 Import from Excel` — upload `.xlsx` file; project name is auto-set to the row's project name
- `🔗 Link existing` — pick from already-imported dashboards

**When a Gantt is linked:** shows `↗ Gantt` link (opens the detailed project dashboard).  
Right-click on `↗ Gantt` opens a context menu:
- `✏️ Rename` — rename the Gantt project (updates all DB tables)
- `🔄 Replace` — re-import from a new Excel file
- `🗑 Delete` — soft-delete with 10-second undo toast; permanently deleted after countdown

**Delete behaviour:**
- Soft-delete sets `is_deleted = 1` on the project (data preserved for undo)
- `linked_dashboard` is set to sentinel `__none__` to prevent auto-match re-showing the link
- Undo within 10 seconds restores `is_deleted = 0` and re-links the row
- After 10 seconds: hard-delete, dashboard data refreshed

---

## Active Gantt Projects (as of 2026-04-15)

| Project | Linked to row |
|---------|--------------|
| Saturn Project | Row 9 — Saturn 926 Point Gas Transmitter |
| 628MP-F31, Nevada Nano Low Power Combustible Sensor | Row 7 — 628MP-F31, Nevada Nano Low Power Combustible Sensor |
| NPD Template Tasks list for overall project | Row 3 (template, no active row link) |

Rows 1–6, 8, 10–18 have no Gantt linked yet.

---

## Key Technical Details

### Server
- Flask 3.x, Python 3.14, port 5003, `DEBUG_MODE = False`
- Every request logged to `logs/server.stdout.log` with timestamp, method, path, status
- 400+ responses also log the response body for debugging

### Database
- `database/dashboards.db` — SQLite with WAL mode
- Key tables: `projects`, `tasks`, `priority_projects`, `gate_sign_offs`, `gate_baselines`, `gate_change_log`, `task_dependencies`, `action_items`, `risks`, `certifications`
- `projects.is_deleted` — soft-delete flag (0 = active, 1 = soft-deleted)
- `priority_projects.linked_dashboard` — explicit Gantt link; `NULL` = auto-match by name; `__none__` = user explicitly has no Gantt

### Auto-match logic
`_build_priority_response` in `server.py`:
1. If `linked_dashboard = '__none__'` → no Gantt (user deleted it)
2. If `linked_dashboard = 'ProjectName'` and project exists (not deleted) → show link
3. If `linked_dashboard` is NULL → fall back to matching project name to row name

### Installer
The `installer/` directory contains a PowerShell-based installer for deploying to new machines.

---

## Main Files

| File | Purpose |
|------|---------|
| `server.py` | Flask app, all API endpoints |
| `database_manager.py` | All DB read/write operations |
| `excel_parser.py` | Parse uploaded `.xlsx` Gantt files |
| `excel_exporter.py` | Export project to Excel |
| `ppt_exporter.py` | Export project schematic to PowerPoint |
| `config.py` | Port, paths, Excel column mapping |
| `templates/index.html` | Single-file frontend (~5000 lines) |
| `START_SERVER_PERSISTENT.bat` | Background server launcher |
| `STOP_SERVER.bat` | Kill all server processes on port 5003 |

---

## Known Behaviours / Watch-outs

- Multiple stale `server.py` processes can accumulate if the server crashes and restarts repeatedly. `STOP_SERVER.bat` kills all of them; if it misses any, kill manually by PID.
- The `START_SERVER_PERSISTENT.bat` skips launch if anything is already listening on port 5003 — even a stale process. If the server seems unresponsive, run `STOP_SERVER.bat` first.
- `excel_parser.py` reads project name from row 3 col C, manager from row 5 col C, task data starting row 11. When importing from a priority row, the row's project name overrides the Excel-parsed name.
