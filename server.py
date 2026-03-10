"""
Dashboard Generator Web Server
Flask-based web server for managing project dashboards
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Ensure stdout/stderr use UTF-8 so Unicode characters (✓ ✗ etc.) don't crash on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename
from database_manager import DatabaseManager
from excel_parser import ExcelParser
import config

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dashboard-generator-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize database manager
db_manager = DatabaseManager(config.DATABASE_PATH)
db_manager.initialize_database()


def allowed_file(filename):
    """Check if uploaded file has .xlsx extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'xlsx'


@app.route('/')
def index():
    """Home page - list all available projects"""
    projects = db_manager.get_all_projects()
    return render_template('index.html', projects=projects)


@app.route('/project/<project_name>')
def view_project(project_name):
    """View a specific project dashboard"""
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return f"Project '{project_name}' not found", 404
    
    return render_template('dashboard.html', 
                         project_name=project_name,
                         project_manager=project['manager'],
                         PROJECT_NAME=project_name,
                         PROJECT_MANAGER=project['manager'],
                         GENERATED_DATE=datetime.now().strftime('%Y-%m-%d %H:%M'))


@app.route('/api/projects')
def api_get_projects():
    """API endpoint to get all projects"""
    projects = db_manager.get_all_projects()
    return jsonify(projects)


@app.route('/api/project/<project_name>')
def api_get_project(project_name):
    """API endpoint to get project details"""
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    return jsonify(project)


@app.route('/api/project/<project_name>/tasks')
def api_get_tasks(project_name):
    """API endpoint to get all tasks for a project"""
    tasks = db_manager.get_tasks_by_project(project_name)
    return jsonify(tasks)


@app.route('/api/task/<int:task_id>', methods=['GET'])
def api_get_task(task_id):
    """API endpoint to get a specific task"""
    task = db_manager.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(task)


@app.route('/api/task/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    """API endpoint to update a task"""
    data = request.json
    
    # Validate required fields
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    success = db_manager.update_task(task_id, data)
    
    if success:
        task = db_manager.get_task_by_id(task_id)
        return jsonify({'message': 'Task updated successfully', 'task': task})
    else:
        return jsonify({'error': 'Failed to update task'}), 500


@app.route('/api/project/<project_name>/task', methods=['POST'])
def api_create_task(project_name):
    """API endpoint to create a new task"""
    data = request.json
    
    # Validate required fields
    required_fields = ['name', 'phase', 'owner', 'start_date', 'end_date', 'status']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Get project ID
    project = db_manager.get_project_by_name(project_name)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    data['project_id'] = project['id']
    
    task_id = db_manager.create_task(data)
    
    if task_id:
        task = db_manager.get_task_by_id(task_id)
        return jsonify({'message': 'Task created successfully', 'task': task}), 201
    else:
        return jsonify({'error': 'Failed to create task'}), 500


@app.route('/api/task/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    """API endpoint to delete a task"""
    success = db_manager.delete_task(task_id)
    
    if success:
        return jsonify({'message': 'Task deleted successfully'})
    else:
        return jsonify({'error': 'Failed to delete task'}), 500


@app.route('/api/upload-excel', methods=['POST'])
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
        # If 0 <= task_B.start_date - task_A.end_date <= 2 days, they are dependent
        from datetime import datetime, timedelta
        db_manager.delete_dependencies_by_project(project_info['name'])
        dep_count = 0
        all_tasks_for_project = db_manager.get_tasks_by_project(project_info['name'])
        DEP_DELTA_DAYS = 2
        # Parse all end dates once for efficiency
        task_end_dates = {}
        for t in all_tasks_for_project:
            ed = t.get('end_date', '')
            if ed:
                try:
                    task_end_dates[t['id']] = datetime.strptime(ed, '%Y-%m-%d')
                except ValueError:
                    pass
        # For each task, find predecessors whose end_date is within DEP_DELTA_DAYS before this task's start_date
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
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_file_path}: {e}")


@app.route('/api/project/<project_name>/export')
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


@app.route('/api/stats')
def api_get_stats():
    """API endpoint to get server statistics"""
    stats = {
        'total_projects': len(db_manager.get_all_projects()),
        'total_tasks': db_manager.get_total_task_count(),
        'last_scan': 'N/A'
    }
    return jsonify(stats)


# Gate Baseline and Change Log Endpoints

@app.route('/api/project/<project_name>/gate-baselines', methods=['GET'])
def api_get_gate_baselines(project_name):
    """Get all Gate baselines for a project"""
    try:
        baselines = db_manager.get_gate_baselines(project_name)
        return jsonify(baselines)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/gate-baselines', methods=['POST'])
def api_create_gate_baselines(project_name):
    """Create/update Gate baselines for a project"""
    try:
        data = request.json
        baselines = data.get('baselines', [])
        
        for baseline in baselines:
            db_manager.create_gate_baseline(
                project_name=project_name,
                gate_name=baseline['gate_name'],
                gate_id=baseline['gate_id'],
                baseline_date=baseline['baseline_date']
            )
        
        return jsonify({'success': True, 'count': len(baselines)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/gate-change-log', methods=['GET'])
def api_get_gate_change_log(project_name):
    """Get all Gate change log entries for a project"""
    try:
        changes = db_manager.get_gate_change_log(project_name)
        return jsonify(changes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/gate-change-log', methods=['POST'])
def api_add_gate_change_log(project_name):
    """Add a Gate change log entry"""
    try:
        log_data = request.json
        log_data['project_name'] = project_name
        
        log_id = db_manager.add_gate_change_log(log_data)
        
        return jsonify({'success': True, 'log_id': log_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/gate-change-log/<gate_name>', methods=['DELETE'])
def api_delete_gate_change_log(project_name, gate_name):
    """Delete all change log entries for a specific Gate"""
    try:
        deleted_count = db_manager.delete_gate_change_log_by_gate(project_name, gate_name)
        
        return jsonify({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/dependencies', methods=['GET'])
def api_get_dependencies(project_name):
    """Get all task dependencies for a project"""
    try:
        deps = db_manager.get_dependencies_by_project(project_name)
        return jsonify(deps)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/dependencies', methods=['POST'])
def api_create_dependency(project_name):
    """Create a task dependency"""
    try:
        data = request.json
        predecessor_id = data.get('predecessor_id')
        successor_id = data.get('successor_id')
        if not predecessor_id or not successor_id:
            return jsonify({'error': 'predecessor_id and successor_id required'}), 400
        dep_id = db_manager.create_dependency(project_name, predecessor_id, successor_id)
        return jsonify({'success': True, 'id': dep_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/dependency/<int:dep_id>', methods=['DELETE'])
def api_delete_dependency(dep_id):
    """Delete a specific dependency"""
    try:
        success = db_manager.delete_dependency(dep_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/project/<project_name>/dependencies/by-tasks', methods=['DELETE'])
def api_delete_dependency_by_tasks(project_name):
    """Delete a dependency between two specific tasks"""
    try:
        data = request.json
        success = db_manager.delete_dependency_by_tasks(data['predecessor_id'], data['successor_id'])
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("Dashboard Generator Web Server")
    print("=" * 80)
    print(f"Server URL: http://localhost:{config.SERVER_PORT}")
    print(f"Database: {config.DATABASE_PATH}")
    print(f"Upload endpoint: /api/upload-excel")
    print("=" * 80)
    print("\nServer starts clean - upload Excel files via web interface")
    print("Press Ctrl+C to stop the server\n")
    
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        debug=config.DEBUG_MODE
    )
