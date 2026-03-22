"""
Flask application for the aggregate portfolio dashboard.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.utils import secure_filename

import aggregate_config
import config
from aggregate_db import initialize_portfolio_database
from aggregate_repository import (
    assign_project_to_programme,
    create_programme,
    create_programme_escalation,
    create_resource_team,
    get_programme_dependencies,
    get_programme_gates,
    get_programme_milestones,
    get_programme_rag,
    get_programme_resources,
    get_programme_summary,
    get_programme_tailed_out,
    get_programme_timeline,
    get_portfolio_overview,
    list_milestone_candidates,
    list_milestone_baselines,
    list_programme_escalations,
    list_programme_projects,
    list_programmes,
    list_resource_teams,
    list_unassigned_projects,
    list_unmapped_owners,
    update_programme_escalation,
    upsert_milestone_baseline,
)
from database_manager import DatabaseManager
from excel_parser import ExcelParser


PROJECT_ROOT = Path(__file__).resolve().parent


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "xlsx"


def _json_error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


def _require_fields(payload, *required_fields):
    for field in required_fields:
        if field not in payload or payload[field] in (None, ""):
            raise ValueError(f"Missing required field: {field}")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="aggregate_templates",
        static_folder="aggregate_static",
    )
    app.config["JSON_SORT_KEYS"] = False
    app.config["SECRET_KEY"] = "dashboard-generator-secret-key"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.jinja_loader = ChoiceLoader(
        [
            FileSystemLoader(str(PROJECT_ROOT / "aggregate_templates")),
            FileSystemLoader(str(PROJECT_ROOT / "templates")),
        ]
    )

    initialize_portfolio_database()
    db_manager = DatabaseManager(config.DATABASE_PATH)
    db_manager.initialize_database()

    @app.route("/")
    def index():
        return render_template("aggregate_index.html")

    @app.route("/projects")
    def detailed_projects_index():
        projects = db_manager.get_all_projects()
        return render_template("index.html", projects=projects)

    @app.route("/project/<project_name>")
    def detailed_project_dashboard(project_name: str):
        project = db_manager.get_project_by_name(project_name)
        if not project:
            return f"Project '{project_name}' not found", 404

        return render_template(
            "dashboard.html",
            project_name=project_name,
            project_manager=project["manager"],
            PROJECT_NAME=project_name,
            PROJECT_MANAGER=project["manager"],
            GENERATED_DATE=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "app": "programme-portfolio-aggregation-dashboard",
                "port": aggregate_config.AGGREGATE_PORT,
            }
        )

    @app.route("/api/projects", methods=["GET", "POST"])
    def api_get_projects():
        if request.method == "GET":
            return jsonify(db_manager.get_all_projects())

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "name", "manager")
            existing_project = db_manager.get_project_by_name(data["name"])
            if existing_project:
                return _json_error("Project already exists", 400)

            project_id = db_manager.create_or_update_project(
                name=data["name"].strip(),
                manager=data["manager"].strip(),
                excel_filename=data.get("excel_filename", "").strip(),
            )
            project = db_manager.get_project_by_id(project_id)
            if not project:
                return _json_error("Failed to create project", 500)
            return jsonify(project), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)

    @app.route("/api/project/<project_name>")
    def api_get_project(project_name: str):
        project = db_manager.get_project_by_name(project_name)
        if not project:
            return _json_error("Project not found", 404)
        return jsonify(project)

    @app.route("/api/project/<project_name>/tasks")
    def api_get_tasks(project_name: str):
        return jsonify(db_manager.get_tasks_by_project(project_name))

    @app.route("/api/task/<int:task_id>", methods=["GET"])
    def api_get_task(task_id: int):
        task = db_manager.get_task_by_id(task_id)
        if not task:
            return _json_error("Task not found", 404)
        return jsonify(task)

    @app.route("/api/task/<int:task_id>", methods=["PUT"])
    def api_update_task(task_id: int):
        data = request.get_json(silent=True) or {}
        if not data:
            return _json_error("No data provided", 400)

        success = db_manager.update_task(task_id, data)
        if not success:
            return _json_error("Failed to update task", 500)

        return jsonify(
            {
                "message": "Task updated successfully",
                "task": db_manager.get_task_by_id(task_id),
            }
        )

    @app.route("/api/project/<project_name>/task", methods=["POST"])
    def api_create_task(project_name: str):
        data = request.get_json(silent=True) or {}
        for field in ("name", "phase", "owner", "start_date", "end_date", "status"):
            if field not in data:
                return _json_error(f"Missing required field: {field}", 400)

        project = db_manager.get_project_by_name(project_name)
        if not project:
            return _json_error("Project not found", 404)

        data["project_id"] = project["id"]
        task_id = db_manager.create_task(data)
        if not task_id:
            return _json_error("Failed to create task", 500)

        return (
            jsonify(
                {
                    "message": "Task created successfully",
                    "task": db_manager.get_task_by_id(task_id),
                }
            ),
            201,
        )

    @app.route("/api/task/<int:task_id>", methods=["DELETE"])
    def api_delete_task(task_id: int):
        success = db_manager.delete_task(task_id)
        if not success:
            return _json_error("Failed to delete task", 500)
        return jsonify({"message": "Task deleted successfully"})

    @app.route("/api/upload-excel", methods=["POST"])
    def api_upload_excel():
        temp_file_path = None
        try:
            if "file" not in request.files:
                return _json_error("No file provided", 400)

            file = request.files["file"]
            if file.filename == "":
                return _json_error("No file selected", 400)

            if not _allowed_file(file.filename):
                return _json_error("Only .xlsx files are allowed", 400)

            filename = secure_filename(file.filename)
            temp_fd, temp_file_path = tempfile.mkstemp(suffix=".xlsx")
            os.close(temp_fd)
            file.save(temp_file_path)

            parser = ExcelParser()
            project_info, tasks = parser.parse_excel_file(temp_file_path)

            project_id = db_manager.create_or_update_project(
                name=project_info["name"],
                manager=project_info["manager"],
                excel_filename=filename,
            )

            db_manager.delete_tasks_by_project(project_id)

            imported_count = 0
            for task in tasks:
                task["project_id"] = project_id
                if db_manager.create_task(task):
                    imported_count += 1

            from datetime import datetime as dt

            db_manager.delete_dependencies_by_project(project_info["name"])
            dep_count = 0
            all_tasks_for_project = db_manager.get_tasks_by_project(project_info["name"])
            dep_delta_days = 2
            task_end_dates = {}
            for task in all_tasks_for_project:
                end_date = task.get("end_date", "")
                if not end_date:
                    continue
                try:
                    task_end_dates[task["id"]] = dt.strptime(end_date, "%Y-%m-%d")
                except ValueError:
                    continue

            for successor in all_tasks_for_project:
                start_date = successor.get("start_date", "")
                if not start_date:
                    continue
                try:
                    start_dt = dt.strptime(start_date, "%Y-%m-%d")
                except ValueError:
                    continue

                for predecessor in all_tasks_for_project:
                    if predecessor["id"] == successor["id"]:
                        continue
                    predecessor_end_dt = task_end_dates.get(predecessor["id"])
                    if predecessor_end_dt is None:
                        continue
                    delta = (start_dt - predecessor_end_dt).days
                    if 0 <= delta <= dep_delta_days:
                        db_manager.create_dependency(
                            project_info["name"],
                            predecessor["id"],
                            successor["id"],
                        )
                        dep_count += 1

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Successfully imported {filename}",
                        "project_name": project_info["name"],
                        "tasks_imported": imported_count,
                        "dependencies_detected": dep_count,
                        "filename": filename,
                    }
                ),
                200,
            )
        except Exception as exc:
            return _json_error(f"Error processing file: {exc}", 500)
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

    @app.route("/api/project/<project_name>/export")
    def api_export_to_excel(project_name: str):
        from excel_exporter import ExcelExporter

        project = db_manager.get_project_by_name(project_name)
        if not project:
            return _json_error("Project not found", 404)

        tasks = db_manager.get_tasks_by_project(project_name)
        exporter = ExcelExporter()
        excel_path = exporter.export_project(project, tasks, config.EXCEL_OUTPUT_FOLDER)
        if not excel_path or not os.path.exists(excel_path):
            return _json_error("Failed to export to Excel", 500)

        return send_file(
            excel_path,
            as_attachment=True,
            download_name=os.path.basename(excel_path),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.route("/api/stats")
    def api_get_stats():
        return jsonify(
            {
                "total_projects": len(db_manager.get_all_projects()),
                "total_tasks": db_manager.get_total_task_count(),
                "last_scan": "N/A",
            }
        )

    @app.route("/api/project/<project_name>/gate-baselines", methods=["GET"])
    def api_get_gate_baselines(project_name: str):
        try:
            return jsonify(db_manager.get_gate_baselines(project_name))
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/gate-baselines", methods=["POST"])
    def api_create_gate_baselines(project_name: str):
        try:
            data = request.get_json(silent=True) or {}
            baselines = data.get("baselines", [])
            for baseline in baselines:
                db_manager.create_gate_baseline(
                    project_name=project_name,
                    gate_name=baseline["gate_name"],
                    gate_id=baseline["gate_id"],
                    baseline_date=baseline["baseline_date"],
                )
            return jsonify({"success": True, "count": len(baselines)})
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/gate-change-log", methods=["GET"])
    def api_get_gate_change_log(project_name: str):
        try:
            return jsonify(db_manager.get_gate_change_log(project_name))
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/gate-change-log", methods=["POST"])
    def api_add_gate_change_log(project_name: str):
        try:
            log_data = request.get_json(silent=True) or {}
            log_data["project_name"] = project_name
            log_id = db_manager.add_gate_change_log(log_data)
            return jsonify({"success": True, "log_id": log_id})
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/gate-change-log/<gate_name>", methods=["DELETE"])
    def api_delete_gate_change_log(project_name: str, gate_name: str):
        try:
            deleted_count = db_manager.delete_gate_change_log_by_gate(project_name, gate_name)
            return jsonify({"success": True, "deleted_count": deleted_count})
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/dependencies", methods=["GET"])
    def api_get_dependencies(project_name: str):
        try:
            return jsonify(db_manager.get_dependencies_by_project(project_name))
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/dependencies", methods=["POST"])
    def api_create_dependency(project_name: str):
        try:
            data = request.get_json(silent=True) or {}
            predecessor_id = data.get("predecessor_id")
            successor_id = data.get("successor_id")
            if not predecessor_id or not successor_id:
                return _json_error("predecessor_id and successor_id required", 400)
            dep_id = db_manager.create_dependency(project_name, predecessor_id, successor_id)
            return jsonify({"success": True, "id": dep_id})
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/dependency/<int:dep_id>", methods=["DELETE"])
    def api_delete_dependency(dep_id: int):
        try:
            return jsonify({"success": db_manager.delete_dependency(dep_id)})
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/dependencies/by-tasks", methods=["DELETE"])
    def api_delete_dependency_by_tasks(project_name: str):
        try:
            data = request.get_json(silent=True) or {}
            return jsonify(
                {
                    "success": db_manager.delete_dependency_by_tasks(
                        data["predecessor_id"],
                        data["successor_id"],
                    )
                }
            )
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/project/<project_name>/gate-sign-offs", methods=["GET"])
    def api_get_gate_sign_offs(project_name: str):
        return jsonify(db_manager.get_gate_sign_offs(project_name))

    @app.route("/api/project/<project_name>/gate-sign-offs", methods=["POST"])
    def api_upsert_gate_sign_off(project_name: str):
        data = request.get_json(silent=True) or {}
        for field in ("gate_name", "gate_id", "sign_off_date", "status"):
            if field not in data:
                return _json_error(f"Missing required field: {field}", 400)
        if data["status"] == "Passed with Rework" and not data.get("rework_due_date"):
            return _json_error(
                "rework_due_date is required for Passed with Rework status",
                400,
            )

        success = db_manager.upsert_gate_sign_off(
            project_name=project_name,
            gate_name=data["gate_name"],
            gate_id=data["gate_id"],
            sign_off_date=data["sign_off_date"],
            status=data["status"],
            rework_due_date=data.get("rework_due_date"),
            rework_sign_off_date=data.get("rework_sign_off_date"),
        )
        return jsonify({"success": success})

    @app.route("/api/project/<project_name>/gate-sign-off/<gate_name>", methods=["DELETE"])
    def api_delete_gate_sign_off(project_name: str, gate_name: str):
        return jsonify({"success": db_manager.delete_gate_sign_off(project_name, gate_name)})

    @app.route("/api/v1/programmes", methods=["GET"])
    def api_get_programmes():
        division = request.args.get("division")
        return jsonify(list_programmes(division))

    @app.route("/api/v1/admin/programmes", methods=["GET", "POST"])
    def api_admin_programmes():
        if request.method == "GET":
            return jsonify(list_programmes())

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "name", "division", "owner")
            programme = create_programme(
                name=data["name"],
                division=data["division"],
                owner=data["owner"],
                status=data.get("status", "active"),
            )
            return jsonify(programme), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/admin/unassigned-projects", methods=["GET"])
    def api_admin_unassigned_projects():
        return jsonify(list_unassigned_projects())

    @app.route("/api/v1/admin/unmapped-owners", methods=["GET"])
    def api_admin_unmapped_owners():
        return jsonify(list_unmapped_owners())

    @app.route("/api/v1/admin/programme/<int:programme_id>/projects", methods=["GET", "POST"])
    def api_admin_programme_projects(programme_id: int):
        if request.method == "GET":
            return jsonify(list_programme_projects(programme_id))

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "project_name")
            mapping = assign_project_to_programme(
                programme_id=programme_id,
                project_name=data["project_name"],
                display_order=int(data.get("display_order", 0)),
            )
            return jsonify(mapping), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/admin/resource-teams", methods=["GET", "POST"])
    def api_admin_resource_teams():
        if request.method == "GET":
            return jsonify(list_resource_teams())

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "team_name", "owner_name")
            team = create_resource_team(
                team_name=data["team_name"],
                owner_name=data["owner_name"],
                capacity_hrs_per_week=float(
                    data.get(
                        "capacity_hrs_per_week",
                        aggregate_config.DEFAULT_TEAM_CAPACITY_HOURS,
                    )
                ),
            )
            return jsonify(team), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/admin/milestone-baselines", methods=["GET", "POST"])
    def api_admin_milestone_baselines():
        if request.method == "GET":
            programme_id = request.args.get("programme_id", type=int)
            return jsonify(list_milestone_baselines(programme_id))

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "project_name", "task_name", "baseline_date")
            baseline = upsert_milestone_baseline(
                project_name=data["project_name"],
                task_name=data["task_name"],
                baseline_date=data["baseline_date"],
            )
            return jsonify(baseline), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/admin/milestone-candidates", methods=["GET"])
    def api_admin_milestone_candidates():
        programme_id = request.args.get("programme_id", type=int)
        return jsonify(list_milestone_candidates(programme_id))

    @app.route("/api/v1/programme/<int:programme_id>/summary", methods=["GET"])
    def api_programme_summary(programme_id: int):
        try:
            return jsonify(get_programme_summary(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/programme/<int:programme_id>/rag", methods=["GET"])
    def api_programme_rag(programme_id: int):
        return jsonify(get_programme_rag(programme_id))

    @app.route("/api/v1/programme/<int:programme_id>/timeline", methods=["GET"])
    def api_programme_timeline(programme_id: int):
        return jsonify(get_programme_timeline(programme_id))

    @app.route("/api/v1/programme/<int:programme_id>/gates", methods=["GET"])
    def api_programme_gates(programme_id: int):
        try:
            return jsonify(get_programme_gates(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/programme/<int:programme_id>/milestones", methods=["GET"])
    def api_programme_milestones(programme_id: int):
        try:
            return jsonify(get_programme_milestones(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/programme/<int:programme_id>/resources", methods=["GET"])
    def api_programme_resources(programme_id: int):
        try:
            return jsonify(get_programme_resources(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/programme/<int:programme_id>/dependencies", methods=["GET"])
    def api_programme_dependencies(programme_id: int):
        try:
            return jsonify(get_programme_dependencies(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/programme/<int:programme_id>/escalations", methods=["GET", "POST"])
    def api_programme_escalations(programme_id: int):
        if request.method == "GET":
            include_resolved = request.args.get("include_resolved", "").lower() in {"1", "true", "yes"}
            try:
                return jsonify(list_programme_escalations(programme_id, include_resolved=include_resolved))
            except ValueError as exc:
                return _json_error(str(exc), 404)

        data = request.get_json(silent=True) or {}
        try:
            _require_fields(data, "issue", "owner", "severity", "raised_date", "target_decision_date")
            escalation = create_programme_escalation(
                programme_id=programme_id,
                issue=data["issue"],
                owner=data["owner"],
                severity=data["severity"],
                raised_date=data["raised_date"],
                target_decision_date=data["target_decision_date"],
                project_name=data.get("project_name"),
                gate_name=data.get("gate_name"),
            )
            return jsonify(escalation), 201
        except ValueError as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/escalation/<int:escalation_id>", methods=["PUT"])
    def api_update_escalation(escalation_id: int):
        data = request.get_json(silent=True) or {}
        try:
            escalation = update_programme_escalation(
                escalation_id=escalation_id,
                resolved=data.get("resolved"),
                issue=data.get("issue"),
                owner=data.get("owner"),
                severity=data.get("severity"),
                target_decision_date=data.get("target_decision_date"),
            )
            return jsonify(escalation)
        except ValueError as exc:
            return _json_error(str(exc), 404)
        except Exception as exc:
            return _json_error(str(exc), 500)

    @app.route("/api/v1/programme/<int:programme_id>/tailed-out", methods=["GET"])
    def api_programme_tailed_out(programme_id: int):
        try:
            return jsonify(get_programme_tailed_out(programme_id))
        except ValueError as exc:
            return _json_error(str(exc), 404)

    @app.route("/api/v1/portfolio/overview", methods=["GET"])
    def api_portfolio_overview():
        division = request.args.get("division")
        return jsonify(get_portfolio_overview(division))

    return app
