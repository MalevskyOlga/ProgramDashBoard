# Copilot Instructions — Overall Programs Dashboard

## Architecture

Two independent Flask servers in the same repository:

| Server | File | Port | DB | Purpose |
|--------|------|------|----|---------|
| Main dashboard | `server.py` | 5001 | `database/dashboards.db` (read-write) | Project/task CRUD, Gantt, gate management |
| Aggregate portfolio | `aggregate_server.py` | 5002 | `database/portfolio.db` + attaches `dashboards.db` as read-only | Cross-project RAG, timeline, resource heatmap |

Both servers run `DEBUG_MODE = False` permanently — there is **no auto-reload**. After any `.py` or `.html` change, kill the old process and restart.

## Starting and stopping

```bat
:: Main dashboard (port 5001)
START_SERVER_PERSISTENT.bat
STOP_SERVER.bat

:: Aggregate portfolio (port 5002)
START_AGGREGATE_SERVER.bat
STOP_AGGREGATE_SERVER.bat
```

Logs land in `logs\server.stdout.log` / `logs\server.stderr.log`.

To restart manually from PowerShell:
```powershell
Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory "C:\Users\omalevsky\OneDrive - Emerson\Documents\AI Projects\Overall programs dashboard" -WindowStyle Normal
```
Then verify: `netstat -ano | findstr :5001 | findstr LISTENING`

## Installing dependencies

```bat
pip install -r requirements.txt
```

For the aggregate React frontend (`aggregate_frontend/`):
```bat
cd aggregate_frontend
npm install
npm run dev       :: dev mode
npm run build     :: production build (tsc + vite)
```

## Project structure

```
server.py                   # 5001 Flask routes (55+ endpoints)
database_manager.py         # All SQLite CRUD for dashboards.db
config.py                   # Ports, paths, Excel column mapping
excel_parser.py             # .xlsx → task objects (reads C3=project, C5=manager, rows 11+)
excel_exporter.py           # Tasks → .xlsx
ppt_exporter.py             # Gantt → PowerPoint (.pptx)
aggregate_server.py         # 5002 entrypoint
aggregate_app.py            # 5002 Flask factory + 40+ routes
aggregate_repository.py     # RAG/gate/utilisation calculations
aggregate_db.py             # SQLite WAL + ATTACH helpers for 5002
aggregate_config.py         # 5002 config (port, DB paths, fiscal year start)
templates/
  index.html                # Home page — tabs: Portfolio Schedule, Resource Load, Projects, Critical Path
  dashboard.html            # Per-project Gantt (~5400 lines, all JS inline)
  project_schematic.html    # PPT export preview
aggregate_frontend/         # React 18 + TypeScript + Tailwind + D3.js + Vite
aggregate_templates/        # Jinja2 templates for 5002
database/
  dashboards.db             # Source of truth (written by 5001 only)
  portfolio.db              # 5002's own tables
```

## API conventions

- `GET /`, `/project/<name>` → Jinja2 HTML templates
- `GET|POST|PUT|DELETE /api/*` → always `jsonify()`, never plain text
- 5001 routes: `/api/project/<name>/...`, `/api/task/<id>`, `/api/upload-excel`
- 5002 routes: all prefixed `/api/v1/` (e.g. `/api/v1/programme/<id>/rag`)

## Database rules

### `dashboards.db` is read-only for server 5002
Never `INSERT`, `UPDATE`, or `DELETE` on `dashboards.db` from `aggregate_*.py`. All writes from 5002 go to `portfolio.db` only.

### Opening a connection in aggregate code
```python
import sqlite3

def get_db():
    conn = sqlite3.connect("database/portfolio.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("ATTACH 'database/dashboards.db' AS src")
    return conn
```

Always use the `src.` prefix for existing tables:
- `src.projects`, `src.tasks`, `src.task_dependencies`
- `src.gate_baselines`, `src.gate_change_log`, `src.gate_sign_offs`

Tables **without** prefix are in `portfolio.db`:
- `programmes`, `programme_projects`, `resource_teams`, `programme_escalations`

### Schema migration pattern
The codebase uses `ALTER TABLE … ADD COLUMN` wrapped in bare `try/except` at startup, not versioned migration scripts:
```python
try:
    cursor.execute("ALTER TABLE tasks ADD COLUMN new_col INTEGER DEFAULT 0")
except:
    pass  # column already exists
```
Follow this pattern when adding columns to `dashboards.db`.

### Key schema notes
- `tasks.status` values: `'Planned'` | `'In Process'` | `'Completed'`
- `tasks.tailed_out = 1` → task removed from scope; **always exclude from counts, RAG, and critical path**
- `tasks.critical` is a session/display concept — set to 0 in DB; only becomes 1 if user checks it in the Edit modal or a critical path overlay is active
- Gate milestones: `milestone = 1` AND name matches `/gate/i`
- Dependencies auto-detected on import: `0 ≤ B.start_date − A.end_date ≤ 2 days` → Finish-to-Start link

## Canonical formulas (do not alter)

### RAG status
```python
schedule_elapsed_pct = (today - min(start_date)) / (max(end_date) - min(start_date)) * 100
completion_pct       = count(status='Completed') / count(all, excl tailed_out) * 100
schedule_variance    = completion_pct - schedule_elapsed_pct

# Apply in order — first match wins:
# 1. Any gate delayed (days_delayed > 0, no sign-off) → RED
# 2. Gate 'Passed with Rework' + rework tasks open    → AMBER
# 3. schedule_variance < -10                          → RED
# 4. schedule_variance between -10 and +5             → AMBER
# 5. schedule_variance > +5                           → GREEN
```

### Gate type mapping
```python
# Derived from gate_sign_offs + gate_change_log — never assumed:
# 'done'            — status='Passed', no open rework tasks
# 'rework'          — status='Passed with Rework', rework tasks still open
# 'rework_complete' — status='Passed with Rework', rework_sign_off_date is set
# 'delayed'         — gate_change_log has days_delayed > 0, no sign-off record
# 'planned'         — gate_baselines record exists, no gate_sign_offs record
```

### Resource utilisation
```python
# active_tasks = COUNT(tasks) WHERE owner = owner
#   AND start_date <= week_end AND end_date >= week_start
#   AND status IN ('Planned', 'In Process') AND tailed_out = 0
# capacity = resource_teams.capacity_hrs_per_week  (default 37.5)
# util_pct = ROUND(active_tasks / (capacity / 37.5) * 100)
# < 80 → 'low', 80–100 → 'mid', > 100 → 'high'
```

## Frontend conventions

### `templates/dashboard.html` (~5400 lines)
All CSS and JS is inline — there are no separate static asset files. Key globals near line 4464:
```js
let tasks              // in-memory array (all ops use this)
let dependencies       // [{id, project_name, predecessor_id, successor_id}]
let _criticalPathIds   // null | Set<taskId>
const PROJECT_NAME = "{{ project_name }}";  // Jinja2 injection
const API_BASE = '/api/project/' + encodeURIComponent(PROJECT_NAME);
```

JS field mapping (DB column → JS object):
| DB | JS |
|----|----|
| `start_date` | `task.entered` |
| `end_date` | `task.due` |
| `critical` | `task.critical` (boolean) |
| `milestone` | `task.milestone` (boolean) |

Key functions: `loadFromAPI()`, `applyFilters()`, `saveTask()`, `saveToAPI()`, `computeCriticalPath()`, `checkAndShowCascadePreview()`

After editing `dashboard.html`, verify brace balance:
```python
python -c "
import re
with open('templates/dashboard.html', encoding='utf-8') as f: s = re.findall(r'<script(?![^>]*src)[^>]*>([\s\S]*?)</script>', f.read())[0]
print(s.count('{'), s.count('}'), s.count('{')-s.count('}'))
"
```

### `templates/index.html` (home page)
Four tabs: `Portfolio Schedule Overview`, `Overall Resource Load`, `Projects`, `Critical Path`. Tab selection is persisted in `localStorage`. Auto-refreshes every 10 seconds and on tab visibility/focus regain.

Resource table filters are client-side checkbox overlays — look for `tableCheckboxFilters`, `ensureFloatingFilterMenu()`, `applyTableFilters()`. Filter state survives the auto-refresh cycle.

### Aggregate frontend (`aggregate_frontend/`)
React 18 + TypeScript + Tailwind + D3. Never hardcode hex colour values in components — use CSS custom properties defined in `src/styles/tokens.css`. Fiscal year starts **October** (set in `aggregate_config.py`; all quarter logic must go through `utils/dateUtils.ts`).

## Validation workflow

No automated test suite. After changes:
1. Restart the relevant server (kill → `Start-Process`)
2. Verify with `Invoke-WebRequest -UseBasicParsing http://localhost:5001` or open in browser
3. For API changes: `Invoke-WebRequest http://localhost:5001/api/projects`

## Files not committed to git

```
PLANNING.md
dashboards.db
portfolio.db
logs\
MD docs\copilot-instructions.md
```
Do not include these in commits unless explicitly asked.
