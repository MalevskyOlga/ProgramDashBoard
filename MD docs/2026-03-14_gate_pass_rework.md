# Gate Pass with Rework — Feature Documentation

## Overview

A gate can be signed off in two ways:
- **Passed** — gate is fully closed, next gate can be signed
- **Passed with Rework** — gate passes but open tasks remain; a rework due date is set for completion

---

## How to Use

### 1. Mark tasks as rework cause
On any task row, click the **⚠** button in the Actions column to mark it as a cause for rework.  
- Row turns amber to indicate rework status
- Click again to remove the mark
- The task's current due date is automatically saved as the **original due date** at the moment of marking

### 2. Sign a gate as Passed with Rework
Click **🔏 Sign** on a gate row → select **⚠️ Passed with Rework** → enter:
- **Sign-off date** — the actual date the gate passed
- **Rework due date** — deadline by which the rework tasks must be completed

The gate row will show:
- `⚠ Rework` badge (amber)
- `🔄 Rework by: [date]` orange pill on the due date column
- Yellow row background

### 3. View the rework task log
Click **📋 N tasks** on the gate row to open the **Rework Task Log** popup.

| Column | Description |
|---|---|
| Task | Name of the rework-cause task |
| Original DD ✏️ | Due date when the task was first marked as rework cause — **click to edit** |
| New DD | Current due date after rework extension |
| Status | Current task status |

> **To correct original dates:** click the date field in the "Original DD ✏️" column, pick the correct date — saves instantly (flashes green on success).

### 4. Move rework task dates without impacting schedule
Edit the due date of any rework-cause task normally (click the date cell or use the edit modal).  
- The cascade preview is **skipped** for rework tasks
- A notification confirms: *"🔄 Rework date updated — schedule not impacted"*
- The main schedule and next gates are not shifted

### 5. Final sign-off after rework is complete
Once all rework tasks are finished, click **🔏 Rework** on the gate row → select **Passed** → enter the final sign-off date.

The gate row will now show **both** badges simultaneously:
- `⚠ Rework` (faded amber — historical record)
- `✅ Passed` (green — final state)
- Row turns green
- Sign button changes to **🔏 Done**
- Rework due date pill and 📋 log remain visible for audit trail

---

## Blocking Logic

| Situation | Next gate |
|---|---|
| Gate is "Passed with Rework" AND rework tasks still open | ❌ Blocked — cannot sign next gate |
| Gate is "Passed with Rework" AND all rework tasks completed | ✅ Allowed |
| Gate is "Passed" (final, even after rework) | ✅ Allowed |

---

## Data Stored

| Field | Where | Description |
|---|---|---|
| `is_rework_cause` | tasks table | 1 if task is a rework cause |
| `rework_original_due` | tasks table | Due date when task was first marked as rework cause |
| `gate_sign_offs.status` | gate_sign_offs table | "Passed" or "Passed with Rework" |
| `gate_sign_offs.rework_due_date` | gate_sign_offs table | Rework deadline set at gate sign-off |
| `gate_sign_offs.rework_sign_off_date` | gate_sign_offs table | Date of original "Passed with Rework" sign-off (preserved after final pass) |
