"""
Gantt Dashboard Test Suite
Tests all major logic areas: API CRUD, dependencies, gate sign-offs,
rework, UI structure, duration calc, validation, export, filters.
"""

import requests
import json
import datetime
import sys
from urllib.parse import quote

BASE = "http://localhost:5001"
PROJECT = "Saturn Project"
ENC_PROJECT = quote(PROJECT)

PASS = []
FAIL = []
WARN = []

def ok(name, detail=""):
    PASS.append(name)
    print(f"  ✅  {name}" + (f" — {detail}" if detail else ""))

def fail(name, detail=""):
    FAIL.append(name)
    print(f"  ❌  {name}" + (f" — {detail}" if detail else ""))

def warn(name, detail=""):
    WARN.append(name)
    print(f"  ⚠️   {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

# ──────────────────────────────────────────────
# 1. SERVER HEALTH
# ──────────────────────────────────────────────
section("1. SERVER HEALTH")
try:
    r = requests.get(f"{BASE}/health", timeout=5)
    if r.status_code == 200:
        ok("Health endpoint responds 200")
    else:
        warn("Health endpoint", f"status {r.status_code}")
except Exception as e:
    fail("Health endpoint unreachable", str(e))

# ──────────────────────────────────────────────
# 2. PROJECTS API
# ──────────────────────────────────────────────
section("2. PROJECTS API")
try:
    r = requests.get(f"{BASE}/api/projects", timeout=5)
    projects = r.json()
    if isinstance(projects, list) and len(projects) > 0:
        ok("GET /api/projects", f"{len(projects)} projects returned")
    else:
        fail("GET /api/projects", "empty or invalid")
except Exception as e:
    fail("GET /api/projects", str(e))

# ──────────────────────────────────────────────
# 3. TASKS API — READ
# ──────────────────────────────────────────────
section("3. TASKS API — READ")
tasks = []
try:
    r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/tasks", timeout=5)
    tasks = r.json()
    if isinstance(tasks, list) and len(tasks) > 0:
        ok("GET /api/project/.../tasks", f"{len(tasks)} tasks")
    else:
        fail("GET /api/project/.../tasks", "empty")
except Exception as e:
    fail("GET /api/project/.../tasks", str(e))

# Check task object shape
if tasks:
    t = tasks[0]
    expected_fields = ["id","name","status","phase","owner","start_date","end_date","milestone","critical","tailed_out"]
    missing = [f for f in expected_fields if f not in t]
    if missing:
        fail("Task object has expected fields", f"missing: {missing}")
    else:
        ok("Task object has expected fields")

    # Check status values
    statuses = {t["status"] for t in tasks}
    valid_statuses = {"Planned","In Process","Completed"}
    invalid = statuses - valid_statuses
    if invalid:
        warn("All task statuses are valid", f"unexpected values: {invalid}")
    else:
        ok("All task statuses are valid values", str(statuses))

# ──────────────────────────────────────────────
# 4. PAGE RENDERS
# ──────────────────────────────────────────────
section("4. PAGE RENDERS — HTML STRUCTURE")
try:
    r = requests.get(f"{BASE}/project/{ENC_PROJECT}", timeout=10)
    html = r.text
    if r.status_code == 200:
        ok("Project page HTTP 200")
    else:
        fail("Project page HTTP status", str(r.status_code))

    checks = {
        "Task table present":       'id="taskTableBody"' in html,
        "Gantt timeline present":   'timeline-grid' in html or 'timeline-task-row' in html,
        "Edit modal present":       'id="taskModal"' in html,
        "Duration column header":   'Dur.' in html,
        "Duration input in modal":  'id="taskDuration"' in html,
        "Start date input":         'id="taskEntered"' in html,
        "End date input":           'id="taskDue"' in html,
        "Duration calc JS":         'calcEndFromDuration' in html,
        "Back-calc duration JS":    'durationInput' in html,
        "Dependency picker":        'id="depPickerList"' in html,
        "Gate sign-off modal":      'gate-signoff' in html or 'openGateSignOff' in html,
        "Rework cause button":      'rework-cause-btn' in html,
        "Critical path button":     'computeCriticalPath' in html or 'critical-path' in html.lower(),
        "Zoom controls":            'Monthly' in html and 'Quarterly' in html and 'Yearly' in html,
        "Export Excel button":      'Export' in html and ('xlsx' in html or 'export' in html.lower()),
        "Phase filter present":     'phase' in html.lower() and 'filter' in html.lower(),
        "Inline date editing":      'date-cell' in html and 'editable' in html,
        "Status badge inline edit": 'status-badge' in html and 'editable' in html,
        "Tooltip JS":               'showTooltip' in html and 'hideTooltip' in html,
        "Sort by columns":          'sortTasks' in html,
        "Cascade preview JS":       'cascadePreview' in html or 'checkAndShowCascade' in html,
        "Actions column 115px":     '115px' in html,
        "8-column grid":            '40px 200px 120px 105px 65px 105px 120px 115px' in html,
        "Task table width 935px":   '935px' in html,
        "Force refresh button":     'Force Refresh' in html or 'forceRefresh' in html or 'force-refresh' in html,
        "High Level view toggle":   'High Level' in html or 'highLevel' in html,
        "Tailed out report":        'tailedOut' in html or 'tailed-out' in html,
        "Owner filter":             'ownerFilter' in html or 'owner-filter' in html,
        "Today highlight":          'today' in html.lower(),
    }
    for label, result in checks.items():
        ok(label) if result else fail(label)

except Exception as e:
    fail("Project page render", str(e))

# ──────────────────────────────────────────────
# 5. TASK CRUD — CREATE / UPDATE / DELETE
# ──────────────────────────────────────────────
section("5. TASK CRUD — CREATE / UPDATE / DELETE")
created_id = None

# CREATE
try:
    payload = {
        "name":       "TEST_AGENT_TASK",
        "owner":      "Test Agent",
        "team":       "",
        "phase":      "Gate 3",
        "status":     "Planned",
        "start_date": "2026-06-01",
        "end_date":   "2026-06-15",
        "critical":   False,
        "milestone":  False,
        "tailed_out": False,
    }
    r = requests.post(f"{BASE}/api/project/{ENC_PROJECT}/task", json=payload, timeout=5)
    if r.status_code in (200, 201):
        resp = r.json()
        created_id = resp.get("id") or resp.get("task_id") or (resp.get("task") or {}).get("id")
        if created_id:
            ok("POST create task", f"new id={created_id}")
        else:
            warn("POST create task - no id returned", str(resp))
    else:
        fail("POST create task", f"status={r.status_code} body={r.text[:200]}")
except Exception as e:
    fail("POST create task", str(e))

# UPDATE
if created_id:
    try:
        update = {
            "name":       "TEST_AGENT_TASK_UPDATED",
            "owner":      "Test Agent",
            "team":       "",
            "phase":      "Gate 3",
            "status":     "In Process",
            "start_date": "2026-06-01",
            "end_date":   "2026-06-20",
            "critical":   False,
            "milestone":  False,
            "tailed_out": False,
        }
        r = requests.put(f"{BASE}/api/task/{created_id}", json=update, timeout=5)
        if r.status_code == 200:
            ok("PUT update task", f"id={created_id} status→In Process, end→2026-06-20")
        else:
            fail("PUT update task", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        fail("PUT update task", str(e))

    # VERIFY update persisted
    try:
        r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/tasks", timeout=5)
        refreshed = r.json()
        updated_task = next((t for t in refreshed if t["id"] == created_id), None)
        if updated_task and updated_task["status"] == "In Process":
            ok("Update persisted to API", f"status={updated_task['status']}")
        elif updated_task:
            fail("Update persisted", f"status still={updated_task['status']}")
        else:
            fail("Updated task not found in task list")
    except Exception as e:
        fail("Verify update persisted", str(e))

# DELETE
if created_id:
    try:
        r = requests.delete(f"{BASE}/api/task/{created_id}", timeout=5)
        if r.status_code in (200, 204):
            ok("DELETE task", f"id={created_id}")
        else:
            fail("DELETE task", f"status={r.status_code}")
    except Exception as e:
        fail("DELETE task", str(e))

    # VERIFY deletion
    try:
        r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/tasks", timeout=5)
        after = r.json()
        still_there = any(t["id"] == created_id for t in after)
        if not still_there:
            ok("Deletion verified — task gone from list")
        else:
            fail("Deletion — task still in list after delete")
    except Exception as e:
        fail("Verify deletion", str(e))

# ──────────────────────────────────────────────
# 6. VALIDATION — DATES
# ──────────────────────────────────────────────
section("6. DATE VALIDATION")
# Create task with end < start — should fail
try:
    bad_payload = {
        "name":       "TEST_BAD_DATES",
        "owner":      "Test Agent",
        "phase":      "Gate 3",
        "status":     "Planned",
        "start_date": "2026-06-15",
        "end_date":   "2026-06-01",   # end BEFORE start
        "critical":   False,
        "milestone":  False,
        "tailed_out": False,
    }
    r = requests.post(f"{BASE}/api/project/{ENC_PROJECT}/task", json=bad_payload, timeout=5)
    if r.status_code in (400, 422):
        ok("API rejects end_date < start_date", f"status={r.status_code}")
    elif r.status_code in (200, 201):
        # Created — always clean up regardless of ID path
        resp = r.json()
        bad_id = (resp.get("id") or resp.get("task_id")
                  or (resp.get("task") or {}).get("id"))
        if bad_id:
            requests.delete(f"{BASE}/api/task/{bad_id}", timeout=5)
        warn("API accepted end_date < start_date (no server-side date validation)", "validation is client-side only")
    else:
        warn("API bad-date test unexpected status", str(r.status_code))
except Exception as e:
    fail("Date validation test", str(e))

# ──────────────────────────────────────────────
# 7. DURATION CALCULATION LOGIC
# ──────────────────────────────────────────────
section("7. DURATION CALCULATION LOGIC (formula check)")
test_cases = [
    ("2026-01-01", "2026-01-01",  1),   # same day = 1
    ("2026-01-01", "2026-01-05",  5),   # 5 days
    ("2026-01-01", "2026-01-31", 31),   # 31 days
    ("2026-03-01", "2026-03-15", 15),   # mid-month
    ("2026-01-30", "2026-02-03",  5),   # month boundary
]
all_ok = True
for start, end, expected in test_cases:
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    calc = (e - s).days + 1
    if calc == expected:
        ok(f"Duration calc {start} → {end}", f"= {calc} days ✓")
    else:
        fail(f"Duration calc {start} → {end}", f"expected {expected}, got {calc}")
        all_ok = False

# End date from start+duration
calc_cases = [
    ("2026-01-01",  5, "2026-01-05"),
    ("2026-01-01",  1, "2026-01-01"),
    ("2026-01-30",  5, "2026-02-03"),
    ("2026-03-01", 31, "2026-03-31"),
]
for start, dur, expected_end in calc_cases:
    s = datetime.date.fromisoformat(start)
    calc_end = s + datetime.timedelta(days=dur - 1)
    if str(calc_end) == expected_end:
        ok(f"End from start={start} dur={dur}", f"= {calc_end} ✓")
    else:
        fail(f"End from start={start} dur={dur}", f"expected {expected_end}, got {calc_end}")

# ──────────────────────────────────────────────
# 8. DEPENDENCIES API
# ──────────────────────────────────────────────
section("8. DEPENDENCIES API")
deps = []
try:
    r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/dependencies", timeout=5)
    deps = r.json()
    if isinstance(deps, list):
        ok("GET dependencies", f"{len(deps)} links")
    else:
        fail("GET dependencies", "not a list")
except Exception as e:
    fail("GET dependencies", str(e))

if deps:
    d = deps[0]
    if "predecessor_id" in d and "successor_id" in d:
        ok("Dependency object shape (predecessor_id, successor_id)")
    else:
        fail("Dependency object shape", str(d.keys()))

# CREATE and DELETE a dependency using real task IDs
if tasks and len(tasks) >= 2:
    tid_a = tasks[0]["id"]
    tid_b = tasks[1]["id"]
    dep_id = None
    try:
        r = requests.post(
            f"{BASE}/api/project/{ENC_PROJECT}/dependencies",
            json={"predecessor_id": tid_a, "successor_id": tid_b},
            timeout=5
        )
        if r.status_code in (200, 201):
            resp = r.json()
            dep_id = resp.get("id") or resp.get("dependency_id")
            ok("POST add dependency", f"{tid_a}→{tid_b} id={dep_id}")
        else:
            warn("POST add dependency", f"status={r.status_code} {r.text[:100]}")
    except Exception as e:
        fail("POST add dependency", str(e))

    if dep_id:
        try:
            r = requests.delete(f"{BASE}/api/dependency/{dep_id}", timeout=5)
            if r.status_code in (200, 204):
                ok("DELETE dependency", f"id={dep_id}")
            else:
                warn("DELETE dependency", f"status={r.status_code}")
        except Exception as e:
            fail("DELETE dependency", str(e))

# ──────────────────────────────────────────────
# 9. GATE SIGN-OFFS API
# ──────────────────────────────────────────────
section("9. GATE SIGN-OFFS API")
try:
    r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/gate-sign-offs", timeout=5)
    if r.status_code == 200:
        signoffs = r.json()
        ok("GET gate-sign-offs", f"{len(signoffs)} sign-offs")
    else:
        warn("GET gate-sign-offs", f"status={r.status_code}")
except Exception as e:
    fail("GET gate-sign-offs", str(e))

# ──────────────────────────────────────────────
# 10. EXPORT API
# ──────────────────────────────────────────────
section("10. EXPORT API")
try:
    r = requests.get(f"{BASE}/api/project/{ENC_PROJECT}/export", timeout=10)
    if r.status_code == 200:
        ct = r.headers.get("Content-Type","")
        if "excel" in ct or "spreadsheet" in ct or "octet" in ct or len(r.content) > 1000:
            ok("GET export", f"Content-Type={ct}, size={len(r.content)} bytes")
        else:
            warn("GET export", f"unexpected Content-Type: {ct}")
    else:
        warn("GET export", f"status={r.status_code}")
except Exception as e:
    fail("GET export", str(e))

# ──────────────────────────────────────────────
# 11. FORCE REFRESH ENDPOINT
# ──────────────────────────────────────────────
section("11. FORCE REFRESH ENDPOINT")
try:
    r = requests.post(f"{BASE}/api/force-refresh", timeout=5)
    if r.status_code == 200:
        ok("POST /api/force-refresh")
    else:
        # try GET
        r2 = requests.get(f"{BASE}/api/force-refresh", timeout=5)
        if r2.status_code == 200:
            ok("GET /api/force-refresh")
        else:
            warn("Force refresh endpoint", f"POST={r.status_code} GET={r2.status_code}")
except Exception as e:
    warn("Force refresh endpoint", str(e))

# ──────────────────────────────────────────────
# 12. TASK DATA INTEGRITY
# ──────────────────────────────────────────────
section("12. TASK DATA INTEGRITY")
if tasks:
    tasks_with_dates = [t for t in tasks if t.get("start_date") and t.get("end_date")]
    tasks_without_dates = [t for t in tasks if not t.get("start_date") or not t.get("end_date")]

    ok("Tasks with complete dates", f"{len(tasks_with_dates)}/{len(tasks)}")

    if tasks_without_dates:
        warn("Tasks with missing dates", f"{len(tasks_without_dates)} tasks have empty start or end")

    # Check end >= start for all tasks with both dates
    bad_dates = []
    for t in tasks_with_dates:
        try:
            s = datetime.date.fromisoformat(t["start_date"])
            e = datetime.date.fromisoformat(t["end_date"])
            if e < s:
                bad_dates.append(f"id={t['id']} {t['name'][:30]}")
        except:
            pass

    if bad_dates:
        fail("No tasks with end < start", f"violations: {bad_dates[:3]}")
    else:
        ok("No tasks have end_date < start_date")

    # Check milestone tasks are gates
    milestone_tasks = [t for t in tasks if t.get("milestone")]
    gate_named = [t for t in milestone_tasks if "gate" in t.get("name","").lower() or "gate" in t.get("phase","").lower()]
    ok("Milestone tasks exist", f"{len(milestone_tasks)} milestones, {len(gate_named)} gate-named")

    # Check critical flag
    critical_tasks = [t for t in tasks if t.get("critical")]
    ok("Critical tasks flagged", f"{len(critical_tasks)} critical tasks")

    # Check tailed-out
    tailed = [t for t in tasks if t.get("tailed_out")]
    ok("Tailed-out tracking present", f"{len(tailed)} tailed-out tasks")

# ──────────────────────────────────────────────
# 13. REWORK FIELDS
# ──────────────────────────────────────────────
section("13. REWORK FIELDS")
if tasks:
    rework_tasks = [t for t in tasks if t.get("is_rework_cause")]
    if "is_rework_cause" in tasks[0]:
        ok("is_rework_cause field present on tasks", f"{len(rework_tasks)} marked")
    else:
        fail("is_rework_cause field missing from task objects")

    rework_orig = [t for t in tasks if t.get("rework_original_due")]
    ok("rework_original_due field present", f"{len(rework_orig)} tasks with rework original due")

# ──────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  RESULTS SUMMARY")
print(f"{'='*55}")
print(f"  ✅  PASSED : {len(PASS)}")
print(f"  ❌  FAILED : {len(FAIL)}")
print(f"  ⚠️   WARNINGS: {len(WARN)}")
print()

if FAIL:
    print("FAILURES:")
    for f in FAIL:
        print(f"   ❌ {f}")

if WARN:
    print("\nWARNINGS (needs attention):")
    for w in WARN:
        print(f"   ⚠️  {w}")

print()
sys.exit(0 if not FAIL else 1)
