# New Agent Handoff

## Project focus

Current live product work is happening in the `5001` application, not in `5002`.

The homepage in `5001` has been turned into a management dashboard driven from the detailed gantt data already imported from Excel.

## Current dashboard structure in `5001`

The home page is split into these tabs:

- `Portfolio Schedule Overview`
- `Overall Resource Load`
- `Projects`
- `Critical Path`

Tab selection is persisted in `localStorage`.

## Latest completed work

The most recent UI work was focused on the `Overall Resource Load` tables in `templates\index.html`.

Completed items:

- removed redundant resource panels/cards the user no longer wanted
- made the top summary cards sticky
- separated sticky header structure so scrolling text does not show behind the cards
- widened the dashboard layout to better fill the screen
- added per-column drill-down filters for resource tables
- excluded columns containing `Start` or `End` from filtering
- preserved filter state across the home-page auto-refresh
- moved the filter affordance into the header like Excel
- changed the filter list into a floating overlay so owner names are not cropped
- added `Select all` / `Unselect all`
- improved first-click behavior so choosing one owner can isolate that owner directly

## Latest commit

Latest pushed commit for this work:

- `d0f5f56` — `Refine dashboard table filters`

Previous major dashboard commit:

- `4c13505`

## Important behavior in `5001`

### Resource filtering

The filter system is implemented client-side in `templates\index.html`.

Key points:

- filters are checkbox-based, not text-input based
- filter menus are floating overlays attached to the page body
- active filters survive periodic data refreshes
- `Owner` can be used to narrow to one person and see all tasks for that owner

Main JS/CSS area:

- `templates\index.html`

Look for:

- `tableCheckboxFilters`
- `ensureFloatingFilterMenu()`
- `positionOpenFilterMenu()`
- `renderColumnFilterMenu()`
- `toggleColumnFilterValue()`
- `applyTableFilters()`

### Live refresh

The dashboard refreshes automatically:

- every 10 seconds
- on browser tab visibility regain
- on window focus

This is intended so gantt changes propagate quickly to the management dashboard.

### Critical path

The portfolio critical-path view no longer depends on broad persisted `critical=1` tasks.

Instead, it projects a management-readable chain from gantt/dependency structure toward Gate 5.

Validated examples:

- `628MP-F31, Nevada Nano Low Power Combustible Sensor`
  - `FDR -> Gate 4 -> Certification process ( overall Certifications) -> Gate 5`
- `Saturn Project`
  - `FDR -> Gate 4 -> Certifications -> Gate 5`

## Important files

- `templates\index.html`
  - main homepage UI, tabs, sticky sections, resource filters, critical-path board
- `database_manager.py`
  - portfolio schedule, resource-load, and critical-path data shaping
- `server.py`
  - home-page API routes
- `START_SERVER_PERSISTENT.bat`
  - stable launcher for `5001`
- `STOP_SERVER.bat`
  - stop script for `5001`
- `CURRENT_DASHBOARD_STATUS.md`
  - older status note; useful, but not fully up to date on the newest filter work

## Server notes

### `5001`

- main active management dashboard
- intended URL: `http://localhost:5001`
- start with `START_SERVER_PERSISTENT.bat`
- stop with `STOP_SERVER.bat`

### `5002`

The aggregate application still exists and has working backend slices, but current live UX work from the user has been focused on `5001`.

## Validation style used in this environment

Validation was mainly done by:

- restarting `5001`
- checking the served page with `Invoke-WebRequest`
- inspecting HTML/CSS/JS directly

There was no browser automation or screenshot-perfect test harness here.

## Environment constraints

- Windows environment
- `python` available
- `node`, `npm`, and `pytest` were not available locally during this work

## Git / local files notes

There are local-only files in the repo folder that were intentionally not committed:

- `PLANNING.md`
- `dashboards.db`
- `logs\`
- `MD docs\copilot-instructions.md`

Do not include those in commits unless the user explicitly asks.

## Good starting point for the next agent

1. Read `templates\index.html` first.
2. If the task is data-related, then inspect `database_manager.py` and `server.py`.
3. Restart `5001` after changes and verify the served page.
4. Preserve current tab/resource UX unless the user explicitly asks to change it.

## Current status

At handoff time there are no open tracked todos in the session database.

The dashboard is in a workable state, and the last user-visible request completed was the Excel-style resource table filtering with floating dropdown menus and select-all controls.
