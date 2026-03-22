"""
Data access and derived metrics for the aggregate portfolio dashboard.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import aggregate_config
from aggregate_db import get_connection


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            continue

    return None


def _safe_pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _schedule_elapsed_pct(start_date: date | None, end_date: date | None) -> float:
    if start_date is None or end_date is None:
        return 0.0

    if end_date <= start_date:
        return 100.0 if date.today() >= end_date else 0.0

    total_days = (end_date - start_date).days
    elapsed_days = (date.today() - start_date).days
    elapsed_ratio = max(0.0, min(1.0, elapsed_days / total_days))
    return round(elapsed_ratio * 100, 2)


def _get_quarter(month: int, start_month: int) -> int:
    shifted = (month - start_month) % 12
    return (shifted // 3) + 1


def _get_fiscal_year(target_date: date, start_month: int) -> int:
    if target_date.month >= start_month:
        return target_date.year + 1
    return target_date.year


def _quarter_start(target_date: date, start_month: int) -> date:
    quarter = _get_quarter(target_date.month, start_month)
    quarter_start_month = ((start_month - 1) + (quarter - 1) * 3) % 12 + 1
    year = target_date.year
    if quarter_start_month > target_date.month:
        year -= 1
    return date(year, quarter_start_month, 1)


def _quarter_end(target_date: date, start_month: int) -> date:
    start = _quarter_start(target_date, start_month)
    month_index = (start.month - 1) + 3
    next_year = start.year + (month_index // 12)
    next_month = (month_index % 12) + 1
    next_quarter_start = date(next_year, next_month, 1)
    return next_quarter_start - timedelta(days=1)


def _day_fraction_in_quarter(target_date: date, start_month: int) -> float:
    q_start = _quarter_start(target_date, start_month)
    q_end = _quarter_end(target_date, start_month)
    total_days = max((q_end - q_start).days + 1, 1)
    elapsed_days = (target_date - q_start).days
    return round(max(0.0, min(0.999, elapsed_days / total_days)), 4)


def _calendar_quarter(target_date: date) -> int:
    return ((target_date.month - 1) // 3) + 1


def _open_rework_task_count(project_name: str, conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        WHERE p.name = ?
          AND t.tailed_out = 0
          AND t.is_rework_cause = 1
          AND COALESCE(t.status, '') != 'Completed'
        """,
        (project_name,),
    ).fetchone()
    return int(row["count"]) if row else 0


def _resolve_programme_context(programme_id: int, conn) -> tuple[dict[str, Any], list[str], bool]:
    programme = conn.execute(
        "SELECT * FROM programmes WHERE id = ?",
        (programme_id,),
    ).fetchone()
    if programme is not None:
        project_rows = conn.execute(
            """
            SELECT project_name
            FROM programme_projects
            WHERE programme_id = ?
            ORDER BY display_order, project_name
            """,
            (programme_id,),
        ).fetchall()
        return dict(programme), [row["project_name"] for row in project_rows], False

    if programme_id >= aggregate_config.BOOTSTRAP_PROGRAMME_ID_OFFSET:
        source_project_id = programme_id - aggregate_config.BOOTSTRAP_PROGRAMME_ID_OFFSET
        source_project = conn.execute(
            """
            SELECT
                id,
                name,
                COALESCE(NULLIF(TRIM(manager), ''), 'Unassigned') AS owner
            FROM src.projects
            WHERE id = ?
            """,
            (source_project_id,),
        ).fetchone()
        if source_project is not None:
            project_name = source_project["name"]
            return (
                {
                    "id": programme_id,
                    "name": project_name,
                    "division": aggregate_config.BOOTSTRAP_DIVISION_NAME,
                    "owner": source_project["owner"],
                    "status": "active",
                    "bootstrap_mode": True,
                    "bootstrap_source_project_id": source_project["id"],
                },
                [project_name],
                True,
            )

    raise ValueError(f"Unknown programme id: {programme_id}")


def _resource_risk_count_for_projects(conn, project_names: list[str]) -> int:
    if not project_names:
        return 0

    placeholders = ",".join("?" for _ in project_names)
    row = conn.execute(
        f"""
        WITH owner_load AS (
            SELECT
                rt.owner_name,
                rt.capacity_hrs_per_week,
                COUNT(t.id) AS active_task_count
            FROM resource_teams rt
            JOIN src.tasks t ON t.owner = rt.owner_name
            JOIN src.projects p ON p.id = t.project_id
            WHERE p.name IN ({placeholders})
              AND t.tailed_out = 0
              AND t.status IN ('Planned', 'In Process')
            GROUP BY rt.owner_name, rt.capacity_hrs_per_week
        )
        SELECT COUNT(*) AS count
        FROM owner_load
        WHERE active_task_count > (capacity_hrs_per_week / 37.5)
        """,
        project_names,
    ).fetchone()
    return int(row["count"]) if row else 0


def list_programmes(division: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT p.*, COUNT(pp.id) AS project_count
        FROM programmes p
        LEFT JOIN programme_projects pp ON pp.programme_id = p.id
    """
    params: list[Any] = []
    if division:
        query += " WHERE p.division = ?"
        params.append(division)

    query += " GROUP BY p.id ORDER BY p.name"
    rows = conn.execute(query, params).fetchall()
    persisted = _rows_to_dicts(rows)
    if persisted:
        conn.close()
        return persisted

    if division and division != aggregate_config.BOOTSTRAP_DIVISION_NAME:
        conn.close()
        return []

    source_rows = conn.execute(
        """
        SELECT
            p.id,
            p.name,
            COALESCE(NULLIF(TRIM(p.manager), ''), 'Unassigned') AS owner
        FROM src.projects p
        ORDER BY p.name
        """
    ).fetchall()
    conn.close()
    return [
        {
            "id": aggregate_config.BOOTSTRAP_PROGRAMME_ID_OFFSET + row["id"],
            "name": row["name"],
            "division": aggregate_config.BOOTSTRAP_DIVISION_NAME,
            "owner": row["owner"],
            "status": "active",
            "project_count": 1,
            "bootstrap_mode": True,
            "bootstrap_source_project_id": row["id"],
        }
        for row in source_rows
    ]


def create_programme(name: str, division: str, owner: str, status: str = "active") -> dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO programmes (name, division, owner, status)
        VALUES (?, ?, ?, ?)
        """,
        (name.strip(), division.strip(), owner.strip(), status.strip()),
    )
    programme_id = cursor.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM programmes WHERE id = ?", (programme_id,)).fetchone()
    conn.close()
    return dict(row)


def list_programme_projects(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    _, project_names, bootstrap_mode = _resolve_programme_context(programme_id, conn)
    if bootstrap_mode:
        rows = conn.execute(
            """
            SELECT
                NULL AS id,
                ? AS programme_id,
                p.name AS project_name,
                0 AS display_order,
                p.manager,
                COUNT(t.id) AS task_count
            FROM src.projects p
            LEFT JOIN src.tasks t ON t.project_id = p.id
            WHERE p.name = ?
            GROUP BY p.name, p.manager
            """,
            (programme_id, project_names[0]),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                pp.id,
                pp.programme_id,
                pp.project_name,
                pp.display_order,
                src.projects.manager,
                COUNT(src.tasks.id) AS task_count
            FROM programme_projects pp
            JOIN src.projects ON src.projects.name = pp.project_name
            LEFT JOIN src.tasks ON src.tasks.project_id = src.projects.id
            WHERE pp.programme_id = ?
            GROUP BY pp.id, src.projects.manager
            ORDER BY pp.display_order, pp.project_name
            """,
            (programme_id,),
        ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def list_unassigned_projects() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            p.id,
            p.name,
            p.manager,
            COUNT(t.id) AS task_count,
            SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS completed_count
        FROM src.projects p
        LEFT JOIN src.tasks t ON t.project_id = p.id
        LEFT JOIN programme_projects pp ON pp.project_name = p.name
        WHERE pp.id IS NULL
        GROUP BY p.id, p.name, p.manager
        ORDER BY p.name
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def assign_project_to_programme(programme_id: int, project_name: str, display_order: int = 0) -> dict[str, Any]:
    conn = get_connection()
    project = conn.execute("SELECT id FROM src.projects WHERE name = ?", (project_name,)).fetchone()
    if project is None:
        conn.close()
        raise ValueError(f"Unknown project: {project_name}")

    programme = conn.execute("SELECT id FROM programmes WHERE id = ?", (programme_id,)).fetchone()
    if programme is None:
        conn.close()
        raise ValueError(f"Unknown programme id: {programme_id}")

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO programme_projects (programme_id, project_name, display_order)
        VALUES (?, ?, ?)
        """,
        (programme_id, project_name, display_order),
    )
    mapping_id = cursor.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM programme_projects WHERE id = ?", (mapping_id,)).fetchone()
    conn.close()
    return dict(row)


def list_resource_teams() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, team_name, owner_name, capacity_hrs_per_week
        FROM resource_teams
        ORDER BY team_name, owner_name
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def list_unmapped_owners() -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            t.owner AS owner_name,
            COUNT(*) AS task_count,
            COUNT(DISTINCT p.name) AS project_count
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        LEFT JOIN resource_teams rt ON rt.owner_name = t.owner
        WHERE t.owner IS NOT NULL
          AND TRIM(t.owner) <> ''
          AND rt.id IS NULL
        GROUP BY t.owner
        ORDER BY task_count DESC, owner_name
        """
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def create_resource_team(team_name: str, owner_name: str, capacity_hrs_per_week: float | None) -> dict[str, Any]:
    capacity = capacity_hrs_per_week or aggregate_config.DEFAULT_TEAM_CAPACITY_HOURS
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO resource_teams (team_name, owner_name, capacity_hrs_per_week)
        VALUES (?, ?, ?)
        """,
        (team_name.strip(), owner_name.strip(), capacity),
    )
    team_id = cursor.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM resource_teams WHERE id = ?", (team_id,)).fetchone()
    conn.close()
    return dict(row)


def list_milestone_baselines(programme_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT mb.*
        FROM milestone_baselines mb
    """
    params: list[Any] = []
    if programme_id is not None:
        _, project_names, _ = _resolve_programme_context(programme_id, conn)
        if not project_names:
            conn.close()
            return []
        placeholders = ",".join("?" for _ in project_names)
        query += f" WHERE mb.project_name IN ({placeholders})"
        params.extend(project_names)

    query += " ORDER BY mb.project_name, mb.task_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def upsert_milestone_baseline(project_name: str, task_name: str, baseline_date: str) -> dict[str, Any]:
    conn = get_connection()
    source_task = conn.execute(
        """
        SELECT t.id
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        WHERE p.name = ?
          AND t.name = ?
          AND t.milestone = 1
        LIMIT 1
        """,
        (project_name, task_name),
    ).fetchone()
    if source_task is None:
        conn.close()
        raise ValueError("Milestone baseline can only be set for an existing milestone task")

    conn.execute(
        """
        INSERT INTO milestone_baselines (project_name, task_name, baseline_date)
        VALUES (?, ?, ?)
        ON CONFLICT(project_name, task_name) DO UPDATE SET
            baseline_date = excluded.baseline_date,
            updated_at = CURRENT_TIMESTAMP
        """,
        (project_name, task_name, baseline_date),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT *
        FROM milestone_baselines
        WHERE project_name = ? AND task_name = ?
        """,
        (project_name, task_name),
    ).fetchone()
    conn.close()
    return dict(row)


def list_milestone_candidates(programme_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    query = """
        SELECT
            p.name AS project_name,
            t.name AS task_name,
            t.start_date,
            t.end_date,
            t.status
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        WHERE t.milestone = 1
    """
    params: list[Any] = []
    if programme_id is not None:
        _, project_names, _ = _resolve_programme_context(programme_id, conn)
        if not project_names:
            conn.close()
            return []
        placeholders = ",".join("?" for _ in project_names)
        query += f" AND p.name IN ({placeholders})"
        params.extend(project_names)

    query += " ORDER BY p.name, t.name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def _latest_gate_changes(conn, project_name: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM src.gate_change_log
        WHERE project_name = ?
        ORDER BY gate_name, changed_at DESC, id DESC
        """,
        (project_name,),
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_dict = dict(row)
        latest.setdefault(row_dict["gate_name"], row_dict)
    return latest


def _determine_gate_type(
    project_name: str,
    gate_name: str,
    sign_off: dict[str, Any] | None,
    latest_change: dict[str, Any] | None,
    conn,
) -> str:
    if sign_off:
        if sign_off["status"] == "Passed":
            return "done"
        if sign_off["status"] == "Passed with Rework":
            if sign_off.get("rework_sign_off_date"):
                return "rework_complete"
            if _open_rework_task_count(project_name, conn) > 0:
                return "rework"
            return "rework_complete"

    if latest_change and int(latest_change.get("days_delayed") or 0) > 0:
        return "delayed"

    return "planned"


def _gate_display_date(
    baseline_date: str,
    sign_off: dict[str, Any] | None,
    latest_change: dict[str, Any] | None,
) -> date | None:
    if sign_off and sign_off.get("sign_off_date"):
        return _parse_iso_date(sign_off["sign_off_date"])
    if latest_change and latest_change.get("new_date"):
        return _parse_iso_date(latest_change["new_date"])
    return _parse_iso_date(baseline_date)


def get_programme_timeline(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    programme, project_names, _ = _resolve_programme_context(programme_id, conn)

    timeline_rows: list[dict[str, Any]] = []
    for project_name in project_names:
        baselines = conn.execute(
            """
            SELECT gate_name, baseline_date
            FROM src.gate_baselines
            WHERE project_name = ?
            ORDER BY baseline_date, gate_name
            """,
            (project_name,),
        ).fetchall()
        sign_offs = {
            row["gate_name"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM src.gate_sign_offs WHERE project_name = ?",
                (project_name,),
            ).fetchall()
        }
        changes = _latest_gate_changes(conn, project_name)

        for baseline in baselines:
            gate_name = baseline["gate_name"]
            sign_off = sign_offs.get(gate_name)
            latest_change = changes.get(gate_name)
            display_date = _gate_display_date(baseline["baseline_date"], sign_off, latest_change)
            if display_date is None:
                continue

            timeline_rows.append(
                {
                    "programme_id": programme_id,
                    "programme_name": programme["name"],
                    "project_name": project_name,
                    "gate_name": gate_name,
                    "gate_type": _determine_gate_type(project_name, gate_name, sign_off, latest_change, conn),
                    "baseline_date": baseline["baseline_date"],
                    "sign_off_date": sign_off.get("sign_off_date") if sign_off else None,
                    "rework_due_date": sign_off.get("rework_due_date") if sign_off else None,
                    "days_delayed": int((latest_change or {}).get("days_delayed") or 0),
                    "has_risk_window": bool(
                        latest_change
                        and int(latest_change.get("days_delayed") or 0) > 14
                        and _parse_iso_date(latest_change.get("changed_at")) is not None
                        and (_parse_iso_date(latest_change.get("changed_at")) >= (date.today() - timedelta(days=60)))
                    ),
                    "calendar_year": display_date.year,
                    "calendar_quarter": _calendar_quarter(display_date),
                    "calendar_day_fraction": _day_fraction_in_quarter(display_date, 1),
                    "fiscal_year": _get_fiscal_year(display_date, aggregate_config.FISCAL_YEAR_START_MONTH),
                    "fiscal_quarter": _get_quarter(display_date.month, aggregate_config.FISCAL_YEAR_START_MONTH),
                    "fiscal_day_fraction": _day_fraction_in_quarter(
                        display_date,
                        aggregate_config.FISCAL_YEAR_START_MONTH,
                    ),
                    "display_date": display_date.isoformat(),
                }
            )

    conn.close()
    return timeline_rows


def get_programme_rag(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    _, project_names, _ = _resolve_programme_context(programme_id, conn)

    results: list[dict[str, Any]] = []
    for project_name in project_names:
        task_rows = conn.execute(
            """
            SELECT t.*
            FROM src.tasks t
            JOIN src.projects p ON p.id = t.project_id
            WHERE p.name = ?
            ORDER BY t.row_order, t.id
            """,
            (project_name,),
        ).fetchall()

        non_tailed = [dict(row) for row in task_rows if int(row["tailed_out"] or 0) == 0]
        total_tasks = len(non_tailed)
        completed = sum(1 for task in non_tailed if task.get("status") == "Completed")
        in_process = sum(1 for task in non_tailed if task.get("status") == "In Process")
        planned = sum(1 for task in non_tailed if task.get("status") == "Planned")
        critical_count = sum(1 for task in non_tailed if int(task.get("critical") or 0) == 1)
        milestone_count = sum(1 for task in non_tailed if int(task.get("milestone") or 0) == 1)
        tailed_out_count = sum(1 for task in task_rows if int(task["tailed_out"] or 0) == 1)

        start_dates = [_parse_iso_date(task.get("start_date")) for task in non_tailed]
        end_dates = [_parse_iso_date(task.get("end_date")) for task in non_tailed]
        valid_starts = [item for item in start_dates if item is not None]
        valid_ends = [item for item in end_dates if item is not None]

        completion_pct = _safe_pct(completed, total_tasks)
        schedule_elapsed_pct = _schedule_elapsed_pct(
            min(valid_starts) if valid_starts else None,
            max(valid_ends) if valid_ends else None,
        )
        schedule_variance = round(completion_pct - schedule_elapsed_pct, 2)
        overdue_count = sum(
            1
            for task in non_tailed
            if task.get("status") != "Completed"
            and (_parse_iso_date(task.get("end_date")) or date.max) < date.today()
        )

        latest_changes = _latest_gate_changes(conn, project_name)
        delayed_override = any(
            int(change.get("days_delayed") or 0) > 0
            and conn.execute(
                """
                SELECT 1
                FROM src.gate_sign_offs
                WHERE project_name = ? AND gate_name = ?
                LIMIT 1
                """,
                (project_name, gate_name),
            ).fetchone()
            is None
            for gate_name, change in latest_changes.items()
        )

        rework_override = bool(
            conn.execute(
                """
                SELECT 1
                FROM src.gate_sign_offs
                WHERE project_name = ?
                  AND status = 'Passed with Rework'
                  AND COALESCE(rework_sign_off_date, '') = ''
                LIMIT 1
                """,
                (project_name,),
            ).fetchone()
        ) and _open_rework_task_count(project_name, conn) > 0

        rag = "G"
        if delayed_override:
            rag = "R"
        elif rework_override:
            rag = "A"
        elif schedule_variance < -10:
            rag = "R"
        elif -10 <= schedule_variance <= 5:
            rag = "A"

        results.append(
            {
                "project_name": project_name,
                "rag": rag,
                "schedule_variance": schedule_variance,
                "completion_pct": completion_pct,
                "total_tasks": total_tasks,
                "completed": completed,
                "in_process": in_process,
                "planned": planned,
                "critical_count": critical_count,
                "overdue_count": overdue_count,
                "tailed_out_count": tailed_out_count,
                "milestone_count": milestone_count,
            }
        )

    conn.close()
    return results


def get_programme_summary(programme_id: int) -> dict[str, Any]:
    conn = get_connection()
    programme, project_names, bootstrap_mode = _resolve_programme_context(programme_id, conn)

    rag_rows = get_programme_rag(programme_id)
    timeline_rows = get_programme_timeline(programme_id)
    if bootstrap_mode:
        open_escalations = {"count": 0}
    else:
        open_escalations = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM programme_escalations
            WHERE programme_id = ? AND resolved = 0
            """,
            (programme_id,),
        ).fetchone()

    next_gate = None
    upcoming = sorted(
        [row for row in timeline_rows if _parse_iso_date(row["display_date"]) and _parse_iso_date(row["display_date"]) >= date.today()],
        key=lambda row: row["display_date"],
    )
    if upcoming:
        next_gate = upcoming[0]

    green = sum(1 for row in rag_rows if row["rag"] == "G")
    amber = sum(1 for row in rag_rows if row["rag"] == "A")
    red = sum(1 for row in rag_rows if row["rag"] == "R")
    project_count = len(rag_rows)
    health_score = _safe_pct(green, project_count)

    resource_risk_count = _resource_risk_count_for_projects(conn, project_names)

    summary = {
        "programme": programme,
        "project_count": project_count,
        "green_count": green,
        "amber_count": amber,
        "red_count": red,
        "health_score": health_score,
        "next_gate": next_gate,
        "open_escalations": int(open_escalations["count"]) if open_escalations else 0,
        "resource_risk_count": resource_risk_count,
    }
    conn.close()
    return summary


def get_portfolio_overview(division: str | None = None) -> list[dict[str, Any]]:
    programmes = list_programmes(division)
    overview_rows: list[dict[str, Any]] = []

    for programme in programmes:
        programme_id = programme["id"]
        summary = get_programme_summary(programme_id)
        timeline = sorted(
            get_programme_timeline(programme_id),
            key=lambda row: (row["display_date"], row["project_name"], row["gate_name"]),
        )

        overview_rows.append(
            {
                "programme": programme,
                "summary": summary,
                "timeline": timeline,
            }
        )

    return overview_rows


def get_programme_gates(programme_id: int) -> list[dict[str, Any]]:
    return get_programme_timeline(programme_id)


def get_programme_milestones(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    _, project_names, _ = _resolve_programme_context(programme_id, conn)
    if not project_names:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in project_names)
    rows = conn.execute(
        f"""
        SELECT
            p.name AS project_name,
            t.name AS task_name,
            mb.baseline_date,
            COALESCE(t.end_date, t.start_date) AS forecast_date,
            t.status
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        LEFT JOIN milestone_baselines mb
            ON mb.project_name = p.name
           AND mb.task_name = t.name
        WHERE p.name IN ({placeholders})
          AND t.milestone = 1
        ORDER BY p.name, COALESCE(t.end_date, t.start_date), t.name
        """,
        project_names,
    ).fetchall()
    conn.close()

    milestones: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        baseline = _parse_iso_date(row_dict.get("baseline_date"))
        forecast = _parse_iso_date(row_dict.get("forecast_date"))
        drift_days = None
        rag = "A"
        if baseline and forecast:
            drift_days = (forecast - baseline).days
            if drift_days <= 0:
                rag = "G"
            elif drift_days <= 14:
                rag = "A"
            else:
                rag = "R"

        milestones.append(
            {
                "project_name": row_dict["project_name"],
                "task_name": row_dict["task_name"],
                "baseline_date": row_dict.get("baseline_date"),
                "forecast_date": row_dict.get("forecast_date"),
                "drift_days": drift_days,
                "rag": rag,
                "status": row_dict.get("status"),
            }
        )

    return milestones


def _week_start(seed_date: date) -> date:
    return seed_date - timedelta(days=seed_date.weekday())


def get_programme_resources(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    programme, project_names, _ = _resolve_programme_context(programme_id, conn)
    if not project_names:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in project_names)
    teams = conn.execute(
        f"""
        SELECT DISTINCT
            rt.team_name,
            rt.capacity_hrs_per_week
        FROM resource_teams rt
        JOIN src.tasks t ON t.owner = rt.owner_name
        JOIN src.projects p ON p.id = t.project_id
        WHERE p.name IN ({placeholders})
        ORDER BY rt.team_name
        """,
        project_names,
    ).fetchall()

    base_week = _week_start(date.today())
    results: list[dict[str, Any]] = []
    for team in teams:
        weeks = []
        for offset in range(8):
            week_start = base_week + timedelta(days=offset * 7)
            week_end = week_start + timedelta(days=6)
            active_task_count_row = conn.execute(
                f"""
                SELECT COUNT(t.id) AS count
                FROM src.tasks t
                JOIN src.projects p ON p.id = t.project_id
                JOIN resource_teams rt ON rt.owner_name = t.owner
                WHERE p.name IN ({placeholders})
                  AND rt.team_name = ?
                  AND t.status IN ('Planned', 'In Process')
                  AND t.tailed_out = 0
                  AND COALESCE(t.start_date, '') <= ?
                  AND COALESCE(t.end_date, '') >= ?
                """,
                [*project_names, team["team_name"], week_end.isoformat(), week_start.isoformat()],
            ).fetchone()
            active_task_count = int(active_task_count_row["count"]) if active_task_count_row else 0
            util_pct = round(active_task_count / (float(team["capacity_hrs_per_week"]) / 37.5) * 100) if team["capacity_hrs_per_week"] else 0
            if util_pct < 80:
                level = "low"
            elif util_pct <= 100:
                level = "mid"
            else:
                level = "high"

            weeks.append(
                {
                    "week_start": week_start.isoformat(),
                    "util_pct": util_pct,
                    "level": level,
                    "active_task_count": active_task_count,
                }
            )

        results.append(
            {
                "team_name": team["team_name"],
                "division": programme.get("division", ""),
                "weeks": weeks,
            }
        )

    conn.close()
    return results


def get_programme_dependencies(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    _, project_names, _ = _resolve_programme_context(programme_id, conn)
    if len(project_names) < 2:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in project_names)
    rows = conn.execute(
        f"""
        SELECT
            td.id,
            pred_project.name AS predecessor_project_name,
            pred_task.name AS predecessor_task_name,
            pred_task.end_date AS predecessor_end_date,
            succ_project.name AS successor_project_name,
            succ_task.name AS successor_task_name,
            succ_task.start_date AS successor_start_date,
            succ_task.status AS successor_status
        FROM src.task_dependencies td
        JOIN src.tasks pred_task ON pred_task.id = td.predecessor_id
        JOIN src.tasks succ_task ON succ_task.id = td.successor_id
        JOIN src.projects pred_project ON pred_project.id = pred_task.project_id
        JOIN src.projects succ_project ON succ_project.id = succ_task.project_id
        WHERE pred_project.name IN ({placeholders})
          AND succ_project.name IN ({placeholders})
          AND pred_project.name <> succ_project.name
        ORDER BY succ_project.name, succ_task.name, pred_project.name
        """,
        [*project_names, *project_names],
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def list_programme_escalations(programme_id: int, include_resolved: bool = False) -> list[dict[str, Any]]:
    conn = get_connection()
    _, _, bootstrap_mode = _resolve_programme_context(programme_id, conn)
    if bootstrap_mode:
        conn.close()
        return []

    query = """
        SELECT *
        FROM programme_escalations
        WHERE programme_id = ?
    """
    params: list[Any] = [programme_id]
    if not include_resolved:
        query += " AND resolved = 0"
    query += " ORDER BY target_decision_date, created_at DESC, id DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {
            **dict(row),
            "resolved": bool(row["resolved"]),
        }
        for row in rows
    ]


def create_programme_escalation(
    programme_id: int,
    issue: str,
    owner: str,
    severity: str,
    raised_date: str,
    target_decision_date: str,
    project_name: str | None = None,
    gate_name: str | None = None,
) -> dict[str, Any]:
    conn = get_connection()
    _, _, bootstrap_mode = _resolve_programme_context(programme_id, conn)
    if bootstrap_mode:
        conn.close()
        raise ValueError("Create a real programme mapping before adding escalations")

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO programme_escalations (
            programme_id,
            project_name,
            gate_name,
            issue,
            owner,
            severity,
            raised_date,
            target_decision_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            programme_id,
            project_name or None,
            gate_name or None,
            issue.strip(),
            owner.strip(),
            severity.strip(),
            raised_date,
            target_decision_date,
        ),
    )
    escalation_id = cursor.lastrowid
    conn.commit()
    row = conn.execute(
        "SELECT * FROM programme_escalations WHERE id = ?",
        (escalation_id,),
    ).fetchone()
    conn.close()
    return {**dict(row), "resolved": bool(row["resolved"])}


def update_programme_escalation(
    escalation_id: int,
    resolved: bool | None = None,
    issue: str | None = None,
    owner: str | None = None,
    severity: str | None = None,
    target_decision_date: str | None = None,
) -> dict[str, Any]:
    conn = get_connection()
    existing = conn.execute(
        "SELECT * FROM programme_escalations WHERE id = ?",
        (escalation_id,),
    ).fetchone()
    if existing is None:
        conn.close()
        raise ValueError(f"Unknown escalation id: {escalation_id}")

    current = dict(existing)
    conn.execute(
        """
        UPDATE programme_escalations
        SET issue = ?,
            owner = ?,
            severity = ?,
            target_decision_date = ?,
            resolved = ?
        WHERE id = ?
        """,
        (
            issue.strip() if issue is not None else current["issue"],
            owner.strip() if owner is not None else current["owner"],
            severity.strip() if severity is not None else current["severity"],
            target_decision_date or current["target_decision_date"],
            1 if resolved else 0 if resolved is not None else current["resolved"],
            escalation_id,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM programme_escalations WHERE id = ?",
        (escalation_id,),
    ).fetchone()
    conn.close()
    return {**dict(row), "resolved": bool(row["resolved"])}


def get_programme_tailed_out(programme_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    _, project_names, _ = _resolve_programme_context(programme_id, conn)
    if not project_names:
        conn.close()
        return []

    placeholders = ",".join("?" for _ in project_names)
    rows = conn.execute(
        f"""
        SELECT
            p.name AS project_name,
            t.id AS task_id,
            t.name AS task_name,
            t.phase,
            t.owner,
            t.start_date,
            t.end_date,
            t.status,
            t.is_rework_cause,
            t.rework_original_due
        FROM src.tasks t
        JOIN src.projects p ON p.id = t.project_id
        WHERE p.name IN ({placeholders})
          AND t.tailed_out = 1
        ORDER BY p.name, t.phase, t.name
        """,
        project_names,
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)
