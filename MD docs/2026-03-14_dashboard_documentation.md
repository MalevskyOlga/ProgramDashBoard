# 📊 Project Dashboard — Full Feature Documentation

**Technology:** Python Flask + Vanilla JavaScript + SQLite  
**Server:** http://localhost:5001  
**Start:** Double-click `START_SERVER_PERSISTENT.bat`  
**Database:** `database/dashboards.db`

---

## Table of Contents

1. [Task Management](#1-task-management)
2. [Gantt Chart & Timeline](#2-gantt-chart--timeline)
3. [Gate Management & Baselines](#3-gate-management--baselines)
4. [Gate Sign-Off System](#4-gate-sign-off-system)
5. [Gate Pass with Rework](#5-gate-pass-with-rework)
6. [Task Dependencies & Cascade](#6-task-dependencies--cascade)
7. [Critical Path Analysis](#7-critical-path-analysis)
8. [Filtering & Search](#8-filtering--search)
9. [Tailed-Out Tasks](#9-tailed-out-tasks)
10. [Excel Import / Export](#10-excel-import--export)
11. [Database Schema](#11-database-schema)
12. [API Reference](#12-api-reference)

---

## 1. Task Management

### Create & Edit Tasks
- **➕ Add New Task** button opens the task modal
- **✏️ Edit** button on any task row opens the same modal pre-filled
- All changes auto-save with a success notification

**Task fields in modal:**
| Field | Required | Notes |
|---|---|---|
| Task Name | ✅ | Free text |
| Owner | ✅ | Person responsible |
| Phase / Gate | ✅ | Gate 1–5 assignment |
| Start Date | ✅ | Planned start |
| Due Date | ✅ | Planned completion |
| Status | ✅ | Planned / In Process / Completed |
| Depends On | – | Predecessor tasks (dependency picker) |
| Critical | – | Checkbox — marks task as critical |
| Milestone | – | Checkbox — marks as milestone |
| Tailed Out | – | Checkbox — removes from active scope |

### Inline Editing
- **Click any date cell** → inline date picker with ✓ Save / ✗ Cancel
- **Click any status badge** → dropdown (Planned / In Process / Completed)
- All inline edits save immediately to the database

### Task Row Visual States

| State | Appearance |
|---|---|
| Planned | Yellow/orange background |
| In Process | Green background |
| Completed | Gray, low opacity |
| Critical | Red left border + light red background |
| Overdue | Dark red, animated pulse |
| Milestone | Gold border glow |
| Rework Cause | Amber background, orange border |
| Tailed Out | Gray, strikethrough text, 60% opacity |
| Gate Passed | Light green background |
| Gate Passed with Rework | Yellow background, orange left border |

### Statistics Bar
Real-time counts shown across the top:
- Total Tasks · Completed · In Process · Planned · Critical Path · Overdue · Milestones

---

## 2. Gantt Chart & Timeline

### Left Panel — Task Table
Columns: **ID · Task Name · Owner · Start Date · End Date · Status · Actions**

### Right Panel — Gantt Bars
- Bars scale to timeline columns
- Color reflects task status (see table below)
- **Today** is highlighted in yellow in the header

### Gantt Bar Colors

| Status | Color | Height | Notes |
|---|---|---|---|
| Planned | Yellow gradient | 22px | |
| In Process | Green gradient | 22px | |
| Completed | Gray gradient | 22px | Low opacity |
| Critical | Red gradient | 26px | Bold red border |
| Overdue | Dark red | 22px | Animated pulse |
| Milestone / Gate | Red with gold border | 22px | Box-shadow glow |
| Tailed Out | Gray | 22px | 55% opacity, strikethrough |
| Rework Cause | Amber | 22px | Orange border |

### Zoom Levels
| Level | Column Width | Columns |
|---|---|---|
| **Monthly** | 120px | One per month |
| **Quarterly** | 120px | One per quarter |
| **Yearly** | 120px | One per year (default) |

### View Modes
- **📊 Detailed Gantt** — all tasks visible (default)
- **⚡ High Level** — shows only critical path tasks + milestones; badge "Critical Path + Milestones"

### Dependency Arrows
- SVG arrows connect predecessor → successor bars on the Gantt
- **Hover any task row or bar:**
  - **Self:** Dark outline
  - **Predecessors:** Blue outline + brightened
  - **Successors:** Orange outline + brightened
  - **Other tasks:** Dimmed to 18% opacity

---

## 3. Gate Management & Baselines

### What is a Gate?
Any task where `name contains "gate"` AND `milestone = true`.  
Gates are phase sign-off milestones (Gate 1 → Gate 5).

### Gate Baseline
The **original planned date** for each gate, captured at project start.

- **Set baseline:** captured automatically or via API
- **Stored in:** `gate_baselines` table (`UNIQUE` per project + gate name)
- **Purpose:** detect and log schedule slippage

### Gate Change Log
**Button: 📋 Gate Change Log**

Every time a gate's date moves (via cascade or manual edit), an entry is logged:

| Field | Description |
|---|---|
| Gate name | e.g., "Gate 3" |
| Baseline date | Original planned date |
| Old date → New date | Before/after dates |
| Days delayed | Calculated delta |
| Triggered by | Task name + ID that caused the change |
| Impact description | Auto-generated summary |
| Changed at | Timestamp |

The modal shows the full chronological history per gate.  
**Delete gate history:** button inside modal clears a gate's log.

---

## 4. Gate Sign-Off System

### Sign a Gate
Click **🔏 Sign** on any gate row to open the sign-off modal.

**Modal fields:**
- **Sign-off date** — actual date the gate was closed (date picker)
- **Status** (radio):
  - ✅ Passed — gate is final
  - ⚠️ Passed with Rework — gate closes but open tasks remain

### Gate States & Visuals

| State | Row Color | Badge | Sign Button |
|---|---|---|---|
| Not signed | Default | – | 🔏 Sign |
| Passed | Green | ✅ Passed | 🔏 Passed |
| Passed with Rework | Yellow | ⚠ Rework | 🔏 Rework |
| Passed (after Rework) | Green | ⚠ Rework + ✅ Passed | 🔏 Done |

---

## 5. Gate Pass with Rework

### Step 1 — Mark tasks as rework cause
Click **⚠** in the Actions column of any task row.  
- Row turns amber with orange border
- Task's current due date is automatically saved as the **original due date**
- Click ⚠ again to unmark

### Step 2 — Sign gate as "Passed with Rework"
Click 🔏 Sign on the gate → select **⚠️ Passed with Rework** → enter:
- **Sign-off date** — when the gate passed
- **Rework due date** — deadline for completing the remaining rework tasks

The gate row will show:
- `⚠ Rework` badge (amber)
- `🔄 Rework by: [date]` orange pill in the due date column
- `📋 N tasks` log button

### Step 3 — View the Rework Task Log
Click **📋 N tasks** on the gate row.

| Column | Description |
|---|---|
| Task | Rework-cause task name |
| Original DD ✏️ | Due date when first marked — **click date to edit** |
| New DD | Current due date (orange, post-rework) |
| Status | Current task status |

> To fix incorrect original dates: click the date field in "Original DD ✏️", pick the correct date, saved instantly (flashes green).

### Step 4 — Edit rework task dates (no cascade)
Edit the due date of any rework-cause task as normal.  
- **Cascade is skipped** for rework tasks
- Schedule and next gates are **not affected**
- Notification: *"🔄 Rework date updated — schedule not impacted"*

### Step 5 — Final sign-off after rework completes
Click **🔏 Rework** on the gate → select **Passed** → enter final sign-off date.

The gate now shows **both badges simultaneously**:
- `⚠ Rework` (faded amber — historical)
- `✅ Passed` (green — final state)
- Row turns green · Sign button: **🔏 Done**
- Rework due date pill and 📋 log remain visible as audit trail

### Blocking Logic

| Situation | Can sign next gate? |
|---|---|
| Gate = "Passed with Rework" + rework tasks still open | ❌ Blocked |
| Gate = "Passed with Rework" + all rework tasks done | ✅ Allowed |
| Gate = "Passed" (final) | ✅ Allowed |

---

## 6. Task Dependencies & Cascade

### Auto-Detection on Import
When importing Excel, Finish-to-Start dependencies are automatically detected:  
If `Task_B.start_date − Task_A.end_date ≤ 2 days` → B depends on A.

### Manual Dependencies (Edit Modal)
Blue-bordered section **"🔗 Depends On (Predecessors)"**:
- Search tasks by name
- Tasks grouped by phase (collapsible)
- Check/uncheck predecessors
- Saved when the task is saved

**API endpoints:**
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/dependencies` | List all |
| POST | `/api/project/<name>/dependencies` | Create `{predecessor_id, successor_id}` |
| DELETE | `/api/dependency/<id>` | Remove by ID |
| DELETE | `/api/project/<name>/dependencies/by-tasks` | Remove by task pair |

### Cascade Date Change Preview
When a task's **due date changes** and it has downstream successors:

1. System calculates all transitive successor tasks (BFS/DFS)
2. **Preview modal** shows two sections:

**Section A — Tasks That Will Shift:**
| Task Name | Phase | Old Start → New Start | Old Due → New Due |
|---|---|---|---|

**Section B — Gate Impacts** (if any gate baseline is exceeded):
- ⚠️ Gate [name] — which tasks push past it
- Checkbox per gate: "Move Gate [name] deadline to [date]" *(unchecked by default)*

**Footer buttons:**
- **Apply Changes** — saves all shifted tasks + any checked gate moves
- **Cancel** — nothing is changed

> **Rework-cause tasks are exempt** from cascade — their dates can be changed freely.

---

## 7. Critical Path Analysis

### Mark Critical Path
**Button: 🔴 Show Critical Path**  
Identifies the longest chain of dependent tasks end-to-end.

### Longest Chain
**Button: 🔗 Longest Chain**  
Highlights the maximum-duration dependency sequence.

### Critical Task Display
- Red Gantt bar (`#ff1744 → #d50000` gradient)
- 26px tall (taller than standard 22px)
- Bold 3px red border
- Red left border on task row

### High-Level View
**Button: ⚡ High Level**  
Shows only: critical path tasks + milestone tasks + gates.  
Hides all non-critical, non-milestone tasks for executive overview.

---

## 8. Filtering & Search

### Status Filters
Checkboxes (all checked by default):
- ✓ In Process
- ✓ Planned
- ✓ Completed

### Phase / Gate Filter
Dropdown: **All Gates** (default) or select a specific Gate 1–5.

### Owner Filter
Multi-select dropdown:
- **✓ All** button (select all)
- **✕ Clear** button (deselect all)
- Individual owner checkboxes
- Shows: "All Owners ▾" or "X Selected ▾"

### Text Search
"Search tasks..." — searches name, owner, phase in real-time (case-insensitive).

### Special Filters
- **Overdue Only** — tasks with `end_date < today`
- **⭐ Milestones Only** — tasks with `milestone = true`

### Column Sorting
Click any column header to sort:  
⇅ neutral · ▲ ascending · ▼ descending  
**Clear Sort** button resets to default order.

---

## 9. Tailed-Out Tasks

Tasks removed from project scope — different from "Completed."

### Mark as Tailed Out
Checkbox **"🚫 Tailed Out (removed from scope)"** in the Add/Edit Task modal.

### Display
- Gray background, 60% opacity, strikethrough text
- Gantt bar: gray, 55% opacity, strikethrough label

### Tailed Out Report
**Button: 🚫 Tailed Out ([count])**  
Modal lists all tailed-out tasks: name · owner · original due date.  
Useful for scope change tracking and audit.

---

## 10. Excel Import / Export

### Import Excel
**Button: Upload Excel** (on main dashboard)  
File must be `.xlsx` with this structure:

| Cell / Column | Content |
|---|---|
| C3 | Project name |
| C5 | Project manager |
| Row 11+ | Task data |
| Col A | Reference ID |
| Col B | Task name |
| Col C | Phase / Gate |
| Col D | Owner |
| Col E | Start date (YYYY-MM-DD) |
| Col F | Status |
| Col G | End date (YYYY-MM-DD) |
| Col H | Date closed (optional) |
| Col I | Result / notes (optional) |

**Import result:** Tasks imported count · Dependencies detected count.

**API:** `POST /api/upload-excel` (multipart form, field: `file`)

### Export to Excel
**Button: 📊 Export to Excel**  
Downloads current project as `.xlsx`.  
**API:** `GET /api/project/<name>/export`

### Export as Shareable HTML
**Button: 📤 Export Updated HTML (Share This!)**  
Exports the current dashboard view as a **standalone HTML file** — no server or database needed.  
Ideal for weekly status reports and sharing with stakeholders.  
**API:** `GET /api/project/<name>/export-html`

---

## 11. Database Schema

### projects
```sql
id, name (UNIQUE), manager, excel_filename, last_imported, created_at, updated_at
```

### tasks
```sql
id, project_id, reference_id, name, phase, owner,
start_date, end_date, status, date_closed, result,
critical (0/1), milestone (0/1), tailed_out (0/1),
is_rework_cause (0/1), rework_original_due,
row_order, created_at, updated_at
```

### task_dependencies
```sql
id, project_name, predecessor_id, successor_id, created_at
UNIQUE(predecessor_id, successor_id)
```

### gate_baselines
```sql
id, project_name, gate_name, gate_id, baseline_date, created_at
UNIQUE(project_name, gate_name)
```

### gate_change_log
```sql
id, project_name, gate_name, gate_id,
baseline_date, old_date, new_date, days_delayed,
triggered_by_task_id, triggered_by_task_name,
impact_description, changed_at
```

### gate_sign_offs
```sql
id, project_name, gate_name, gate_id,
sign_off_date, rework_due_date, rework_sign_off_date,
status,  -- "Passed" or "Passed with Rework"
created_at, updated_at
UNIQUE(project_name, gate_name)
```

---

## 12. API Reference

### Projects
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/projects` | List all projects |
| GET | `/api/project/<name>` | Get project details |
| GET | `/api/stats` | Server statistics |

### Tasks
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/tasks` | Get all tasks |
| GET | `/api/task/<id>` | Get one task |
| POST | `/api/project/<name>/task` | Create task |
| PUT | `/api/task/<id>` | Update task (any allowed fields) |
| DELETE | `/api/task/<id>` | Delete task |

### Dependencies
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/dependencies` | List dependencies |
| POST | `/api/project/<name>/dependencies` | Create dependency |
| DELETE | `/api/dependency/<id>` | Delete by ID |
| DELETE | `/api/project/<name>/dependencies/by-tasks` | Delete by task pair |

### Gate Baselines
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/gate-baselines` | List baselines |
| POST | `/api/project/<name>/gate-baselines` | Create / update baselines |

### Gate Change Log
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/gate-change-log` | List history |
| POST | `/api/project/<name>/gate-change-log` | Add entry |
| DELETE | `/api/project/<name>/gate-change-log/<gate_name>` | Clear gate history |

### Gate Sign-Offs
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/project/<name>/gate-sign-offs` | List all sign-offs |
| POST | `/api/project/<name>/gate-sign-offs` | Create / update sign-off |
| DELETE | `/api/project/<name>/gate-sign-off/<gate_name>` | Remove sign-off |

### File Operations
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/upload-excel` | Import Excel file |
| GET | `/api/project/<name>/export` | Export as Excel |
| GET | `/api/project/<name>/export-html` | Export as shareable HTML |

---

## Quick Reference — Buttons & Icons

| Button | Where | Action |
|---|---|---|
| 🏠 | Toolbar | Return to main dashboard |
| ➕ Add New Task | Toolbar | Open create task modal |
| 📋 Gate Change Log | Toolbar | View gate deadline history |
| 🔴 Show Critical Path | Toolbar | Highlight critical tasks |
| 🔗 Longest Chain | Toolbar | Show max dependency chain |
| 📊 Export to Excel | Toolbar | Download project as Excel |
| 📤 Export Updated HTML | Toolbar | Share as standalone HTML |
| 🔄 Force Refresh | Toolbar | Reload data from server |
| 📊 Detailed Gantt | Toolbar | Full task view |
| ⚡ High Level | Toolbar | Critical + milestones only |
| 🚫 Tailed Out | Toolbar | Show removed tasks |
| ✏️ | Task row | Edit task modal |
| 🔗 | Task row | Show dependency links |
| ⚠ | Task row | Mark / unmark as rework cause |
| 🔏 Sign / Passed / Rework / Done | Gate row | Gate sign-off modal |
| 📋 N tasks | Gate row | Rework task log popup |
