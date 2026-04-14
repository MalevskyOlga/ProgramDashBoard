"""
Database Manager for Dashboard Generator Web Server
Handles all SQLite database operations
"""

import sqlite3
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import config


class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        
    def get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path, timeout=config.DB_TIMEOUT)
        conn.row_factory = sqlite3.Row
        return conn
    
    def initialize_database(self):
        """Create database tables if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                manager TEXT,
                excel_filename TEXT,
                last_imported TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tasks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                reference_id TEXT,
                name TEXT NOT NULL,
                phase TEXT,
                owner TEXT,
                start_date DATE,
                end_date DATE,
                status TEXT,
                date_closed DATE,
                result TEXT,
                critical INTEGER DEFAULT 0,
                milestone INTEGER DEFAULT 0,
                tailed_out INTEGER DEFAULT 0,
                row_order INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        
        # Add critical and milestone columns to existing tables if they don't exist
        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN critical INTEGER DEFAULT 0')
        except:
            pass  # Column already exists
        
        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN milestone INTEGER DEFAULT 0')
        except:
            pass  # Column already exists
        
        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN tailed_out INTEGER DEFAULT 0')
        except:
            pass  # Column already exists

        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN is_rework_cause INTEGER DEFAULT 0')
        except:
            pass  # Column already exists

        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN rework_original_due TEXT')
        except:
            pass  # Column already exists

        try:
            cursor.execute('ALTER TABLE gate_sign_offs ADD COLUMN rework_sign_off_date TEXT')
        except:
            pass  # Column already exists

        try:
            cursor.execute('ALTER TABLE tasks ADD COLUMN cloned_from_phase TEXT')
        except:
            pass  # Column already exists

        # Gate sign-offs table- tracks gate pass/pass-with-rework decisions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_sign_offs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                gate_id INTEGER NOT NULL,
                sign_off_date TEXT NOT NULL,
                rework_due_date TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_name, gate_name)
            )
        ''')

        # Gate baselines table - stores original planned dates for Gates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                gate_id INTEGER NOT NULL,
                baseline_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_name, gate_name)
            )
        ''')
        
        # Gate change log table - tracks all Gate deadline changes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gate_change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                gate_id INTEGER NOT NULL,
                baseline_date TEXT NOT NULL,
                old_date TEXT NOT NULL,
                new_date TEXT NOT NULL,
                days_delayed INTEGER NOT NULL,
                triggered_by_task_id INTEGER,
                triggered_by_task_name TEXT,
                impact_description TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Task dependencies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                predecessor_id INTEGER NOT NULL,
                successor_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(predecessor_id, successor_id),
                FOREIGN KEY (predecessor_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (successor_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        ''')

        # Resource teams table - maps owners to discipline/team for resource load view
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resource_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                owner_name TEXT NOT NULL UNIQUE,
                capacity_hrs_per_week REAL NOT NULL DEFAULT 37.5
            )
        ''')

        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gate_baselines_project ON gate_baselines(project_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gate_change_log_project ON gate_change_log(project_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_deps_project ON task_dependencies(project_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_resource_teams_owner ON resource_teams(owner_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_resource_teams_team ON resource_teams(team_name)')
        
        conn.commit()

        # Migration: add is_deleted for soft-delete support
        try:
            cursor.execute('ALTER TABLE projects ADD COLUMN is_deleted INTEGER DEFAULT 0')
            conn.commit()
        except Exception:
            pass  # column already exists

        conn.close()

        print(f"✓ Database initialized: {self.db_path}")
    
    def get_all_projects(self):
        """Get all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            WITH task_counts AS (
                SELECT
                    project_id,
                    COUNT(*) AS task_count
                FROM tasks
                GROUP BY project_id
            ),
            gate_status AS (
                SELECT
                    p.id AS project_id,
                    t.name AS gate_name,
                    gb.baseline_date,
                    t.end_date AS projected_date,
                    gso.sign_off_date,
                    COALESCE(gso.sign_off_date, t.end_date, gb.baseline_date) AS current_gate_date,
                    CASE
                        WHEN gb.baseline_date IS NOT NULL
                             AND COALESCE(gso.sign_off_date, t.end_date, gb.baseline_date) IS NOT NULL
                             AND COALESCE(gso.sign_off_date, t.end_date, gb.baseline_date) != gb.baseline_date THEN 1
                        ELSE 0
                    END AS is_gate_changed
                FROM projects p
                LEFT JOIN tasks t
                    ON t.project_id = p.id
                   AND t.milestone = 1
                   AND t.name IN ('Gate 4', 'Gate 5')
                LEFT JOIN gate_baselines gb
                    ON gb.project_name = p.name
                   AND gb.gate_name = t.name
                LEFT JOIN gate_sign_offs gso
                    ON gso.project_name = p.name
                   AND gso.gate_name = t.name
                WHERE t.id IS NOT NULL
            ),
            gate_rollup AS (
                SELECT
                    project_id,
                    SUM(is_gate_changed) AS changed_gate_count,
                    GROUP_CONCAT(CASE WHEN is_gate_changed = 1 THEN gate_name END, ', ') AS changed_gate_names
                FROM gate_status
                GROUP BY project_id
            )
            SELECT
                p.*,
                COALESCE(tc.task_count, 0) AS task_count,
                COALESCE(gr.changed_gate_count, 0) AS changed_gate_count,
                COALESCE(gr.changed_gate_names, '') AS changed_gate_names
            FROM projects p
            LEFT JOIN task_counts tc
                ON tc.project_id = p.id
            LEFT JOIN gate_rollup gr
                ON gr.project_id = p.id
            WHERE (p.is_deleted = 0 OR p.is_deleted IS NULL)
            ORDER BY p.updated_at DESC
        ''')
        
        projects = []
        for row in cursor.fetchall():
            project = dict(row)
            changed_gate_count = int(project.get('changed_gate_count') or 0)
            changed_gate_names = [name.strip() for name in (project.get('changed_gate_names') or '').split(',') if name and name.strip()]
            project['changed_gate_count'] = changed_gate_count
            project['changed_gate_names'] = changed_gate_names
            project['is_delayed'] = changed_gate_count > 0
            projects.append(project)
        conn.close()
        
        return projects
    
    def get_project_by_name(self, name):
        """Get a project by name"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE name = ? AND (is_deleted = 0 OR is_deleted IS NULL)', (name,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_project_by_id(self, project_id):
        """Get a project by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def create_or_update_project(self, name, manager, excel_filename):
        """Create a new project or update existing one"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO projects (name, manager, excel_filename, last_imported, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                manager = excluded.manager,
                excel_filename = excluded.excel_filename,
                last_imported = excluded.last_imported,
                updated_at = excluded.updated_at
        ''', (name, manager, excel_filename, now, now))
        
        project_id = cursor.lastrowid
        
        # If it was an update, get the actual project ID
        if project_id == 0:
            cursor.execute('SELECT id FROM projects WHERE name = ?', (name,))
            project_id = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return project_id
    
    def get_tasks_by_project(self, project_name):
        """Get all tasks for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.* FROM tasks t
            JOIN projects p ON t.project_id = p.id
            WHERE p.name = ?
            ORDER BY t.row_order, t.id
        ''', (project_name,))
        
        tasks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return tasks
    
    def get_task_by_id(self, task_id):
        """Get a task by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def create_task(self, task_data):
        """Create a new task"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO tasks (
                project_id, reference_id, name, phase, owner,
                start_date, end_date, status, date_closed, result,
                critical, milestone, tailed_out, row_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_data['project_id'],
            task_data.get('reference_id', ''),
            task_data['name'],
            task_data.get('phase', ''),
            task_data.get('owner', ''),
            task_data.get('start_date', ''),
            task_data.get('end_date', ''),
            task_data.get('status', 'Planned'),
            task_data.get('date_closed', ''),
            task_data.get('result', ''),
            task_data.get('critical', 0),
            task_data.get('milestone', 0),
            task_data.get('tailed_out', 0),
            task_data.get('row_order', 999),
            now,
            now
        ))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return task_id
    
    def update_task(self, task_id, task_data):
        """Update an existing task"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        update_values = []
        
        allowed_fields = ['reference_id', 'name', 'phase', 'owner', 'start_date', 
                         'end_date', 'status', 'date_closed', 'result', 'row_order',
                         'critical', 'milestone', 'tailed_out', 'is_rework_cause',
                         'rework_original_due', 'cloned_from_phase']
        
        for field in allowed_fields:
            if field in task_data:
                update_fields.append(f'{field} = ?')
                update_values.append(task_data[field])
        
        if not update_fields:
            conn.close()
            return False
        
        update_fields.append('updated_at = ?')
        update_values.append(now)
        update_values.append(task_id)
        
        query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
        
        cursor.execute(query, update_values)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete_task(self, task_id):
        """Delete a task"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete_tasks_by_project(self, project_id):
        """Delete all tasks for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count

    def soft_delete_project(self, project_name):
        """Mark a project as deleted without removing data (supports undo)."""
        conn = self.get_connection()
        try:
            conn.execute('UPDATE projects SET is_deleted = 1 WHERE name = ?', (project_name,))
            conn.commit()
            return True
        finally:
            conn.close()

    def restore_project(self, project_name):
        """Restore a soft-deleted project."""
        conn = self.get_connection()
        try:
            conn.execute('UPDATE projects SET is_deleted = 0 WHERE name = ?', (project_name,))
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_project(self, project_name):
        """Delete a project and all its related data (tasks, dependencies, gates)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id FROM projects WHERE name = ?', (project_name,))
            row = cursor.fetchone()
            if not row:
                return False
            project_id = row[0]
            cursor.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
            cursor.execute('DELETE FROM task_dependencies WHERE project_name = ?', (project_name,))
            cursor.execute('DELETE FROM gate_sign_offs WHERE project_name = ?', (project_name,))
            cursor.execute('DELETE FROM gate_baselines WHERE project_name = ?', (project_name,))
            cursor.execute('DELETE FROM gate_change_log WHERE project_name = ?', (project_name,))
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_total_task_count(self):
        """Get total number of tasks across all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM tasks')
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    # Gate Baseline Management
    
    def get_gate_baselines(self, project_name):
        """Get all Gate baselines for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM gate_baselines 
            WHERE project_name = ?
            ORDER BY baseline_date
        ''', (project_name,))
        
        baselines = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return baselines
    
    def create_gate_baseline(self, project_name, gate_name, gate_id, baseline_date):
        """Create a Gate baseline (or update if exists)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO gate_baselines 
            (project_name, gate_name, gate_id, baseline_date, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (project_name, gate_name, gate_id, baseline_date, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return True
    
    def get_gate_baseline(self, project_name, gate_name):
        """Get specific Gate baseline"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM gate_baselines 
            WHERE project_name = ? AND gate_name = ?
        ''', (project_name, gate_name))
        
        baseline = cursor.fetchone()
        conn.close()
        
        return dict(baseline) if baseline else None

    def get_overall_gate_timeline(self):
        """Get a unified gate timeline across all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            WITH gate_tasks AS (
                SELECT
                    p.name AS project_name,
                    t.name AS gate_name,
                    CAST(REPLACE(t.name, 'Gate ', '') AS INTEGER) AS gate_id,
                    t.start_date,
                    t.end_date AS projected_date,
                    gb.baseline_date,
                    gso.sign_off_date,
                    gso.status AS sign_off_status,
                    gso.rework_due_date
                FROM tasks t
                JOIN projects p
                    ON p.id = t.project_id
                LEFT JOIN gate_baselines gb
                    ON gb.project_name = p.name
                   AND gb.gate_name = t.name
                LEFT JOIN gate_sign_offs gso
                    ON gso.project_name = p.name
                   AND gso.gate_name = t.name
                WHERE t.milestone = 1
                  AND t.name LIKE 'Gate %'
            )
            SELECT
                project_name,
                gate_name,
                gate_id,
                start_date,
                projected_date,
                baseline_date,
                sign_off_date,
                sign_off_status,
                rework_due_date,
                COALESCE(sign_off_date, projected_date, baseline_date) AS display_date,
                CASE
                    WHEN sign_off_date IS NOT NULL THEN 'Signed Off'
                    WHEN projected_date IS NOT NULL THEN 'Projected'
                    ELSE 'Baseline'
                END AS date_source
            FROM gate_tasks

            UNION ALL

            SELECT
                project_name,
                gate_name,
                gate_id,
                start_date,
                projected_date,
                baseline_date,
                sign_off_date,
                sign_off_status,
                rework_due_date,
                rework_due_date AS display_date,
                'Rework Due' AS date_source
            FROM gate_tasks
            WHERE sign_off_status = 'Passed with Rework'
              AND rework_due_date IS NOT NULL

            ORDER BY display_date, project_name, gate_name, date_source
        ''')

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_overall_resource_load(self):
        """Get a unified owner workload view across all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                p.name AS project_name,
                t.id AS task_id,
                t.name AS task_name,
                t.phase,
                t.owner,
                t.start_date,
                t.end_date,
                t.status,
                t.date_closed,
                t.critical,
                t.tailed_out
            FROM tasks t
            JOIN projects p
                ON p.id = t.project_id
            WHERE COALESCE(TRIM(t.owner), '') <> ''
              AND COALESCE(t.milestone, 0) = 0
              AND t.start_date IS NOT NULL
              AND t.end_date IS NOT NULL
            ORDER BY t.owner, t.start_date, p.name, t.name
        ''')

        task_rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        def count_working_days(start_date, end_date):
            current_date = start_date
            working_days = 0
            while current_date <= end_date:
                if current_date.weekday() < 5:
                    working_days += 1
                current_date = current_date + timedelta(days=1)
            return max(1, working_days)

        def normalize_status(value):
            return (value or '').strip().lower().replace('-', ' ')

        owners = {}
        all_dates = []
        today = datetime.now().date()

        for row in task_rows:
            owner_name = (row['owner'] or '').strip()
            if not owner_name:
                continue

            start_date = datetime.strptime(row['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(row['end_date'], '%Y-%m-%d').date()
            if end_date < start_date:
                start_date, end_date = end_date, start_date

            duration_days = max(1, (end_date - start_date).days + 1)
            working_days = count_working_days(start_date, end_date)
            status_value = (row['status'] or '').strip()
            normalized_status = normalize_status(status_value)
            is_completed = status_value.lower() == 'completed'
            is_active_today = (start_date <= today <= end_date) and not is_completed
            closed_date_value = (row['date_closed'] or '').strip()
            closed_date = datetime.strptime(closed_date_value[:10], '%Y-%m-%d').date() if closed_date_value else None
            is_open_delayed = (not is_completed) and end_date < today
            is_closed_delayed = is_completed and closed_date is not None and closed_date > end_date
            is_delayed = is_open_delayed or is_closed_delayed
            delay_reason = 'Open overdue' if is_open_delayed else ('Closed late' if is_closed_delayed else None)

            task_item = {
                'task_id': row['task_id'],
                'project_name': row['project_name'],
                'task_name': row['task_name'],
                'phase': row['phase'],
                'owner': owner_name,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'status': status_value,
                'date_closed': closed_date.isoformat() if closed_date else None,
                'critical': bool(row['critical']),
                'tailed_out': bool(row['tailed_out']),
                'duration_days': duration_days,
                'working_days': working_days,
                'is_active_today': is_active_today,
                'is_delayed': is_delayed,
                'delay_reason': delay_reason
            }

            owner_entry = owners.setdefault(owner_name, {
                'owner': owner_name,
                'task_count': 0,
                'active_today_count': 0,
                'critical_task_count': 0,
                'delayed_task_count': 0,
                'tailed_out_count': 0,
                'planned_working_days': 0,
                'in_process_working_days': 0,
                'project_names': set(),
                'date_points': [],
                'pm_date_points': [],
                'tasks': []
            })

            owner_entry['task_count'] += 1
            owner_entry['active_today_count'] += 1 if is_active_today else 0
            owner_entry['critical_task_count'] += 1 if task_item['critical'] else 0
            owner_entry['delayed_task_count'] += 1 if task_item['is_delayed'] else 0
            owner_entry['tailed_out_count'] += 1 if task_item['tailed_out'] else 0
            owner_entry['planned_working_days'] += working_days if normalized_status == 'planned' else 0
            owner_entry['in_process_working_days'] += working_days if normalized_status == 'in process' else 0
            owner_entry['project_names'].add(row['project_name'])
            # Only count active/future tasks for concurrent load (exclude completed)
            if normalized_status in ('planned', 'in process'):
                owner_entry['date_points'].append((start_date, 1))
                owner_entry['date_points'].append((end_date, -1))
            owner_entry['tasks'].append(task_item)
            all_dates.extend([start_date, end_date])

        # Build managed-projects map: manager_name -> list of active projects they own
        conn2 = self.get_connection()
        proj_rows = conn2.execute('''
            SELECT p.name AS proj_name,
                   TRIM(p.manager) AS manager,
                   SUM(CASE WHEN t.status IN ('In Process','Planned') THEN 1 ELSE 0 END) AS active_tasks,
                   MIN(CASE WHEN t.status IN ('In Process','Planned') THEN t.start_date ELSE NULL END) AS proj_start,
                   MAX(CASE WHEN t.status IN ('In Process','Planned') THEN t.end_date ELSE NULL END) AS proj_end
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE TRIM(COALESCE(p.manager,'')) != ''
            GROUP BY p.id, p.name, p.manager
        ''').fetchall()
        conn2.close()

        manager_projects = {}
        for pr in proj_rows:
            proj_name  = pr['proj_name']
            manager    = pr['manager']
            active_cnt = pr['active_tasks'] or 0
            if active_cnt > 0:
                manager_projects.setdefault(manager, []).append({
                    'name': proj_name,
                    'active_tasks': active_cnt,
                    'start_date': pr['proj_start'],
                    'end_date': pr['proj_end']
                })

        # Build flexible manager-to-owner lookup:
        # Try exact match first, then first-name-only match (e.g. "Olga Malevsky" -> "Olga")
        def resolve_manager(manager_name, owner_names_set):
            if manager_name in owner_names_set:
                return manager_name
            first = manager_name.split()[0] if manager_name else ''
            if first and first in owner_names_set:
                return first
            # Try: any owner whose name is a prefix/suffix of manager name
            for owner in owner_names_set:
                if owner and (manager_name.startswith(owner) or manager_name.endswith(owner)):
                    return owner
            return None

        owner_names_set = set(owners.keys())
        # Remap manager_projects keys to match actual owner keys
        remapped_manager_projects = {}
        for manager_name, projs in manager_projects.items():
            resolved = resolve_manager(manager_name, owner_names_set)
            if resolved:
                existing = remapped_manager_projects.setdefault(resolved, [])
                # avoid duplicates
                seen = {p['name'] for p in existing}
                for p in projs:
                    if p['name'] not in seen:
                        existing.append(p)
                        seen.add(p['name'])

        # Inject PM overhead into pm_date_points and add synthetic [PM] tasks
        PM_LOAD_PER_PROJECT = 5  # 5 equivalent tasks per month per managed project
        today_str = today.isoformat()
        for owner_name, managed_projs in remapped_manager_projects.items():
            if owner_name not in owners:
                owners[owner_name] = {
                    'owner': owner_name,
                    'task_count': 0,
                    'active_today_count': 0,
                    'critical_task_count': 0,
                    'delayed_task_count': 0,
                    'tailed_out_count': 0,
                    'planned_working_days': 0,
                    'in_process_working_days': 0,
                    'project_names': set(),
                    'date_points': [],
                    'pm_date_points': [],
                    'tasks': []
                }
            owner_entry = owners[owner_name]
            for proj in managed_projs:
                pstart = proj.get('start_date')
                pend   = proj.get('end_date')
                if pstart and pend:
                    owner_entry['pm_date_points'].append((pstart, PM_LOAD_PER_PROJECT))
                    owner_entry['pm_date_points'].append((pend,  -PM_LOAD_PER_PROJECT))
                    is_active = pstart <= today_str <= pend
                    owner_entry['active_today_count'] += 1 if is_active else 0
                    owner_entry['project_names'].add(proj['name'])
                    owner_entry['task_count'] += 1  # 1 synthetic task entry
                    owner_entry['tasks'].append({
                        'task_id': f'pm_{proj["name"]}',
                        'task_name': f'[PM] {proj["name"]}',
                        'project_name': proj['name'],
                        'start_date': pstart,
                        'end_date': pend,
                        'status': 'In Process' if is_active else 'Planned',
                        'date_closed': None,
                        'critical': False,
                        'tailed_out': False,
                        'duration_days': 0,
                        'working_days': 0,
                        'is_active_today': is_active,
                        'is_delayed': False,
                        'delay_reason': None,
                        'is_pm_overhead': True,
                        'pm_weight': PM_LOAD_PER_PROJECT,
                        'phase': '',
                        'owner': owner_name
                    })

        owner_rows = []
        for owner_name, owner_entry in owners.items():
            # Sweep real task date_points for direct concurrent load
            concurrent_load = 0
            current_load = 0
            for date_point, delta in sorted(owner_entry['date_points'], key=lambda item: (item[0], -item[1])):
                current_load += delta
                if current_load > concurrent_load:
                    concurrent_load = current_load

            # Sweep combined (real + PM overhead) for effective concurrent load
            effective_concurrent_load = 0
            current_eff = 0
            combined_points = owner_entry['date_points'] + owner_entry['pm_date_points']
            for date_point, delta in sorted(combined_points, key=lambda item: (item[0], -item[1])):
                current_eff += delta
                if current_eff > effective_concurrent_load:
                    effective_concurrent_load = current_eff

            managed = remapped_manager_projects.get(owner_name, [])

            owner_entry['tasks'].sort(key=lambda item: (item['start_date'], item['end_date'], item['project_name'], item['task_name']))
            owner_rows.append({
                'owner': owner_name,
                'task_count': owner_entry['task_count'],
                'active_today_count': owner_entry['active_today_count'],
                'critical_task_count': owner_entry['critical_task_count'],
                'delayed_task_count': owner_entry['delayed_task_count'],
                'tailed_out_count': owner_entry['tailed_out_count'],
                'planned_working_days': owner_entry['planned_working_days'],
                'in_process_working_days': owner_entry['in_process_working_days'],
                'project_count': len(owner_entry['project_names']),
                'project_names': sorted(owner_entry['project_names']),
                'peak_parallel_tasks': concurrent_load,
                'concurrent_load': concurrent_load,
                'effective_concurrent_load': effective_concurrent_load,
                'managed_projects': managed,
                'has_delayed_tasks': owner_entry['delayed_task_count'] > 0,
                'tasks': owner_entry['tasks']
            })

        owner_rows.sort(key=lambda item: (-item['active_today_count'], -item['effective_concurrent_load'], item['owner'].lower()))

        summary = {
            'owner_count': len(owner_rows),
            'task_count': len(task_rows),
            'owners_active_today': sum(1 for owner in owner_rows if owner['active_today_count'] > 0),
            'owners_with_delays': sum(1 for owner in owner_rows if owner['has_delayed_tasks']),
            'owners_without_delays': sum(1 for owner in owner_rows if not owner['has_delayed_tasks']),
            'delayed_task_count': sum(owner['delayed_task_count'] for owner in owner_rows),
            'max_parallel_tasks': max((owner['effective_concurrent_load'] for owner in owner_rows), default=0),
            'max_concurrent_load': max((owner['effective_concurrent_load'] for owner in owner_rows), default=0),
            'planned_working_days': sum(owner['planned_working_days'] for owner in owner_rows),
            'in_process_working_days': sum(owner['in_process_working_days'] for owner in owner_rows),
            'range_start': min(all_dates).isoformat() if all_dates else None,
            'range_end': max(all_dates).isoformat() if all_dates else None
        }

        return {
            'summary': summary,
            'owners': owner_rows
        }

    def get_overall_critical_path_overview(self):
        """Get a Gate-5-focused management chain projected from detailed gantts"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            WITH predecessor_counts AS (
                SELECT successor_id AS task_id, COUNT(*) AS predecessor_count
                FROM task_dependencies
                GROUP BY successor_id
            ),
            successor_counts AS (
                SELECT predecessor_id AS task_id, COUNT(*) AS successor_count
                FROM task_dependencies
                GROUP BY predecessor_id
            )
            SELECT
                p.name AS project_name,
                p.manager AS project_manager,
                t.id AS task_id,
                t.name AS task_name,
                t.phase,
                t.owner,
                t.start_date,
                t.end_date,
                t.status,
                t.date_closed,
                t.milestone,
                COALESCE(t.tailed_out, 0) AS tailed_out,
                COALESCE(pc.predecessor_count, 0) AS predecessor_count,
                COALESCE(sc.successor_count, 0) AS successor_count
            FROM tasks t
            JOIN projects p
                ON p.id = t.project_id
            LEFT JOIN predecessor_counts pc
                ON pc.task_id = t.id
            LEFT JOIN successor_counts sc
                ON sc.task_id = t.id
            WHERE t.end_date IS NOT NULL
            ORDER BY p.name, t.end_date, t.row_order, t.id
        ''')
        rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute('''
            SELECT
                project_name,
                predecessor_id,
                successor_id
            FROM task_dependencies
            ORDER BY project_name, predecessor_id, successor_id
        ''')
        dependency_rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        today = datetime.now().date()
        gate_pattern = re.compile(r'gate\s*(\d+)', re.IGNORECASE)
        review_keywords = ('fdr', 'pdr', 'cdr', 'trr', 'mrr', 'review')

        def parse_date(value):
            if not value:
                return None
            return datetime.strptime(value[:10], '%Y-%m-%d').date()

        def phase_gate_number(task):
            for text_value in (task.get('phase'), task.get('task_name')):
                if not text_value:
                    continue
                match = gate_pattern.search(text_value)
                if match:
                    return int(match.group(1))
            return None

        def is_gate_task(task):
            return bool(task.get('milestone')) and bool(gate_pattern.search(task.get('task_name') or ''))

        def looks_like_review(task):
            task_name = (task.get('task_name') or '').strip()
            lowered = task_name.lower()
            return any(keyword in lowered for keyword in review_keywords)

        def get_driver_priority(task):
            lowered = (task.get('task_name') or '').strip().lower()
            if 'certification process' in lowered or 'certifications' in lowered or 'certif' in lowered:
                return 3
            if 'csa application' in lowered:
                return 2
            if looks_like_review(task):
                return 1
            return 0

        normalized_rows = []
        tasks_by_project = {}
        for row in rows:
            end_date = parse_date((row['end_date'] or '').strip())
            start_date = parse_date((row['start_date'] or '').strip())
            closed_date = parse_date((row['date_closed'] or '').strip())
            status_value = (row['status'] or '').strip()
            is_completed = status_value.lower() == 'completed'
            is_open_delayed = bool(end_date and (not is_completed) and end_date < today)
            is_closed_delayed = bool(end_date and is_completed and closed_date and closed_date > end_date)
            duration_days = 0
            if start_date and end_date:
                duration_days = max(0, (end_date - start_date).days)

            task = {
                'project_name': row['project_name'],
                'project_manager': row['project_manager'],
                'task_id': row['task_id'],
                'task_name': row['task_name'],
                'phase': row['phase'],
                'owner': row['owner'],
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'status': status_value,
                'date_closed': closed_date.isoformat() if closed_date else None,
                'milestone': bool(row['milestone']),
                'tailed_out': bool(row['tailed_out']),
                'predecessor_count': int(row['predecessor_count'] or 0),
                'successor_count': int(row['successor_count'] or 0),
                'gate_number': None,
                'is_delayed': is_open_delayed or is_closed_delayed,
                'delay_reason': 'Open overdue' if is_open_delayed else ('Closed late' if is_closed_delayed else None),
                'is_active_today': bool(start_date and end_date and start_date <= today <= end_date),
                'duration_days': duration_days
            }
            task['gate_number'] = phase_gate_number(task)
            normalized_rows.append(task)
            tasks_by_project.setdefault(task['project_name'], []).append(task)

        dependencies_by_project = {}
        for dependency in dependency_rows:
            dependencies_by_project.setdefault(dependency['project_name'], []).append(dependency)

        def pick_best_candidate(candidates, task_lookup, successor_map):
            if not candidates:
                return None

            def rank(candidate):
                candidate_gate = candidate.get('gate_number') or -1
                successor_ids = successor_map.get(candidate['task_id'], [])
                successors = [
                    task_lookup[successor_id]
                    for successor_id in successor_ids
                    if successor_id in task_lookup
                ]
                has_later_phase_successor = any(
                    (successor.get('gate_number') or -1) > candidate_gate
                    for successor in successors
                )
                end_date = parse_date(candidate.get('end_date')) or datetime(1900, 1, 1).date()
                start_date = parse_date(candidate.get('start_date')) or datetime(1900, 1, 1).date()
                return (
                    1 if has_later_phase_successor else 0,
                    get_driver_priority(candidate),
                    end_date.toordinal(),
                    int(candidate.get('duration_days') or 0),
                    -start_date.toordinal(),
                    int(candidate.get('successor_count') or 0),
                    candidate.get('task_name', '').lower()
                )

            return max(candidates, key=rank)

        def previous_gate_for_task(task, gate_tasks):
            task_date = parse_date(task.get('end_date'))
            candidates = [
                gate for gate in gate_tasks
                if gate['task_id'] != task['task_id']
                and parse_date(gate.get('end_date'))
                and parse_date(gate.get('end_date')) < task_date
            ]
            if not candidates:
                return None

            current_gate_number = task.get('gate_number')
            if current_gate_number:
                exact_candidates = [
                    gate for gate in candidates
                    if gate.get('gate_number') == current_gate_number - 1
                ]
                if exact_candidates:
                    return max(exact_candidates, key=lambda gate: gate['end_date'])

            return max(candidates, key=lambda gate: gate['end_date'])

        project_rows = []
        all_project_chain_tasks = []

        for project_name, project_tasks in tasks_by_project.items():
            project_tasks = [
                task for task in project_tasks
                if not task['tailed_out'] and task['end_date']
            ]
            if not project_tasks:
                continue

            task_lookup = {task['task_id']: task for task in project_tasks}
            predecessor_map = {}
            successor_map = {}
            for dependency in dependencies_by_project.get(project_name, []):
                predecessor_id = dependency['predecessor_id']
                successor_id = dependency['successor_id']
                predecessor_map.setdefault(successor_id, []).append(predecessor_id)
                successor_map.setdefault(predecessor_id, []).append(successor_id)

            gate_tasks = sorted(
                [task for task in project_tasks if is_gate_task(task)],
                key=lambda task: (task['end_date'], task['task_name'].lower())
            )
            if not gate_tasks:
                continue

            target_gate = next((gate for gate in gate_tasks if gate.get('gate_number') == 5), gate_tasks[-1])

            def phase_driver_for_gate(gate_task):
                explicit_predecessors = [
                    task_lookup[task_id]
                    for task_id in predecessor_map.get(gate_task['task_id'], [])
                    if task_id in task_lookup and not task_lookup[task_id]['tailed_out']
                ]
                if explicit_predecessors:
                    return pick_best_candidate(explicit_predecessors, task_lookup, successor_map)

                gate_date = parse_date(gate_task['end_date'])
                same_phase_candidates = [
                    task for task in project_tasks
                    if task['task_id'] != gate_task['task_id']
                    and not is_gate_task(task)
                    and task.get('gate_number') == gate_task.get('gate_number')
                    and parse_date(task['end_date'])
                    and parse_date(task['end_date']) <= gate_date
                ]
                return pick_best_candidate(same_phase_candidates, task_lookup, successor_map)

            target_driver = phase_driver_for_gate(target_gate)
            previous_gate = previous_gate_for_task(target_driver or target_gate, gate_tasks)
            previous_driver = phase_driver_for_gate(previous_gate) if previous_gate else None

            chain = []
            seen_ids = set()
            for item in (previous_driver, previous_gate, target_driver, target_gate):
                if not item or item['task_id'] in seen_ids:
                    continue
                seen_ids.add(item['task_id'])
                chain.append(item)

            if not chain:
                chain = [target_gate]

            project_gates = [{
                'gate_name': gate['task_name'],
                'gate_date': gate['end_date'],
                'is_upcoming': bool(parse_date(gate['end_date']) and parse_date(gate['end_date']) >= today)
            } for gate in gate_tasks]
            upcoming_gates = [gate for gate in project_gates if gate['is_upcoming']]
            selected_gate = min(upcoming_gates, key=lambda gate: gate['gate_date']) if upcoming_gates else project_gates[-1]

            project_entry = {
                'project_name': project_name,
                'project_manager': project_tasks[0]['project_manager'],
                'critical_task_count': len(chain),
                'delayed_critical_count': sum(1 for task in chain if task['is_delayed']),
                'active_critical_count': sum(1 for task in chain if task['is_active_today']),
                'milestone_critical_count': sum(1 for task in chain if task['milestone']),
                'gate_5_date': target_gate['end_date'] if target_gate.get('gate_number') == 5 else None,
                'next_gate_name': selected_gate['gate_name'],
                'next_gate_date': selected_gate['gate_date'],
                'next_gate_is_upcoming': selected_gate['is_upcoming'],
                'tasks': chain,
                'critical_path_tasks': chain
            }

            project_rows.append(project_entry)
            all_project_chain_tasks.extend(chain)

        project_rows.sort(key=lambda item: (
            item['gate_5_date'] or item['next_gate_date'] or '9999-12-31',
            item['project_name'].lower()
        ))

        summary = {
            'critical_task_count': sum(project['critical_task_count'] for project in project_rows),
            'project_count': len(project_rows),
            'delayed_critical_count': sum(project['delayed_critical_count'] for project in project_rows),
            'active_critical_count': sum(project['active_critical_count'] for project in project_rows),
            'milestone_critical_count': sum(project['milestone_critical_count'] for project in project_rows)
        }

        return {
            'summary': summary,
            'projects': project_rows,
            'tasks': all_project_chain_tasks
        }
    
    # Gate Change Log Management
    
    def get_gate_change_log(self, project_name):
        """Get all Gate changes for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM gate_change_log 
            WHERE project_name = ?
            ORDER BY changed_at DESC
        ''', (project_name,))
        
        changes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return changes
    
    def add_gate_change_log(self, log_data):
        """Add a Gate change log entry"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO gate_change_log 
            (project_name, gate_name, gate_id, baseline_date, old_date, new_date, 
             days_delayed, triggered_by_task_id, triggered_by_task_name, 
             impact_description, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            log_data['project_name'],
            log_data['gate_name'],
            log_data['gate_id'],
            log_data['baseline_date'],
            log_data['old_date'],
            log_data['new_date'],
            log_data['days_delayed'],
            log_data.get('triggered_by_task_id'),
            log_data.get('triggered_by_task_name'),
            log_data.get('impact_description'),
            datetime.now().isoformat()
        ))
        
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return log_id
    
    def delete_gate_change_log_by_gate(self, project_name, gate_name):
        """Delete all change log entries for a specific Gate"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM gate_change_log 
            WHERE project_name = ? AND gate_name = ?
        ''', (project_name, gate_name))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count

    # Task Dependency Management

    def get_dependencies_by_project(self, project_name):
        """Get all task dependencies for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM task_dependencies WHERE project_name = ?', (project_name,))
        deps = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return deps

    def create_dependency(self, project_name, predecessor_id, successor_id):
        """Create a dependency between two tasks. Returns id or None if already exists."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO task_dependencies (project_name, predecessor_id, successor_id) VALUES (?, ?, ?)',
                (project_name, predecessor_id, successor_id)
            )
            dep_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return dep_id
        except Exception as e:
            conn.close()
            return None

    def delete_dependency(self, dep_id):
        """Delete a specific dependency"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM task_dependencies WHERE id = ?', (dep_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def delete_dependencies_by_project(self, project_name):
        """Delete all dependencies for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM task_dependencies WHERE project_name = ?', (project_name,))
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count

    def delete_dependency_by_tasks(self, predecessor_id, successor_id):
        """Delete a dependency between two specific tasks"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM task_dependencies WHERE predecessor_id = ? AND successor_id = ?', (predecessor_id, successor_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    # Gate Sign-Off Management

    def get_gate_sign_offs(self, project_name):
        """Get all gate sign-offs for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM gate_sign_offs WHERE project_name = ? ORDER BY gate_name', (project_name,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def upsert_gate_sign_off(self, project_name, gate_name, gate_id, sign_off_date, status, rework_due_date=None, rework_sign_off_date=None):
        """Create or update a gate sign-off"""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO gate_sign_offs
                (project_name, gate_name, gate_id, sign_off_date, rework_due_date, rework_sign_off_date, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_name, gate_name) DO UPDATE SET
                gate_id = excluded.gate_id,
                sign_off_date = excluded.sign_off_date,
                rework_due_date = excluded.rework_due_date,
                rework_sign_off_date = excluded.rework_sign_off_date,
                status = excluded.status,
                updated_at = excluded.updated_at
        ''', (project_name, gate_name, gate_id, sign_off_date, rework_due_date, rework_sign_off_date, status, now, now))
        conn.commit()
        conn.close()
        return True

    def delete_gate_sign_off(self, project_name, gate_name):
        """Remove a gate sign-off"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM gate_sign_offs WHERE project_name = ? AND gate_name = ?', (project_name, gate_name))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success
