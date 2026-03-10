# Feature: Cascade Date Change with Gate Impact Warning

## Overview
When a user changes the **Due Date** of a task via the **Edit Task modal** and saves, the system must:
1. Detect all dependent (successor) tasks — direct and transitive
2. Show a **preview modal** listing every task that will shift
3. Highlight any **Gate Milestones** that would be exceeded by the shifted tasks
4. Ask the user to confirm the cascade **and** separately approve/reject moving each affected gate
5. On confirmation: apply all shifts via API, optionally update gate dates

---

## Trigger
- **Where**: Edit Task modal — Save button (`saveTask()` in `dashboard.html`)
- **Condition**: `taskData.due !== originalTask.due` (due date actually changed)
- **NOT triggered by**: inline Gantt edits, start date changes only

---

## Step-by-Step Flow

### 1. Compute delta
```js
const delta = daysDiff(newDueDate, originalDueDate); // positive = pushed later, negative = pulled earlier
```

### 2. Walk dependency graph — collect all downstream tasks
Recursive BFS/DFS using the global `dependencies` array:
```js
function getDownstreamTasks(taskId, visited = new Set()) {
    // returns array of all transitive successor task objects
}
```
- Uses `dependencies` array (already loaded): `d.predecessor_id === taskId` → `d.successor_id`
- Skip milestones? **No** — shift all types including milestones (except Gate Milestones — handled separately)
- Avoid cycles with `visited` set

### 3. Compute new dates for each downstream task
```js
shiftedTask.newStart = addDays(task.entered, delta);
shiftedTask.newDue   = addDays(task.due,     delta);
```

### 4. Gate impact check
For every gate milestone in `tasks` (where `task.milestone === true && task.name.toLowerCase().includes('gate')`):
- Check if any shifted task's `newDue > gate.due`
- Collect a list of `{ gate, affectedTasks[] }` pairs

### 5. Show Cascade Preview Modal
Single modal with two sections:

#### Section A — Tasks that will shift
| Task Name | Phase | Old Start → New Start | Old Due → New Due |
|-----------|-------|-----------------------|-------------------|
| ...       | ...   | ...                   | ...               |

#### Section B — Gate impacts (only shown if gates are affected)
For each affected gate:
```
⚠️ Gate 3 (2027-06-01) will be exceeded by:
   - "RSK Manufacturing Verification Testing" (new due: 2027-06-15)
   [ ] Move Gate 3 deadline to 2027-06-15
```
Each gate has an independent checkbox — **unchecked by default** (gate locked unless user approves).

#### Footer buttons
- **Apply Changes** — saves all shifted tasks + whichever gate moves were checked
- **Cancel** — no changes applied at all (not even the original task save)

> Note: The original task save and all cascade saves happen together on confirm, or nothing is saved on cancel.

---

## Implementation Plan

### A. `dashboard.html` changes

#### A1. Add Cascade Preview Modal HTML
- New modal `id="cascadePreviewModal"`
- Table of shifted tasks
- Gate impact section with per-gate checkboxes
- Apply / Cancel buttons

#### A2. Function: `getDownstreamTasks(taskId)`
- Already partially exists as `getDownstream()` inside `checkAndShowCascadePreview()` (line ~4112)
- Refactor into a standalone reusable function

#### A3. Function: `buildCascadePreview(changedTask, newDue)`
- Computes delta
- Calls `getDownstreamTasks()`
- Computes new dates for each
- Checks gate impacts
- Returns `{ delta, shiftedTasks, gateImpacts }`

#### A4. Function: `showCascadePreviewModal(preview)`
- Populates and opens the cascade modal
- Returns a Promise that resolves to `{ confirmed: bool, gatesToMove: [gateTaskIds] }`

#### A5. Modify `saveTask()` — inject cascade check
After `saveToAPI(taskData, false)` succeeds for an edited task, before closing modal:
```js
if (delta !== 0 && downstreamTasks.length > 0) {
    const result = await showCascadePreviewModal(preview);
    if (!result.confirmed) { /* undo original save or re-save with old date */ return; }
    // apply cascade shifts
    for (const t of result.shiftedTasks) {
        await saveToAPI({ id: t.id, entered: t.newStart, due: t.newDue, ... }, false);
    }
    // apply approved gate moves
    for (const gateId of result.gatesToMove) {
        await saveToAPI({ id: gateId, due: newGateDate, ... }, false);
    }
}
```

> **Cancel behaviour**: if user cancels the cascade preview, the original task has already been saved. Need to revert it by re-saving with the original due date, OR change the order to: show preview BEFORE saving, then save everything at once on confirm.
> **Recommended**: show preview BEFORE saving. Save original task + all dependents + approved gates all in one go on confirm.

#### A6. Remove old `checkAndShowCascadePreview()` dead code
The partially-written function at line ~4104 should be replaced by the new implementation.

---

### B. `server.py` changes
No new endpoints needed — all saves use the existing `PUT /api/project/<name>/task/<id>` (or equivalent task-update route).

Verify the existing task-update endpoint accepts `start_date` + `end_date` updates (check `api_update_task`).

---

## Data Model Notes (from HANDOFF)

### JS Task fields
- `task.id` — DB integer id
- `task.entered` → `start_date`
- `task.due` → `end_date`
- `task.phase` — phase label
- `task.milestone` — boolean
- `task.name` — task name

### Gate detection (JS)
```js
task.milestone === true && task.name.toLowerCase().includes('gate')
```

### Dependencies global array
```js
// Loaded in loadFromAPI()
dependencies = [{ id, project_name, predecessor_id, successor_id }, ...]
```

---

## Edge Cases to Handle
| Case | Behaviour |
|------|-----------|
| No downstream tasks | Skip cascade preview, save normally |
| Delta = 0 | Skip cascade preview, save normally |
| Circular dependency in graph | `visited` set prevents infinite loop |
| Downstream task is a Gate Milestone | Include in task shift list AND in gate impact section |
| User cancels cascade preview | No saves at all (including original task) |
| Negative delta (date pulled earlier) | Same logic, tasks shift earlier; gate impacts only apply for pushed-later dates |

---

## Files to Edit
- `templates/dashboard.html` — all UI and JS logic
- `server.py` — verify `api_update_task` supports start+end date updates (likely no change needed)

## Key Line References in dashboard.html
- `saveTask()` — line ~3916
- `getDownstream()` (old, inline) — line ~4112
- `checkAndShowCascadePreview()` (old stub) — line ~4104
- `dependencies` global array — line ~1824
- `loadFromAPI()` — line ~1832
- Gate milestone detection — line ~1824 area and `checkGateDeadlineExceeded()`
