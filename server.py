"""
Dashboard Generator Web Server — Blueprint version for unified server
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename
from database_manager import DatabaseManager
from excel_parser import ExcelParser
import config
import sqlite3

dashboard_pages = Blueprint('dashboard_pages', __name__)
dashboard_api   = Blueprint('dashboard_api',   __name__)

# Initialize database manager (initialize_database() called from register_dashboard)
db_manager = DatabaseManager(config.DATABASE_PATH)


def allowed_file(filename):
    """Check if uploaded file has .xlsx extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'xlsx'


@dashboard_pages.route('/')
def index():
    """Home page - list all available projects"""
    projects = db_manager.get_all_projects()
    return render_template('dashboard/index.html', projects=projects)


@dashboard_pages.route('/project/<project_name>')
def view_project(project_name):
    """View a specific project dashboard"""
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return f"Project '{project_name}' not found", 404

    return render_template('dashboard/dashboard.html',
                         project_name=project_name,
                         project_manager=project['manager'],
                         PROJECT_NAME=project_name,
                         PROJECT_MANAGER=project['manager'],
                         GENERATED_DATE=datetime.now().strftime('%Y-%m-%d %H:%M'))


@dashboard_pages.route('/project/<project_name>/schematic')
def view_project_schematic(project_name):
    """View a standalone schematic schedule for a project"""
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return f"Project '{project_name}' not found", 404

    return render_template(
        'dashboard/project_schematic.html',
        project_name=project_name,
        project_manager=project['manager'],
        PROJECT_NAME=project_name,
        PROJECT_MANAGER=project['manager'],
        GENERATED_DATE=datetime.now().strftime('%Y-%m-%d %H:%M')
    )


@dashboard_pages.route('/disciplines')
def disciplines_page():
    return render_template('dashboard/disciplines.html')


@dashboard_api.route('/api/projects')
def api_get_projects():
    """API endpoint to get all projects"""
    projects = db_manager.get_all_projects()
    return jsonify(projects)


@dashboard_api.route('/api/overall-gate-timeline')
def api_get_overall_gate_timeline():
    """API endpoint to get unified gate timeline across all projects"""
    timeline = db_manager.get_overall_gate_timeline()
    return jsonify(timeline)


@dashboard_api.route('/api/overall-resource-load')
def api_get_overall_resource_load():
    """API endpoint to get unified owner workload across all projects"""
    resource_load = db_manager.get_overall_resource_load()
    return jsonify(resource_load)


@dashboard_api.route('/api/overall-critical-path-overview')
def api_get_overall_critical_path_overview():
    """API endpoint to get unified critical path overview across all projects"""
    critical_overview = db_manager.get_overall_critical_path_overview()
    return jsonify(critical_overview)


@dashboard_api.route('/api/project/<project_name>')
def api_get_project(project_name):
    """API endpoint to get project details"""
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    return jsonify(project)


@dashboard_api.route('/api/task/<int:task_id>', methods=['GET'])
def api_get_task(task_id):
    """API endpoint to get a specific task"""
    task = db_manager.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(task)


@dashboard_api.route('/api/upload-excel', methods=['POST'])
def api_upload_excel():
    """API endpoint to upload and import Excel file"""
    temp_file_path = None

    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        # Check if file was actually selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate file extension
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only .xlsx files are allowed'}), 400

        # Secure the filename
        filename = secure_filename(file.filename)

        # Create temporary file to store upload
        temp_fd, temp_file_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(temp_fd)

        # Save uploaded file to temporary location
        file.save(temp_file_path)

        # Initialize parser
        parser = ExcelParser()

        # Parse Excel file
        project_info, tasks = parser.parse_excel_file(temp_file_path)

        # Create or update project
        project_id = db_manager.create_or_update_project(
            name=project_info['name'],
            manager=project_info['manager'],
            excel_filename=filename
        )

        # Delete existing tasks for this project
        deleted_count = db_manager.delete_tasks_by_project(project_id)
        if deleted_count > 0:
            print(f"  ✓ Removed {deleted_count} old tasks")

        # Import all tasks
        imported_count = 0
        for task in tasks:
            task['project_id'] = project_id
            task_id = db_manager.create_task(task)
            if task_id:
                imported_count += 1

        print(f"  ✓ Imported {imported_count} tasks for project '{project_info['name']}'")

        # Auto-detect dependencies by date matching (Finish-to-Start, delta <= 2 days)
        from datetime import datetime, timedelta
        db_manager.delete_dependencies_by_project(project_info['name'])
        dep_count = 0
        all_tasks_for_project = db_manager.get_tasks_by_project(project_info['name'])
        DEP_DELTA_DAYS = 2
        task_end_dates = {}
        for t in all_tasks_for_project:
            ed = t.get('end_date', '')
            if ed:
                try:
                    task_end_dates[t['id']] = datetime.strptime(ed, '%Y-%m-%d')
                except ValueError:
                    pass
        for successor in all_tasks_for_project:
            sd = successor.get('start_date', '')
            if not sd:
                continue
            try:
                start_dt = datetime.strptime(sd, '%Y-%m-%d')
            except ValueError:
                continue
            for predecessor in all_tasks_for_project:
                if predecessor['id'] == successor['id']:
                    continue
                pred_end_dt = task_end_dates.get(predecessor['id'])
                if pred_end_dt is None:
                    continue
                delta = (start_dt - pred_end_dt).days
                if 0 <= delta <= DEP_DELTA_DAYS:
                    db_manager.create_dependency(project_info['name'], predecessor['id'], successor['id'])
                    dep_count += 1
        print(f"  ✓ Detected {dep_count} task dependencies (Finish-to-Start, delta <= {DEP_DELTA_DAYS} days)")

        return jsonify({
            'success': True,
            'message': f'Successfully imported {filename}',
            'project_name': project_info['name'],
            'tasks_imported': imported_count,
            'dependencies_detected': dep_count,
            'filename': filename
        }), 200

    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_file_path}: {e}")


@dashboard_api.route('/api/project/<project_name>/export')
def api_export_to_excel(project_name):
    """API endpoint to export project to Excel"""
    from excel_exporter import ExcelExporter

    project = db_manager.get_project_by_name(project_name)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    tasks = db_manager.get_tasks_by_project(project_name)

    exporter = ExcelExporter()
    excel_path = exporter.export_project(project, tasks, config.EXCEL_OUTPUT_FOLDER)

    if excel_path and os.path.exists(excel_path):
        return send_file(
            excel_path,
            as_attachment=True,
            download_name=os.path.basename(excel_path),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        return jsonify({'error': 'Failed to export to Excel'}), 500


@dashboard_api.route('/api/project/<project_name>/export-ppt')
def api_export_schematic_to_ppt(project_name):
    """API endpoint to export project schematic to PowerPoint"""
    from ppt_exporter import PptExporter

    project = db_manager.get_project_by_name(project_name)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    tasks = db_manager.get_tasks_by_project(project_name)
    gate_sign_offs = db_manager.get_gate_sign_offs(project_name)

    exporter = PptExporter()
    ppt_path = exporter.export_schematic(project, tasks, gate_sign_offs, config.EXCEL_OUTPUT_FOLDER)

    if ppt_path and os.path.exists(ppt_path):
        return send_file(
            ppt_path,
            as_attachment=True,
            download_name=os.path.basename(ppt_path),
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )

    return jsonify({'error': 'Failed to export schematic to PowerPoint'}), 500


@dashboard_api.route('/api/stats')
def api_get_stats():
    """API endpoint to get server statistics"""
    resource_load = db_manager.get_overall_resource_load()
    stats = {
        'total_projects': len(db_manager.get_all_projects()),
        'total_tasks': db_manager.get_total_task_count(),
        'total_owners': resource_load['summary']['owner_count'],
        'last_scan': 'N/A'
    }
    return jsonify(stats)


@dashboard_api.route('/api/v1/admin/resource-teams', methods=['GET'])
def api_resource_teams_get():
    try:
        conn = db_manager.get_connection()
        rows = conn.execute(
            "SELECT id, team_name, owner_name, capacity_hrs_per_week FROM resource_teams ORDER BY owner_name"
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_api.route('/api/v1/admin/resource-teams/bulk', methods=['POST'])
def api_resource_teams_bulk():
    mappings = request.get_json(silent=True) or []
    if not isinstance(mappings, list):
        return jsonify({'error': 'Expected a JSON array of {owner_name, team_name}'}), 400
    try:
        conn = db_manager.get_connection()
        conn.execute("DELETE FROM resource_teams")
        count = 0
        for m in mappings:
            owner = (m.get('owner_name') or '').strip()
            team = (m.get('team_name') or '').strip()
            if owner and team:
                conn.execute(
                    """INSERT INTO resource_teams (owner_name, team_name, capacity_hrs_per_week)
                       VALUES (?, ?, ?)
                       ON CONFLICT(owner_name) DO UPDATE SET
                           team_name = excluded.team_name""",
                    (owner, team, m.get('capacity_hrs_per_week') or 37.5),
                )
                count += 1
        conn.commit()
        conn.close()
        return jsonify({'saved': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_api.route('/api/discipline-resource-load')
def api_discipline_resource_load():
    import calendar
    from datetime import date as _date
    today = _date.today()

    months = []
    for i in range(-1, 12):
        raw_month = today.month - 1 + i
        y = today.year + raw_month // 12
        m = raw_month % 12 + 1
        months.append(_date(y, m, 1))

    p_conn = db_manager.get_connection()
    mappings = p_conn.execute("SELECT TRIM(owner_name), team_name FROM resource_teams").fetchall()
    p_conn.close()
    owner_to_disc = {row[0].lower(): row[1] for row in mappings}

    disc_owners = {}
    for owner_lower, disc in owner_to_disc.items():
        disc_owners[disc] = disc_owners.get(disc, 0) + 1

    db_path = config.DATABASE_PATH
    t_conn = sqlite3.connect(str(db_path))
    tasks = t_conn.execute("""
        SELECT TRIM(owner), start_date, end_date, status
        FROM tasks
        WHERE status IN ('In Process','Planned')
          AND start_date IS NOT NULL AND start_date != ''
          AND end_date   IS NOT NULL AND end_date   != ''
    """).fetchall()
    t_conn.close()

    disc_monthly = {}
    for owner_raw, start_str, end_str, status in tasks:
        disc = owner_to_disc.get((owner_raw or '').lower())
        if not disc:
            continue
        try:
            start = _date.fromisoformat(start_str[:10])
            end   = _date.fromisoformat(end_str[:10])
        except Exception:
            continue
        if disc not in disc_monthly:
            disc_monthly[disc] = {'In Process': [0]*len(months), 'Planned': [0]*len(months)}
        bucket = 'In Process' if status == 'In Process' else 'Planned'
        for i, ms in enumerate(months):
            last_day = calendar.monthrange(ms.year, ms.month)[1]
            me = _date(ms.year, ms.month, last_day)
            if start <= me and end >= ms:
                disc_monthly[disc][bucket][i] += 1

    PM_LOAD_PER_PROJECT = 5
    pm_conn = sqlite3.connect(str(db_path))
    pm_conn.row_factory = sqlite3.Row
    pm_proj_rows = pm_conn.execute("""
        SELECT TRIM(p.manager) AS manager,
               MIN(CASE WHEN t.status IN ('In Process','Planned') THEN t.start_date ELSE NULL END) AS proj_start,
               MAX(CASE WHEN t.status IN ('In Process','Planned') THEN t.end_date   ELSE NULL END) AS proj_end,
               SUM(CASE WHEN t.status IN ('In Process','Planned') THEN 1 ELSE 0 END) AS active_tasks
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        WHERE TRIM(COALESCE(p.manager,'')) != ''
        GROUP BY p.id, p.name, p.manager
        HAVING active_tasks > 0
    """).fetchall()
    pm_conn.close()

    for pr in pm_proj_rows:
        manager   = (pr['manager'] or '').strip()
        pstart_s  = pr['proj_start']
        pend_s    = pr['proj_end']
        if not manager or not pstart_s or not pend_s:
            continue
        disc = owner_to_disc.get(manager.lower())
        if not disc:
            disc = owner_to_disc.get(manager.split()[0].lower())
        if not disc:
            continue
        try:
            pstart = _date.fromisoformat(pstart_s[:10])
            pend   = _date.fromisoformat(pend_s[:10])
        except Exception:
            continue
        if disc not in disc_monthly:
            disc_monthly[disc] = {'In Process': [0]*len(months), 'Planned': [0]*len(months)}
        for i, ms in enumerate(months):
            last_day = calendar.monthrange(ms.year, ms.month)[1]
            me = _date(ms.year, ms.month, last_day)
            if pstart <= me and pend >= ms:
                bucket = 'In Process' if ms <= today else 'Planned'
                disc_monthly[disc][bucket][i] += PM_LOAD_PER_PROJECT

    result = []
    for disc in sorted(disc_monthly):
        ip = disc_monthly[disc]['In Process']
        pl = disc_monthly[disc]['Planned']
        combined = [ip[i] + pl[i] for i in range(len(months))]
        peak = max(combined) if combined else 0
        peak_idx = combined.index(peak) if peak else 0
        owner_count = disc_owners.get(disc, 1)
        result.append({
            'name': disc,
            'owner_count': owner_count,
            'in_process': ip,
            'planned': pl,
            'combined': combined,
            'peak_count': peak,
            'peak_month': months[peak_idx].strftime('%Y-%m'),
        })

    result.sort(key=lambda x: x['peak_count'], reverse=True)
    return jsonify({
        'months': [m.strftime('%Y-%m') for m in months],
        'month_labels': [m.strftime("%b '%y") for m in months],
        'today_month': today.strftime('%Y-%m'),
        'disciplines': result,
    })


@dashboard_api.route('/api/project/<project_name>/dependencies/by-tasks', methods=['DELETE'])
def api_delete_dependency_by_tasks(project_name):
    """Delete a dependency between two specific tasks"""
    try:
        data = request.json
        success = db_manager.delete_dependency_by_tasks(data['predecessor_id'], data['successor_id'])
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dashboard_api.route('/api/project/<project_name>', methods=['DELETE'])
def api_delete_project(project_name):
    """Delete a project and all its data"""
    try:
        success = db_manager.delete_project(project_name)
        if success:
            return jsonify({'success': True, 'message': f'Project "{project_name}" deleted'})
        else:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def register_dashboard(app):
    db_manager.initialize_database()
    app.register_blueprint(dashboard_pages, url_prefix='/dashboard')
    app.register_blueprint(dashboard_api)   # no prefix — API routes stay at /api/...
