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

        # Disciplines master list - per-division vocabulary used by the discipline map.
        # Seeded per division (see migrations/001_disciplines.sql and tenancy.create_division).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS disciplines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER DEFAULT 100,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Per-task threaded comment log (see migrations/002_task_comments.sql)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at TEXT,
                closed_by TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        ''')

        # Per-task attachments: links or uploaded files (see migrations/003_task_attachments.sql)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                label TEXT,
                url TEXT,
                stored_name TEXT,
                original_name TEXT,
                size_bytes INTEGER,
                mime TEXT,
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_comments_task_id ON task_comments(task_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_comments_task_open ON task_comments(task_id, state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_attachments_task_id ON task_attachments(task_id)')

        conn.commit()

        # Migration: add is_deleted for soft-delete support
        try:
            cursor.execute('ALTER TABLE projects ADD COLUMN is_deleted INTEGER DEFAULT 0')
            conn.commit()
        except Exception:
            pass  # column already exists

        # Migration: add program_manager field
        try:
            cursor.execute('ALTER TABLE projects ADD COLUMN program_manager TEXT')
            conn.commit()
        except Exception:
            pass  # column already exists

        # Migration: add gate_5_date field
        try:
            cursor.execute('ALTER TABLE projects ADD COLUMN gate_5_date TEXT')
            conn.commit()
        except Exception:
            pass  # column already exists

        # Risks table — ensure correct schema (project_id nullable, pipeline_project_id present)
        cursor.execute("PRAGMA table_info(risks)")
        risk_info = cursor.fetchall()
        risk_cols = [r[1] for r in risk_info]
        risk_notnull = {r[1]: r[3] for r in risk_info}  # col -> notnull flag
        needs_recreate = (
            not risk_cols                                        # table missing
            or 'project_id' not in risk_cols                    # old portfolio schema
            or risk_notnull.get('project_id', 0) == 1          # project_id wrongly NOT NULL
        )
        if needs_recreate:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS risks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    pipeline_project_id INTEGER,
                    title TEXT NOT NULL,
                    category TEXT DEFAULT 'Other',
                    probability TEXT DEFAULT 'Medium',
                    impact TEXT DEFAULT 'Medium',
                    owner TEXT,
                    mitigation TEXT,
                    status TEXT DEFAULT 'Open',
                    due_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            if risk_cols and 'project_id' in risk_cols:
                # Preserve existing rows
                common = [c for c in ['id','project_id','pipeline_project_id','title','category',
                                      'probability','impact','owner','mitigation','status',
                                      'due_date','created_at','updated_at'] if c in risk_cols]
                cols_sql = ', '.join(common)
                cursor.execute(f'INSERT INTO risks_new ({cols_sql}) SELECT {cols_sql} FROM risks')
            cursor.execute('DROP TABLE IF EXISTS risks')
            cursor.execute('ALTER TABLE risks_new RENAME TO risks')
        else:
            # Add pipeline_project_id if missing (upgrade from older install)
            try:
                cursor.execute('ALTER TABLE risks ADD COLUMN pipeline_project_id INTEGER')
            except Exception:
                pass
        conn.commit()

        # Migrate new risk fields (v2 — Excel-aligned)
        for _col, _typedef in [
            ('strategy',              "TEXT DEFAULT 'Mitigate'"),
            ('risk_type',             "TEXT DEFAULT 'Type 1'"),
            ('outcome',               'TEXT'),
            ('date_closed',           'DATE'),
            ('schedule_impact_weeks', 'REAL'),
        ]:
            try:
                cursor.execute(f'ALTER TABLE risks ADD COLUMN {_col} {_typedef}')
            except Exception:
                pass
        conn.commit()

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
            SELECT t.*,
                   (SELECT COUNT(*) FROM task_comments c
                     WHERE c.task_id = t.id AND c.state = 'open') AS open_comment_count,
                   (SELECT COUNT(*) FROM task_attachments a
                     WHERE a.task_id = t.id) AS attachment_count
            FROM tasks t
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
    
    def get_subtasks(self, parent_id):
        """Get all direct sub-tasks of a task (one level deep)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE parent_id = ?', (parent_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def _validate_task_hierarchy(self, cursor, task_id, project_id, parent_id, start_date, end_date):
        """Hard-block validation for the macro-task/sub-task containment rule (one level
        deep only). Raises ValueError with a user-facing message on any violation.
        `task_id` is None when validating a brand-new task that doesn't have an id yet."""
        if parent_id:
            if task_id is not None and parent_id == task_id:
                raise ValueError('A task cannot be its own parent.')
            cursor.execute(
                'SELECT id, project_id, parent_id, name, start_date, end_date FROM tasks WHERE id = ?',
                (parent_id,)
            )
            parent = cursor.fetchone()
            if not parent:
                raise ValueError('Parent task not found.')
            if parent['project_id'] != project_id:
                raise ValueError('Parent task must be in the same project.')
            if parent['parent_id']:
                raise ValueError(
                    'Cannot assign a sub-task as a parent — only one level of nesting is supported.'
                )
            if task_id is not None:
                cursor.execute('SELECT COUNT(*) AS c FROM tasks WHERE parent_id = ?', (task_id,))
                if cursor.fetchone()['c'] > 0:
                    raise ValueError(
                        'This task already has sub-tasks of its own and cannot become a '
                        'sub-task itself (one level of nesting only).'
                    )
            if start_date and end_date and parent['start_date'] and parent['end_date']:
                if start_date < parent['start_date'] or end_date > parent['end_date']:
                    raise ValueError(
                        f"Sub-task dates ({start_date} to {end_date}) must fall within parent "
                        f"task \"{parent['name']}\"'s date range "
                        f"({parent['start_date']} to {parent['end_date']})."
                    )

        # Parent-side: if this task already has children, its own (possibly new) dates must
        # still contain every existing child's span.
        if task_id is not None and start_date and end_date:
            cursor.execute(
                'SELECT name, start_date, end_date FROM tasks WHERE parent_id = ?', (task_id,)
            )
            children = cursor.fetchall()
            offenders = [
                c['name'] for c in children
                if (c['start_date'] and c['start_date'] < start_date)
                or (c['end_date'] and c['end_date'] > end_date)
            ]
            if offenders:
                names = ', '.join(f'"{n}"' for n in offenders[:3])
                more = f' and {len(offenders) - 3} more' if len(offenders) > 3 else ''
                raise ValueError(
                    f'New dates would exclude its own sub-task(s): {names}{more}. '
                    'Adjust the sub-task(s) first.'
                )

    def _sync_macro_due_down(self, cursor, parent_id):
        """A sub-task's due date can never exceed its macro parent's (enforced in
        _validate_task_hierarchy). Once that's satisfied, pull the parent's own due
        date DOWN to match its latest (max) sub-task due date whenever the parent is
        currently set further out than its sub-tasks need — never the opposite
        direction. Called after a sub-task's own save succeeds, same transaction."""
        cursor.execute('SELECT end_date FROM tasks WHERE id = ?', (parent_id,))
        parent = cursor.fetchone()
        if not parent or not parent['end_date']:
            return
        cursor.execute(
            "SELECT MAX(end_date) AS max_due FROM tasks "
            "WHERE parent_id = ? AND end_date IS NOT NULL AND end_date != ''",
            (parent_id,)
        )
        max_due = cursor.fetchone()['max_due']
        if max_due and max_due < parent['end_date']:
            cursor.execute(
                'UPDATE tasks SET end_date = ?, updated_at = ? WHERE id = ?',
                (max_due, datetime.now().isoformat(), parent_id)
            )

    def place_task_after(self, project_id, new_task_id, anchor_task_id, side='after'):
        """Give a newly created task the row position directly after (or before) the anchor.

        The anchor's whole block (its top-level ancestor and all of that ancestor's
        sub-tasks) stays together, so the new task lands just after or just before that
        block. Every task in the project is then renumbered (row_order = 10, 20, 30, ...).
        Returns False if either task is not in the project.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            rows = cursor.execute(
                'SELECT id, parent_id FROM tasks WHERE project_id = ? ORDER BY row_order, id',
                (project_id,)
            ).fetchall()
            parent_of = {r[0]: r[1] for r in rows}
            if anchor_task_id not in parent_of or new_task_id not in parent_of:
                return False

            # Walk up from the anchor to its top-level ancestor (guarded against bad data)
            top = anchor_task_id
            hops = 0
            while parent_of.get(top) is not None and hops <= len(parent_of):
                top = parent_of[top]
                hops += 1

            def in_block(task_id):
                current, steps = task_id, 0
                while current is not None and steps <= len(parent_of):
                    if current == top:
                        return True
                    current = parent_of.get(current)
                    steps += 1
                return False

            ids = [r[0] for r in rows if r[0] != new_task_id]
            block_positions = [i for i, tid in enumerate(ids) if in_block(tid)]
            if side == 'before':
                insert_at = block_positions[0] if block_positions else len(ids)
            else:
                insert_at = block_positions[-1] + 1 if block_positions else len(ids)
            ids.insert(insert_at, new_task_id)
            for order, tid in enumerate(ids, start=1):
                cursor.execute('UPDATE tasks SET row_order = ? WHERE id = ?', (order * 10, tid))
            conn.commit()
            return True
        finally:
            conn.close()

    def create_task(self, task_data):
        """Create a new task"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            parent_id = task_data.get('parent_id') or None
            self._validate_task_hierarchy(
                cursor, None, task_data['project_id'], parent_id,
                task_data.get('start_date'), task_data.get('end_date')
            )
        except ValueError:
            conn.close()
            raise

        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO tasks (
                project_id, reference_id, name, phase, owner,
                start_date, end_date, status, date_closed, result,
                critical, milestone, tailed_out, row_order, parent_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            parent_id,
            now,
            now
        ))

        task_id = cursor.lastrowid

        if parent_id and task_data.get('end_date'):
            self._sync_macro_due_down(cursor, parent_id)

        conn.commit()
        conn.close()

        return task_id

    def update_task(self, task_id, task_data):
        """Update an existing task"""
        conn = self.get_connection()
        cursor = conn.cursor()

        effective_parent_id = None
        if 'parent_id' in task_data or 'start_date' in task_data or 'end_date' in task_data:
            cursor.execute(
                'SELECT project_id, parent_id, start_date, end_date FROM tasks WHERE id = ?',
                (task_id,)
            )
            current = cursor.fetchone()
            if current:
                effective_parent_id = (
                    task_data.get('parent_id') if 'parent_id' in task_data else current['parent_id']
                ) or None
                effective_start = task_data.get('start_date', current['start_date'])
                effective_end = task_data.get('end_date', current['end_date'])
                try:
                    self._validate_task_hierarchy(
                        cursor, task_id, current['project_id'], effective_parent_id,
                        effective_start, effective_end
                    )
                except ValueError:
                    conn.close()
                    raise

        now = datetime.now().isoformat()

        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        update_values = []

        allowed_fields = ['reference_id', 'name', 'phase', 'owner', 'start_date',
                         'end_date', 'status', 'date_closed', 'result', 'row_order',
                         'critical', 'milestone', 'tailed_out', 'is_rework_cause',
                         'rework_original_due', 'cloned_from_phase', 'parent_id']

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

        if success and ('end_date' in task_data or 'parent_id' in task_data) and effective_parent_id:
            self._sync_macro_due_down(cursor, effective_parent_id)

        conn.commit()
        conn.close()

        return success

    def delete_task(self, task_id):
        """Delete a task. Sub-tasks (one level deep) are deleted along with their parent."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM tasks WHERE parent_id = ?', (task_id,))
        child_ids = [row['id'] for row in cursor.fetchall()]

        # FK cascade is not enabled at the connection level, so remove children explicitly
        for tid in child_ids + [task_id]:
            cursor.execute('DELETE FROM task_comments WHERE task_id = ?', (tid,))
            cursor.execute('DELETE FROM task_attachments WHERE task_id = ?', (tid,))
        if child_ids:
            cursor.execute(
                'DELETE FROM tasks WHERE id IN (%s)' % ','.join('?' * len(child_ids)),
                child_ids
            )
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def delete_tasks_by_project(self, project_id):
        """Delete all tasks for a project"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Remove children for this project's tasks first (FK cascade is not enabled)
        cursor.execute('''
            DELETE FROM task_comments
            WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)
        ''', (project_id,))
        cursor.execute('''
            DELETE FROM task_attachments
            WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ?)
        ''', (project_id,))
        cursor.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    # ---- Per-task comment log -------------------------------------------------

    def get_comments_for_task(self, task_id, include_closed=False):
        """Return a task's comment log, oldest first. Open-only unless include_closed."""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM task_comments WHERE task_id = ?'
        params = [task_id]
        if not include_closed:
            query += " AND state = 'open'"
        query += ' ORDER BY created_at, id'

        cursor.execute(query, params)
        comments = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return comments

    def add_comment(self, task_id, author, body):
        """Add an open comment to a task's log. Returns the new comment id."""
        conn = self.get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO task_comments (task_id, author, body, state, created_at)
            VALUES (?, ?, ?, 'open', ?)
        ''', (task_id, author, body, now))

        comment_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return comment_id

    def set_comment_state(self, comment_id, state, actor):
        """Close or reopen a comment. state is 'open' or 'closed'. Returns True if updated."""
        conn = self.get_connection()
        cursor = conn.cursor()

        if state == 'closed':
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE task_comments
                SET state = 'closed', closed_at = ?, closed_by = ?
                WHERE id = ?
            ''', (now, actor, comment_id))
        else:
            cursor.execute('''
                UPDATE task_comments
                SET state = 'open', closed_at = NULL, closed_by = NULL
                WHERE id = ?
            ''', (comment_id,))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def get_open_comment_count(self, task_id):
        """Return the number of open comments on a task."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM task_comments WHERE task_id = ? AND state = 'open'",
            (task_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()

        return count

    # ---- Per-task attachments -------------------------------------------------

    def get_attachments_for_task(self, task_id):
        """Return a task's attachments, oldest first."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM task_attachments WHERE task_id = ? ORDER BY created_at, id',
            (task_id,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def add_link_attachment(self, task_id, label, url, uploaded_by):
        """Add a link attachment to a task. Returns the new attachment id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO task_attachments (task_id, kind, label, url, uploaded_by, created_at)
            VALUES (?, 'link', ?, ?, ?, ?)
        ''', (task_id, label, url, uploaded_by, now))
        attachment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return attachment_id

    def add_file_attachment(self, task_id, label, stored_name, original_name,
                            size_bytes, mime, uploaded_by):
        """Add a file attachment record to a task. Returns the new attachment id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO task_attachments
                (task_id, kind, label, stored_name, original_name, size_bytes, mime, uploaded_by, created_at)
            VALUES (?, 'file', ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, label, stored_name, original_name, size_bytes, mime, uploaded_by, now))
        attachment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return attachment_id

    def get_attachment_by_id(self, attachment_id):
        """Get a single attachment row by id, or None."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM task_attachments WHERE id = ?', (attachment_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_attachment(self, attachment_id):
        """Delete an attachment row. Returns True if a row was removed."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM task_attachments WHERE id = ?', (attachment_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def get_attachment_count(self, task_id):
        """Return the number of attachments on a task."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM task_attachments WHERE task_id = ?', (task_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_file_attachments_for_task(self, task_id):
        """Return stored_name rows of file attachments for a task (for disk cleanup)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, task_id, stored_name FROM task_attachments WHERE task_id = ? AND kind = 'file'",
            (task_id,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_file_attachments_for_project(self, project_id):
        """Return file-attachment rows (with task_id, stored_name) for a project (for disk cleanup)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, task_id, stored_name FROM task_attachments
            WHERE kind = 'file' AND task_id IN (SELECT id FROM tasks WHERE project_id = ?)
        ''', (project_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

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

    def _ensure_archived_projects_table(self, cursor):
        """Lazily create archived_projects if the Pipeline feature hasn't touched this DB yet.

        Schema must stay compatible with server.py's _ensure_priority_tables(), which also
        creates this table — both only need it to exist, so IF NOT EXISTS makes either safe."""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archived_projects (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL DEFAULT '',
                completed_date TEXT NOT NULL DEFAULT '',
                priority       INTEGER DEFAULT 0,
                leader         TEXT DEFAULT '',
                process_type   TEXT DEFAULT '',
                next_gate      TEXT DEFAULT '',
                launch_date    TEXT DEFAULT '',
                objective      TEXT DEFAULT '',
                segment        TEXT DEFAULT ''
            )
        ''')

    # Shared WHERE-clause fragment: a project is excluded from cross-project overview
    # endpoints once it's archived via the Pipeline "Mark Complete" action, or once every
    # one of its tasks is individually marked Completed or Cancelled (Cancelled is treated
    # as closed-out, same as Completed, for "is this project still open" purposes).
    # `project_alias` must be the SQL alias/table name bound to the `projects` row
    # (needs `.id` and `.name` columns).
    def _completed_project_exclusion_sql(self, project_alias):
        return f'''
              AND LOWER(TRIM({project_alias}.name)) NOT IN
                  (SELECT LOWER(TRIM(name)) FROM archived_projects)
              AND NOT (
                  EXISTS (SELECT 1 FROM tasks _allt WHERE _allt.project_id = {project_alias}.id)
                  AND NOT EXISTS (
                      SELECT 1 FROM tasks _opent
                      WHERE _opent.project_id = {project_alias}.id
                        AND LOWER(COALESCE(_opent.status, '')) NOT IN ('completed', 'cancelled')
                  )
              )
        '''

    def get_overall_gate_timeline(self):
        """Get a unified gate timeline across all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()
        self._ensure_archived_projects_table(cursor)

        cursor.execute('''
            WITH gate_tasks AS (
                SELECT
                    p.name AS project_name,
                    t.name AS gate_name,
                    CAST(REPLACE(t.name, 'Gate ', '') AS INTEGER) AS gate_id,
                    t.start_date,
                    t.end_date AS projected_date,
                    t.status AS task_status,
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
                WHERE LOWER(t.name) LIKE '%gate%'
                  AND p.is_deleted = 0
                  ''' + self._completed_project_exclusion_sql('p') + '''
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
                    WHEN task_status = 'Completed' THEN 'Signed Off'
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
        # The SQL LIKE '%gate%' also matches substrings like "gateway"; keep only
        # whole-word "gate" names (Gate 3, Military Gate 2, Discontinued Gate A, …).
        rows = [r for r in rows if re.search(r'\bgate\b', r.get('gate_name') or '', re.IGNORECASE)]
        return rows

    def get_overall_resource_load(self):
        """Get a unified owner workload view across all projects"""
        conn = self.get_connection()
        cursor = conn.cursor()
        self._ensure_archived_projects_table(cursor)

        from datetime import date as _date_cls
        today_dt = datetime.now().date()
        cutoff_year, cutoff_month = today_dt.year, today_dt.month - config.RESOURCE_LOAD_LOOKBACK_MONTHS
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year  -= 1
        cutoff_date = _date_cls(cutoff_year, cutoff_month, 1).isoformat()

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
              AND NOT EXISTS (SELECT 1 FROM tasks _c WHERE _c.parent_id = t.id)
              AND t.start_date IS NOT NULL
              AND t.end_date IS NOT NULL
              AND t.end_date >= ?
              ''' + self._completed_project_exclusion_sql('p') + '''
            ORDER BY t.owner, t.start_date, p.name, t.name
        ''', (cutoff_date,))

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

            if not row['start_date'] or not row['end_date']:
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
            # Cancelled is closed-out just like Completed for "is this still open work" purposes
            # (active-today, overdue), but only a literal Completed task can be "closed late".
            is_closed = normalized_status in ('completed', 'cancelled')
            # On Hold tasks don't count toward "active workload" (resource load, busy badges,
            # overload spotlight) even though they aren't finished — only a delay-tracking
            # concern (is_open_delayed below) still looks at them.
            is_active_today = (start_date <= today <= end_date) and not is_closed and normalized_status != 'on hold'
            closed_date_value = (row['date_closed'] or '').strip()
            closed_date = datetime.strptime(closed_date_value[:10], '%Y-%m-%d').date() if closed_date_value else None
            is_open_delayed = (not is_closed) and end_date < today
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
                'review_working_days': 0,
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
            owner_entry['review_working_days'] += working_days if normalized_status == 'review' else 0
            owner_entry['project_names'].add(row['project_name'])
            # Only count active/future tasks for concurrent load (exclude completed/cancelled/on hold)
            if normalized_status in ('planned', 'in process', 'review'):
                owner_entry['date_points'].append((start_date, 1))
                owner_entry['date_points'].append((end_date, -1))
            owner_entry['tasks'].append(task_item)
            all_dates.extend([start_date, end_date])

        # Build managed-projects map: manager_name -> list of active projects they own
        conn2 = self.get_connection()
        cursor2 = conn2.cursor()
        self._ensure_archived_projects_table(cursor2)
        cursor2.execute('''
            SELECT p.name AS proj_name,
                   TRIM(p.manager) AS manager,
                   SUM(CASE WHEN t.status IN ('In Process','Planned','Review') THEN 1 ELSE 0 END) AS active_tasks,
                   MIN(CASE WHEN t.status IN ('In Process','Planned','Review') THEN t.start_date ELSE NULL END) AS proj_start,
                   MAX(CASE WHEN t.status IN ('In Process','Planned','Review') THEN t.end_date ELSE NULL END) AS proj_end
            FROM projects p
            LEFT JOIN tasks t ON t.project_id = p.id
            WHERE TRIM(COALESCE(p.manager,'')) != ''
              ''' + self._completed_project_exclusion_sql('p') + '''
            GROUP BY p.id, p.name, p.manager
        ''')
        proj_rows = cursor2.fetchall()
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
        PM_LOAD_PER_PROJECT = config.PM_LOAD_PER_PROJECT
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
                    'review_working_days': 0,
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
                    try:
                        pstart_d = datetime.strptime(pstart[:10], '%Y-%m-%d').date()
                        pend_d   = datetime.strptime(pend[:10],   '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        continue
                    owner_entry['pm_date_points'].append((pstart_d, PM_LOAD_PER_PROJECT))
                    owner_entry['pm_date_points'].append((pend_d,  -PM_LOAD_PER_PROJECT))
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

        # Load per-owner capacity from resource_teams (case-insensitive match)
        cap_conn = self.get_connection()
        cap_rows = cap_conn.execute(
            "SELECT TRIM(LOWER(owner_name)) AS k, capacity_hrs_per_week FROM resource_teams"
        ).fetchall()
        cap_conn.close()
        capacity_map = {row[0]: row[1] for row in cap_rows}

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

            # Capacity-aware overload threshold: scales linearly with capacity vs full-time
            capacity_hrs = capacity_map.get(owner_name.lower(), config.FULL_TIME_CAPACITY_HRS)
            overload_threshold = max(2, round(
                (capacity_hrs / config.FULL_TIME_CAPACITY_HRS) * config.OVERLOAD_TASK_THRESHOLD
            ))

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
                'review_working_days': owner_entry['review_working_days'],
                'project_count': len(owner_entry['project_names']),
                'project_names': sorted(owner_entry['project_names']),
                'peak_parallel_tasks': concurrent_load,
                'concurrent_load': concurrent_load,
                'effective_concurrent_load': effective_concurrent_load,
                'capacity_hrs_per_week': capacity_hrs,
                'overload_threshold': overload_threshold,
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
        self._ensure_archived_projects_table(cursor)

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
                p.gate_5_date AS manual_gate_5_date,
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
                COALESCE(sc.successor_count, 0) AS successor_count,
                EXISTS (SELECT 1 FROM tasks _c WHERE _c.parent_id = t.id) AS has_children
            FROM tasks t
            JOIN projects p
                ON p.id = t.project_id
            LEFT JOIN predecessor_counts pc
                ON pc.task_id = t.id
            LEFT JOIN successor_counts sc
                ON sc.task_id = t.id
            WHERE t.end_date IS NOT NULL
              ''' + self._completed_project_exclusion_sql('p') + '''
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
            is_closed = status_value.lower() in ('completed', 'cancelled')
            is_open_delayed = bool(end_date and (not is_closed) and end_date < today)
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
                'has_children': bool(row['has_children']),
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
                    and not task.get('has_children')  # never pick a macro/container task as the driver
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
                # Manual Gate 5 date (set from the project header Edit dialog) overrides the Gantt milestone
                'gate_5_date': (project_tasks[0].get('manual_gate_5_date')
                                or (target_gate['end_date'] if target_gate.get('gate_number') == 5 else None)),
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

    def _would_create_cycle(self, cursor, project_name, predecessor_id, successor_id):
        """Return True if adding predecessor_id→successor_id would create a cycle."""
        if predecessor_id == successor_id:
            return True
        # BFS: can we reach predecessor_id starting from successor_id via existing edges?
        cursor.execute(
            'SELECT predecessor_id, successor_id FROM task_dependencies WHERE project_name = ?',
            (project_name,)
        )
        succ_map = {}
        for row in cursor.fetchall():
            succ_map.setdefault(row['predecessor_id'], []).append(row['successor_id'])
        visited = set()
        queue = [successor_id]
        while queue:
            node = queue.pop()
            if node == predecessor_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            queue.extend(succ_map.get(node, []))
        return False

    def create_dependency(self, project_name, predecessor_id, successor_id):
        """Create a dependency between two tasks. Returns id, None if duplicate, or raises ValueError on cycle."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if self._would_create_cycle(cursor, project_name, predecessor_id, successor_id):
                raise ValueError(f'Adding this dependency would create a circular chain')
            cursor.execute(
                'INSERT OR IGNORE INTO task_dependencies (project_name, predecessor_id, successor_id) VALUES (?, ?, ?)',
                (project_name, predecessor_id, successor_id)
            )
            dep_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return dep_id
        except ValueError:
            conn.close()
            raise
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

    # ── Risk Management ──────────────────────────────────────────────────────

    def get_risks(self, project_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.* FROM risks r
            JOIN projects p ON p.id = r.project_id
            WHERE p.name = ? AND p.is_deleted = 0
            ORDER BY r.created_at DESC
        ''', (project_name,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def create_risk(self, project_name, title, category, probability, impact, owner, mitigation, status, due_date,
                    strategy='Mitigate', risk_type='Type 1', schedule_impact_weeks=None, outcome=None, date_closed=None,
                    date_added=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM projects WHERE name = ?', (project_name,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        project_id = row['id']
        now = datetime.now().isoformat()
        created_at = self._normalize_date_added(date_added) or now
        cursor.execute('''
            INSERT INTO risks (project_id, title, category, probability, impact, owner, mitigation, status, due_date,
                               strategy, risk_type, schedule_impact_weeks, outcome, date_closed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (project_id, title, category, probability, impact, owner, mitigation, status, due_date,
              strategy, risk_type, schedule_impact_weeks, outcome, date_closed, created_at, now))
        risk_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return risk_id

    @staticmethod
    def _normalize_date_added(date_added):
        """A bare 'YYYY-MM-DD' (from a date input or Excel) sorts correctly against
        full created_at timestamps once padded with a time component."""
        if not date_added:
            return None
        date_added = str(date_added).strip()
        if len(date_added) == 10:
            return date_added + 'T00:00:00'
        return date_added

    def update_risk(self, risk_id, title, category, probability, impact, owner, mitigation, status, due_date,
                    strategy='Mitigate', risk_type='Type 1', schedule_impact_weeks=None, outcome=None, date_closed=None,
                    date_added=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        created_at = self._normalize_date_added(date_added)
        if created_at:
            cursor.execute('''
                UPDATE risks SET title=?, category=?, probability=?, impact=?, owner=?, mitigation=?, status=?, due_date=?,
                                 strategy=?, risk_type=?, schedule_impact_weeks=?, outcome=?, date_closed=?, created_at=?, updated_at=?
                WHERE id=?
            ''', (title, category, probability, impact, owner, mitigation, status, due_date,
                  strategy, risk_type, schedule_impact_weeks, outcome, date_closed, created_at, now, risk_id))
        else:
            cursor.execute('''
                UPDATE risks SET title=?, category=?, probability=?, impact=?, owner=?, mitigation=?, status=?, due_date=?,
                                 strategy=?, risk_type=?, schedule_impact_weeks=?, outcome=?, date_closed=?, updated_at=?
                WHERE id=?
            ''', (title, category, probability, impact, owner, mitigation, status, due_date,
                  strategy, risk_type, schedule_impact_weeks, outcome, date_closed, now, risk_id))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def delete_risk(self, risk_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM risks WHERE id = ?', (risk_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return success

    def get_pipeline_risks(self, pipeline_project_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM risks WHERE pipeline_project_id = ?
            ORDER BY created_at DESC
        ''', (pipeline_project_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def create_pipeline_risk(self, pipeline_project_id, title, category, probability, impact, owner, mitigation, status, due_date,
                             strategy='Mitigate', risk_type='Type 1', schedule_impact_weeks=None, outcome=None, date_closed=None,
                             date_added=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        created_at = self._normalize_date_added(date_added) or now
        cursor.execute('''
            INSERT INTO risks (pipeline_project_id, title, category, probability, impact, owner, mitigation, status, due_date,
                               strategy, risk_type, schedule_impact_weeks, outcome, date_closed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (pipeline_project_id, title, category, probability, impact, owner, mitigation, status, due_date,
              strategy, risk_type, schedule_impact_weeks, outcome, date_closed, created_at, now))
        risk_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return risk_id

    _PROB_SCORE   = {'Low': 2, 'Medium': 3, 'High': 4, 'Very High': 5}
    _IMPACT_SCORE = {'Low': 2, 'Medium': 3, 'High': 4, 'Very High': 5}

    @staticmethod
    def _rpn(prob, impact):
        p = DatabaseManager._PROB_SCORE.get(prob, 3)
        i = DatabaseManager._IMPACT_SCORE.get(impact, 3)
        return p * i

    def get_risk_counts_all_projects(self):
        """Returns {project_id: {...}} for Gantt projects and badge display."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.project_id, r.status, r.probability, r.impact
            FROM risks r
            JOIN projects p ON p.id = r.project_id
            WHERE p.is_deleted = 0 AND r.project_id IS NOT NULL
        ''')
        rows = cursor.fetchall()
        conn.close()
        counts = {}
        for row in rows:
            pid = row['project_id']
            if pid not in counts:
                counts[pid] = {'open': 0, 'high': 0, 'medium': 0, 'total': 0}
            counts[pid]['total'] += 1
            st = (row['status'] or '').strip()
            if st not in ('Completed', 'Canceled'):
                counts[pid]['open'] += 1
                rpn = self._rpn(row['probability'], row['impact'])
                if rpn >= 16:
                    counts[pid]['high'] += 1
                elif rpn >= 9:
                    counts[pid]['medium'] += 1
        return counts

    def get_risk_counts_pipeline(self):
        """Returns {pipeline_project_id: {...}} for F&G pipeline badge display."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pipeline_project_id, status, probability, impact
            FROM risks WHERE pipeline_project_id IS NOT NULL
        ''')
        rows = cursor.fetchall()
        conn.close()
        counts = {}
        for row in rows:
            pid = row['pipeline_project_id']
            if pid not in counts:
                counts[pid] = {'open': 0, 'high': 0, 'medium': 0, 'total': 0}
            counts[pid]['total'] += 1
            st = (row['status'] or '').strip()
            if st not in ('Completed', 'Canceled'):
                counts[pid]['open'] += 1
                rpn = self._rpn(row['probability'], row['impact'])
                if rpn >= 16:
                    counts[pid]['high'] += 1
                elif rpn >= 9:
                    counts[pid]['medium'] += 1
        return counts

    def bulk_import_risks(self, risks, project_name=None, pipeline_project_id=None):
        """Insert or update a list of risk dicts, keyed by each row's 'id' (the Excel
        file's Risk ID column — round-tripped from export so re-importing an exported
        file syncs existing risks instead of duplicating every row). A risk whose id
        doesn't match an existing row in THIS project/pipeline-project (blank, unknown,
        or belonging to a different project) is inserted as new instead — an id is only
        ever matched within its own scope, never across projects.

        Among the rows being INSERTED as new (an id match is never treated as a
        duplicate — it's an intentional update), any whose Risk Statement text
        (case/whitespace-insensitive) matches either another new row earlier in the
        same file, or a risk already sitting in this project/pipeline-project, is
        logically a duplicate/overlap and is skipped (not inserted) rather than
        creating a second copy.

        Returns {'inserted': N, 'updated': M, 'skipped_duplicates': [{'title', 'reason'}]}."""
        if not risks:
            return {'inserted': 0, 'updated': 0, 'skipped_duplicates': []}
        conn = self.get_connection()
        cursor = conn.cursor()
        project_id = None
        if project_name:
            cursor.execute('SELECT id FROM projects WHERE name = ?', (project_name,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return {'inserted': 0, 'updated': 0, 'skipped_duplicates': []}
            project_id = row['id']

        if project_id is not None:
            cursor.execute('SELECT id, title FROM risks WHERE project_id = ?', (project_id,))
        else:
            cursor.execute('SELECT id, title FROM risks WHERE pipeline_project_id = ?', (pipeline_project_id,))
        existing_rows = cursor.fetchall()
        existing_ids = {row['id'] for row in existing_rows}
        existing_titles = {(row['title'] or '').strip().lower() for row in existing_rows}

        def _norm_title(t):
            return (t or '').strip().lower()

        now = datetime.now().isoformat()
        inserted = 0
        updated = 0
        skipped_duplicates = []
        seen_new_titles = set()
        for r in risks:
            risk_id = r.get('id')
            title = r.get('title') or ''
            date_added = self._normalize_date_added(r.get('date_added'))
            if risk_id is not None and risk_id in existing_ids:
                if date_added:
                    cursor.execute('''
                        UPDATE risks SET title=?, category=?, probability=?, impact=?, owner=?, mitigation=?,
                                         status=?, due_date=?, strategy=?, risk_type=?, schedule_impact_weeks=?,
                                         outcome=?, date_closed=?, created_at=?, updated_at=?
                        WHERE id=?
                    ''', (title, r.get('category','Other'),
                          r.get('probability','Medium'), r.get('impact','Medium'),
                          r.get('owner',''), r.get('mitigation',''),
                          r.get('status','In Process'), r.get('due_date'),
                          r.get('strategy','Mitigate'), r.get('risk_type','Type 1'),
                          r.get('schedule_impact_weeks'), r.get('outcome'),
                          r.get('date_closed'), date_added, now, risk_id))
                else:
                    cursor.execute('''
                        UPDATE risks SET title=?, category=?, probability=?, impact=?, owner=?, mitigation=?,
                                         status=?, due_date=?, strategy=?, risk_type=?, schedule_impact_weeks=?,
                                         outcome=?, date_closed=?, updated_at=?
                        WHERE id=?
                    ''', (title, r.get('category','Other'),
                          r.get('probability','Medium'), r.get('impact','Medium'),
                          r.get('owner',''), r.get('mitigation',''),
                          r.get('status','In Process'), r.get('due_date'),
                          r.get('strategy','Mitigate'), r.get('risk_type','Type 1'),
                          r.get('schedule_impact_weeks'), r.get('outcome'),
                          r.get('date_closed'), now, risk_id))
                updated += 1
                continue

            norm_title = _norm_title(title)
            if norm_title and norm_title in existing_titles:
                skipped_duplicates.append({'title': title, 'reason': 'Already exists in this project'})
                continue
            if norm_title and norm_title in seen_new_titles:
                skipped_duplicates.append({'title': title, 'reason': 'Duplicate row within the uploaded file'})
                continue

            cursor.execute('''
                INSERT INTO risks (project_id, pipeline_project_id, title, category, probability, impact,
                                   owner, mitigation, status, due_date, strategy, risk_type,
                                   schedule_impact_weeks, outcome, date_closed, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (project_id, pipeline_project_id,
                  title, r.get('category','Other'),
                  r.get('probability','Medium'), r.get('impact','Medium'),
                  r.get('owner',''), r.get('mitigation',''),
                  r.get('status','In Process'), r.get('due_date'),
                  r.get('strategy','Mitigate'), r.get('risk_type','Type 1'),
                  r.get('schedule_impact_weeks'), r.get('outcome'),
                  r.get('date_closed'), date_added or now, now))
            inserted += 1
            if norm_title:
                seen_new_titles.add(norm_title)
        conn.commit()
        conn.close()
        return {'inserted': inserted, 'updated': updated, 'skipped_duplicates': skipped_duplicates}

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
