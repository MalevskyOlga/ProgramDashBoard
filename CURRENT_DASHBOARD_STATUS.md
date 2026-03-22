# Overall Programs Dashboard - Current Status

## Current direction

The active product direction is to keep building the management dashboard inside the `5001` application and use the detailed gantts as the source of truth.

The aggregate `5002` application still exists, but the live portfolio/management work is currently centered in `5001`.

## What is working now

- `5001` server start/stop flow was stabilized and the persistent launcher was fixed.
- The home page includes an overall portfolio gate schedule board.
- The home page includes resource summary cards, owner drilldowns, delay visibility, and expandable owner views.
- The home page includes a critical-path management section.

## Critical path behavior

The critical section no longer uses the broad `critical=1` task list as the management view.

Instead, it projects a management chain from the detailed gantts using gate-aware selection logic. The intent is to show the key path to Gate 5 in a management-readable form.

Examples now validated:

- `628MP-F31, Nevada Nano Low Power Combustible Sensor`
  - `FDR -> Gate 4 -> Certification process ( overall Certifications) -> Gate 5`
- `Saturn Project`
  - `FDR -> Gate 4 -> Certifications -> Gate 5`

## Dashboard rendering

The critical section on the `5001` home page is currently rendered as a compact gantt-style board:

- one row per project
- projected path tasks shown in red
- short tasks use outside labels for better readability
- spacing was adjusted to reduce overlap

## Live projection from gantts

Dashboard sections read live data from the gantt database. To make updates appear faster on the home page, the dashboard now:

- refreshes every 10 seconds
- refreshes when the browser tab becomes visible again
- refreshes when the window regains focus

This means gantt edits should project into the management dashboard much faster without needing a full manual reload.

## Main files touched for this work

- `database_manager.py`
- `server.py`
- `templates\index.html`
- `START_SERVER_PERSISTENT.bat`
- `STOP_SERVER.bat`

## Suggested next steps

- further tune the critical-path projection rules if management wants different task selection per phase
- continue cleaning unused CSS/HTML left from earlier dashboard iterations
- keep validating that gantt edits are reflected correctly in the overall dashboard
