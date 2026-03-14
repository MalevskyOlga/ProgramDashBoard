"""
Database Manager for Dashboard Generator Web Server
Handles all SQLite database operations
"""

import sqlite3
import json
from datetime import datetime
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

        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gate_baselines_project ON gate_baselines(project_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gate_change_log_project ON gate_change_log(project_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_deps_project ON task_dependencies(project_name)')
        
        conn.commit()
        conn.close()
        
        print(f"✓ Database initialized: {self.db_path}")
    
    def get_all_projects(self):
        """Get all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.*, COUNT(t.id) as task_count
            FROM projects p
            LEFT JOIN tasks t ON p.id = t.project_id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
        ''')
        
        projects = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return projects
    
    def get_project_by_name(self, name):
        """Get a project by name"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE name = ?', (name,))
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
