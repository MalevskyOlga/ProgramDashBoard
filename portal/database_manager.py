"""
Database Manager — Product Pipeline Portal
Handles all SQLite operations for portfolio.db
"""

import sqlite3
import json
from datetime import datetime, timedelta, date
from pathlib import Path
import config


def _today():
    return date.today().isoformat()


def _now():
    return datetime.now().isoformat(sep=' ', timespec='seconds')


class PortfolioDatabase:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DATABASE_PATH

    # ── Connection ─────────────────────────────────────────────────────────────

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=config.DB_TIMEOUT)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    # ── Schema ─────────────────────────────────────────────────────────────────

    def initialize_database(self):
        conn = self.get_connection()
        c = conn.cursor()

        # ── Portfolio projects (top-level registry) ──────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_projects (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT    UNIQUE NOT NULL,
                leader           TEXT,
                process_type     TEXT,
                next_gate        TEXT,
                planned_launch   TEXT,
                objective        TEXT,
                business_segment TEXT,
                priority         INTEGER DEFAULT 999,
                management_type  TEXT    DEFAULT 'card',
                status_text      TEXT,
                next_steps       TEXT,
                project_id       INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
                updated_at       TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Gantt project link (reuses existing projects table from dashboard) ─
        # resource_teams table also reused from dashboard app (owner_name, team_name)
        c.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT UNIQUE NOT NULL,
                manager        TEXT,
                excel_filename TEXT,
                last_imported  TEXT,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at     TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS resource_teams (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name             TEXT NOT NULL,
                owner_name            TEXT NOT NULL UNIQUE,
                capacity_hrs_per_week REAL NOT NULL DEFAULT 37.5
            )
        ''')

        # ── Tasks (gantt rows) ────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                reference_id     TEXT,
                name             TEXT NOT NULL,
                phase            TEXT,
                owner            TEXT,
                start_date       TEXT,
                end_date         TEXT,
                status           TEXT DEFAULT 'Planned',
                date_closed      TEXT,
                result           TEXT,
                critical         INTEGER DEFAULT 0,
                milestone        INTEGER DEFAULT 0,
                tailed_out       INTEGER DEFAULT 0,
                is_rework_cause  INTEGER DEFAULT 0,
                rework_original_due TEXT,
                cloned_from_phase   TEXT,
                row_order        INTEGER DEFAULT 999,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Task dependencies ─────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS task_dependencies (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name   TEXT NOT NULL,
                predecessor_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                successor_id   INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(predecessor_id, successor_id)
            )
        ''')

        # ── Gate baselines ────────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS gate_baselines (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name   TEXT NOT NULL,
                gate_name      TEXT NOT NULL,
                gate_id        INTEGER NOT NULL,
                baseline_date  TEXT NOT NULL,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_name, gate_name)
            )
        ''')

        # ── Gate change log ───────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS gate_change_log (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name           TEXT NOT NULL,
                gate_name              TEXT NOT NULL,
                gate_id                INTEGER NOT NULL,
                baseline_date          TEXT NOT NULL,
                old_date               TEXT NOT NULL,
                new_date               TEXT NOT NULL,
                days_delayed           INTEGER NOT NULL,
                triggered_by_task_id   INTEGER,
                triggered_by_task_name TEXT,
                impact_description     TEXT,
                changed_at             TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Gate sign-offs ────────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS gate_sign_offs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name     TEXT NOT NULL,
                gate_name        TEXT NOT NULL,
                gate_id          INTEGER NOT NULL,
                sign_off_date    TEXT NOT NULL,
                rework_due_date  TEXT,
                status           TEXT NOT NULL,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_name, gate_name)
            )
        ''')

        # resource_discipline_map removed — resource_teams.team_name is the discipline

        # ── Per-project resource status ───────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS project_resources (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                discipline           TEXT    NOT NULL,
                coverage             TEXT    DEFAULT 'N/A',
                demand_days          REAL    DEFAULT 0,
                is_manual_override   INTEGER DEFAULT 0,
                computed_coverage    TEXT,
                computed_demand_days REAL,
                updated_at           TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portfolio_project_id, discipline)
            )
        ''')

        # ── Card data (for card-managed projects) ─────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS card_data (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER UNIQUE REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                start_date           TEXT,
                end_date             TEXT,
                owner                TEXT,
                description          TEXT
            )
        ''')

        # ── Action items ──────────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS action_items (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                description          TEXT NOT NULL,
                owner                TEXT,
                start_date           TEXT,
                due_date             TEXT,
                status               TEXT DEFAULT 'Not Started',
                notes                TEXT,
                sort_order           INTEGER DEFAULT 0,
                created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Risks ─────────────────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS risks (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                description          TEXT NOT NULL,
                impact               TEXT DEFAULT 'Medium',
                probability          TEXT DEFAULT 'Medium',
                mitigation           TEXT,
                status               TEXT DEFAULT 'Open',
                created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Certifications ────────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS certifications (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                agency               TEXT,
                cert_name            TEXT NOT NULL,
                cert_type            TEXT,
                status               TEXT DEFAULT 'Planned',
                expected_date        TEXT,
                actual_date          TEXT,
                notes                TEXT,
                created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Updates log (activity feed) ───────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS updates_log (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                author               TEXT,
                content              TEXT NOT NULL,
                created_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Priority history ──────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS priority_history (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_project_id INTEGER NOT NULL REFERENCES portfolio_projects(id) ON DELETE CASCADE,
                old_priority         INTEGER,
                new_priority         INTEGER,
                changed_by           TEXT,
                changed_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Monthly snapshots ─────────────────────────────────────────────────
        c.execute('''
            CREATE TABLE IF NOT EXISTS monthly_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                source        TEXT DEFAULT 'manual',
                data_json     TEXT NOT NULL,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Indexes ───────────────────────────────────────────────────────────
        for stmt in [
            'CREATE INDEX IF NOT EXISTS idx_tasks_project       ON tasks(project_id)',
            'CREATE INDEX IF NOT EXISTS idx_tasks_owner         ON tasks(owner)',
            'CREATE INDEX IF NOT EXISTS idx_task_deps_pred      ON task_dependencies(predecessor_id)',
            'CREATE INDEX IF NOT EXISTS idx_task_deps_succ      ON task_dependencies(successor_id)',
            'CREATE INDEX IF NOT EXISTS idx_proj_res_proj       ON project_resources(portfolio_project_id)',
            'CREATE INDEX IF NOT EXISTS idx_action_proj         ON action_items(portfolio_project_id)',
            'CREATE INDEX IF NOT EXISTS idx_risks_proj          ON risks(portfolio_project_id)',
            'CREATE INDEX IF NOT EXISTS idx_certs_proj          ON certifications(portfolio_project_id)',
            'CREATE INDEX IF NOT EXISTS idx_updates_proj        ON updates_log(portfolio_project_id)',
            'CREATE INDEX IF NOT EXISTS idx_pp_priority         ON portfolio_projects(priority)',
            'CREATE INDEX IF NOT EXISTS idx_pp_project          ON portfolio_projects(project_id)',
            'CREATE INDEX IF NOT EXISTS idx_rt_owner            ON resource_teams(owner_name)',
        ]:
            c.execute(stmt)

        conn.commit()
        conn.close()
        print(f'[DB] Initialized: {self.db_path}')

    # ══════════════════════════════════════════════════════════════════════════
    # PORTFOLIO PROJECTS
    # ══════════════════════════════════════════════════════════════════════════

    def get_all_portfolio_projects(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT pp.*,
                   gp.id  AS gantt_project_id,
                   gp.name AS gantt_project_name
            FROM portfolio_projects pp
            LEFT JOIN projects gp ON gp.id = pp.project_id
            ORDER BY pp.priority, pp.name
        ''')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_portfolio_project(self, project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM portfolio_projects WHERE id = ?', (project_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_portfolio_project_by_name(self, name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM portfolio_projects WHERE name = ?', (name,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def upsert_portfolio_project(self, data):
        """Insert or update a portfolio project. Returns project id."""
        conn = self.get_connection()
        c = conn.cursor()
        fields = ['name', 'leader', 'process_type', 'next_gate', 'planned_launch',
                  'objective', 'business_segment', 'priority', 'management_type',
                  'status_text', 'next_steps']
        existing = None
        c.execute('SELECT id FROM portfolio_projects WHERE name = ?', (data.get('name'),))
        row = c.fetchone()
        if row:
            existing = row['id']
            set_clauses = ', '.join(f'{f} = ?' for f in fields if f in data)
            values = [data[f] for f in fields if f in data]
            values.append(_now())
            values.append(existing)
            c.execute(f'UPDATE portfolio_projects SET {set_clauses}, updated_at = ? WHERE id = ?', values)
            conn.commit()
            conn.close()
            return existing
        else:
            cols = [f for f in fields if f in data]
            placeholders = ', '.join(['?'] * len(cols))
            values = [data[f] for f in cols]
            c.execute(f'INSERT INTO portfolio_projects ({", ".join(cols)}) VALUES ({placeholders})', values)
            new_id = c.lastrowid
            conn.commit()
            conn.close()
            return new_id

    def update_portfolio_project(self, project_id, data):
        allowed = ['name', 'leader', 'process_type', 'next_gate', 'planned_launch',
                   'objective', 'business_segment', 'management_type',
                   'status_text', 'next_steps']
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return
        conn = self.get_connection()
        c = conn.cursor()
        set_clauses = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [_now(), project_id]
        c.execute(f'UPDATE portfolio_projects SET {set_clauses}, updated_at = ? WHERE id = ?', values)
        conn.commit()
        conn.close()

    def delete_portfolio_project(self, project_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM portfolio_projects WHERE id = ?', (project_id,))
        conn.commit()
        conn.close()

    # ── Priority management ───────────────────────────────────────────────────

    def reorder_priorities(self, ordered_ids, changed_by='PM'):
        """Set priority = position for each id in ordered_ids list."""
        conn = self.get_connection()
        c = conn.cursor()
        for pos, pid in enumerate(ordered_ids, start=1):
            c.execute('SELECT priority FROM portfolio_projects WHERE id = ?', (pid,))
            row = c.fetchone()
            old_pri = row['priority'] if row else None
            if old_pri != pos:
                c.execute('UPDATE portfolio_projects SET priority = ?, updated_at = ? WHERE id = ?',
                          (pos, _now(), pid))
                c.execute('''INSERT INTO priority_history
                             (portfolio_project_id, old_priority, new_priority, changed_by, changed_at)
                             VALUES (?, ?, ?, ?, ?)''',
                          (pid, old_pri, pos, changed_by, _now()))
        conn.commit()
        conn.close()

    def get_priority_history(self, project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT ph.*, pp.name AS project_name
                     FROM priority_history ph
                     JOIN portfolio_projects pp ON pp.id = ph.portfolio_project_id
                     WHERE ph.portfolio_project_id = ?
                     ORDER BY ph.changed_at DESC LIMIT 50''', (project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    # ══════════════════════════════════════════════════════════════════════════
    # GANTT PROJECTS (mirror of 5001 structure)
    # ══════════════════════════════════════════════════════════════════════════

    def get_all_projects(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT p.*, pp.id AS portfolio_project_id, pp.priority, pp.management_type,
                   COUNT(t.id) AS task_count
            FROM projects p
            JOIN portfolio_projects pp ON pp.project_id = p.id
            LEFT JOIN tasks t ON t.project_id = p.id
            GROUP BY p.id
            ORDER BY pp.priority
        ''')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_project_by_name(self, name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT p.*, pp.priority, pp.management_type, pp.status_text,
                   pp.next_steps, pp.id AS portfolio_project_id
            FROM projects p
            JOIN portfolio_projects pp ON pp.project_id = p.id
            WHERE p.name = ?
        ''', (name,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_project_by_id(self, project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_or_update_gantt_project(self, portfolio_project_id, name, manager, excel_filename=None):
        """Create or update a gantt project and link it via portfolio_projects.project_id."""
        conn = self.get_connection()
        c = conn.cursor()
        # Check if portfolio project already has a linked gantt project
        c.execute('SELECT project_id FROM portfolio_projects WHERE id = ?', (portfolio_project_id,))
        pp_row = c.fetchone()
        existing_pid = pp_row['project_id'] if pp_row else None

        if existing_pid:
            pid = existing_pid
            c.execute('''UPDATE projects SET name=?, manager=?, excel_filename=?, last_imported=?, updated_at=?
                         WHERE id=?''', (name, manager, excel_filename, _now(), _now(), pid))
        else:
            # Try to find by name in case it already exists (e.g. migrated from dashboard)
            c.execute('SELECT id FROM projects WHERE name = ?', (name,))
            name_row = c.fetchone()
            if name_row:
                pid = name_row['id']
                c.execute('''UPDATE projects SET manager=?, excel_filename=?, last_imported=?, updated_at=?
                             WHERE id=?''', (manager, excel_filename, _now(), _now(), pid))
            else:
                c.execute('''INSERT INTO projects (name, manager, excel_filename, last_imported)
                             VALUES (?, ?, ?, ?)''',
                          (name, manager, excel_filename, _now()))
                pid = c.lastrowid
            # Link portfolio project → gantt project
            c.execute('UPDATE portfolio_projects SET project_id=?, updated_at=? WHERE id=?',
                      (pid, _now(), portfolio_project_id))
        conn.commit()
        conn.close()
        return pid

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def get_tasks(self, project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM tasks WHERE project_id = ?
                     ORDER BY row_order, id''', (project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_task(self, task_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def insert_tasks_bulk(self, project_id, tasks):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
        for t in tasks:
            c.execute('''INSERT INTO tasks
                (project_id, reference_id, name, phase, owner, start_date, end_date,
                 status, date_closed, result, milestone, critical, tailed_out, row_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                project_id,
                t.get('reference_id', ''),
                t.get('name', ''),
                t.get('phase', ''),
                t.get('owner', ''),
                t.get('start_date', ''),
                t.get('end_date', ''),
                t.get('status', 'Planned'),
                t.get('date_closed', ''),
                t.get('result', ''),
                t.get('milestone', 0),
                t.get('critical', 0),
                t.get('tailed_out', 0),
                t.get('row_order', 999),
            ))
        conn.commit()
        conn.close()

    def create_task(self, project_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO tasks
            (project_id, reference_id, name, phase, owner, start_date, end_date,
             status, date_closed, result, milestone, critical, tailed_out, row_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            project_id,
            data.get('reference_id', ''),
            data.get('name', ''),
            data.get('phase', ''),
            data.get('owner', ''),
            data.get('start_date', ''),
            data.get('end_date', ''),
            data.get('status', 'Planned'),
            data.get('date_closed', ''),
            data.get('result', ''),
            data.get('milestone', 0),
            data.get('critical', 0),
            data.get('tailed_out', 0),
            data.get('row_order', 999),
        ))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def update_task(self, task_id, data):
        allowed = ['reference_id', 'name', 'phase', 'owner', 'start_date', 'end_date',
                   'status', 'date_closed', 'result', 'milestone', 'critical',
                   'tailed_out', 'row_order', 'is_rework_cause', 'rework_original_due']
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return
        conn = self.get_connection()
        c = conn.cursor()
        set_clauses = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [_now(), task_id]
        c.execute(f'UPDATE tasks SET {set_clauses}, updated_at = ? WHERE id = ?', values)
        conn.commit()
        conn.close()

    def delete_task(self, task_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

    # ── Dependencies ─────────────────────────────────────────────────────────

    def get_dependencies(self, project_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM task_dependencies WHERE project_name = ?', (project_name,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def add_dependency(self, project_name, predecessor_id, successor_id):
        conn = self.get_connection()
        try:
            conn.execute('''INSERT OR IGNORE INTO task_dependencies
                            (project_name, predecessor_id, successor_id)
                            VALUES (?, ?, ?)''', (project_name, predecessor_id, successor_id))
            conn.commit()
        except Exception:
            pass
        conn.close()

    def delete_dependency(self, dep_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM task_dependencies WHERE id = ?', (dep_id,))
        conn.commit()
        conn.close()

    def set_dependencies_for_task(self, project_name, task_id, predecessor_ids):
        conn = self.get_connection()
        conn.execute('DELETE FROM task_dependencies WHERE successor_id = ? AND project_name = ?',
                     (task_id, project_name))
        for pid in predecessor_ids:
            try:
                conn.execute('''INSERT OR IGNORE INTO task_dependencies
                                (project_name, predecessor_id, successor_id)
                                VALUES (?, ?, ?)''', (project_name, pid, task_id))
            except Exception:
                pass
        conn.commit()
        conn.close()

    # ── Gate baselines ────────────────────────────────────────────────────────

    def get_gate_baselines(self, project_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM gate_baselines WHERE project_name = ?', (project_name,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def set_gate_baseline(self, project_name, gate_name, gate_id, baseline_date):
        conn = self.get_connection()
        conn.execute('''INSERT OR IGNORE INTO gate_baselines
                        (project_name, gate_name, gate_id, baseline_date)
                        VALUES (?, ?, ?, ?)''', (project_name, gate_name, gate_id, baseline_date))
        conn.commit()
        conn.close()

    def get_gate_change_log(self, project_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM gate_change_log WHERE project_name = ?
                     ORDER BY changed_at DESC''', (project_name,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def log_gate_change(self, project_name, gate_name, gate_id, baseline_date,
                        old_date, new_date, days_delayed,
                        triggered_by_task_id=None, triggered_by_task_name=None,
                        impact_description=None):
        conn = self.get_connection()
        conn.execute('''INSERT INTO gate_change_log
                        (project_name, gate_name, gate_id, baseline_date, old_date, new_date,
                         days_delayed, triggered_by_task_id, triggered_by_task_name, impact_description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (project_name, gate_name, gate_id, baseline_date, old_date, new_date,
                      days_delayed, triggered_by_task_id, triggered_by_task_name, impact_description))
        conn.commit()
        conn.close()

    def get_gate_sign_offs(self, project_name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM gate_sign_offs WHERE project_name = ?', (project_name,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def set_gate_sign_off(self, project_name, gate_name, gate_id, sign_off_date, status, rework_due_date=None):
        conn = self.get_connection()
        conn.execute('''INSERT INTO gate_sign_offs
                        (project_name, gate_name, gate_id, sign_off_date, rework_due_date, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(project_name, gate_name) DO UPDATE SET
                            sign_off_date   = excluded.sign_off_date,
                            rework_due_date = excluded.rework_due_date,
                            status          = excluded.status,
                            updated_at      = CURRENT_TIMESTAMP''',
                     (project_name, gate_name, gate_id, sign_off_date, rework_due_date, status))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # RESOURCE TEAMS (owner → discipline via resource_teams.team_name)
    # Reuses existing resource_teams table from dashboard app.
    # team_name IS the discipline — no translation needed.
    # ══════════════════════════════════════════════════════════════════════════

    def get_discipline_map(self):
        """Returns {owner_name: [discipline, ...]}  (team_name = discipline)"""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT owner_name, team_name FROM resource_teams ORDER BY owner_name')
        result = {}
        for row in c.fetchall():
            result.setdefault(row['owner_name'], []).append(row['team_name'])
        conn.close()
        return result

    def get_all_discipline_map_rows(self):
        """Returns rows with id, owner_name, discipline (aliased from team_name)."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT id, owner_name, team_name AS discipline FROM resource_teams ORDER BY owner_name')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def set_discipline_map(self, mappings):
        """Replace full mapping. mappings = [{owner_name, discipline}, ...]"""
        conn = self.get_connection()
        conn.execute('DELETE FROM resource_teams')
        for m in mappings:
            conn.execute('''INSERT OR IGNORE INTO resource_teams (owner_name, team_name)
                            VALUES (?, ?)''',
                         (m['owner_name'], m['discipline']))
        conn.commit()
        conn.close()

    def add_discipline_mapping(self, owner_name, discipline):
        conn = self.get_connection()
        conn.execute('INSERT OR IGNORE INTO resource_teams (owner_name, team_name) VALUES (?, ?)',
                     (owner_name, discipline))
        conn.commit()
        conn.close()

    def delete_discipline_mapping(self, mapping_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM resource_teams WHERE id = ?', (mapping_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # RESOURCE STATUS (per project × discipline)
    # ══════════════════════════════════════════════════════════════════════════

    def get_project_resources(self, portfolio_project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM project_resources WHERE portfolio_project_id = ? ORDER BY discipline',
                  (portfolio_project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def upsert_project_resource(self, portfolio_project_id, discipline,
                                coverage=None, demand_days=None, is_manual_override=None,
                                computed_coverage=None, computed_demand_days=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT id, is_manual_override FROM project_resources WHERE portfolio_project_id=? AND discipline=?',
                  (portfolio_project_id, discipline))
        existing = c.fetchone()
        if existing:
            updates = {'updated_at': _now()}
            if computed_coverage is not None:
                updates['computed_coverage'] = computed_coverage
            if computed_demand_days is not None:
                updates['computed_demand_days'] = computed_demand_days
            # Only apply manual values if override is set or there is no existing override
            if is_manual_override is not None:
                updates['is_manual_override'] = is_manual_override
            if coverage is not None and (is_manual_override or not existing['is_manual_override']):
                updates['coverage'] = coverage
            if demand_days is not None and (is_manual_override or not existing['is_manual_override']):
                updates['demand_days'] = demand_days
            set_clauses = ', '.join(f'{k} = ?' for k in updates)
            values = list(updates.values()) + [existing['id']]
            c.execute(f'UPDATE project_resources SET {set_clauses} WHERE id = ?', values)
        else:
            c.execute('''INSERT INTO project_resources
                         (portfolio_project_id, discipline, coverage, demand_days,
                          is_manual_override, computed_coverage, computed_demand_days, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (portfolio_project_id, discipline,
                       coverage or 'N/A', demand_days or 0,
                       is_manual_override or 0,
                       computed_coverage, computed_demand_days, _now()))
        conn.commit()
        conn.close()

    def set_manual_resource_override(self, portfolio_project_id, discipline, coverage, demand_days):
        self.upsert_project_resource(portfolio_project_id, discipline,
                                     coverage=coverage, demand_days=demand_days,
                                     is_manual_override=1)

    def compute_and_store_gantt_resources(self, portfolio_project_id, project_id):
        """
        Auto-compute resource coverage + demand from gantt tasks.
        Coverage logic:
          - Fully    : all tasks for this discipline have owners assigned
          - Partially: some tasks missing owner
          - No       : discipline has tasks but zero owners
          - N/A      : no tasks touch this discipline
        Demand = working days of owner's tasks overlapping next 60 days.
        """
        discipline_map = self.get_discipline_map()   # {owner: [disciplines]}
        tasks = self.get_tasks(project_id)
        today = date.today()
        window_end = today + timedelta(days=60)

        # Reverse map: discipline → list of owners
        disc_owners = {}
        for owner, discs in discipline_map.items():
            for d in discs:
                disc_owners.setdefault(d, []).append(owner.lower())

        # Build task sets per discipline
        disc_tasks = {d: [] for d in config.DISCIPLINES}
        for t in tasks:
            if t.get('tailed_out'):
                continue
            owner = (t.get('owner') or '').strip().lower()
            for disc, owners in disc_owners.items():
                if owner in owners:
                    disc_tasks[disc].append(t)

        for discipline in config.DISCIPLINES:
            dt = disc_tasks.get(discipline, [])
            if not dt:
                computed_cov = 'N/A'
                computed_days = 0.0
            else:
                assigned = [t for t in dt if (t.get('owner') or '').strip()]
                if len(assigned) == 0:
                    computed_cov = 'No'
                elif len(assigned) == len(dt):
                    computed_cov = 'Fully'
                else:
                    computed_cov = 'Partially'

                # Demand: sum working days in next 60 days
                total_days = 0.0
                for t in assigned:
                    try:
                        ts = date.fromisoformat(t['start_date']) if t.get('start_date') else today
                        te = date.fromisoformat(t['end_date'])   if t.get('end_date')   else today
                        overlap_start = max(ts, today)
                        overlap_end   = min(te, window_end)
                        if overlap_end >= overlap_start:
                            # rough working days (exclude weekends)
                            delta = (overlap_end - overlap_start).days + 1
                            total_days += delta * 5 / 7
                    except Exception:
                        pass
                computed_days = round(total_days, 1)

            self.upsert_project_resource(
                portfolio_project_id, discipline,
                computed_coverage=computed_cov,
                computed_demand_days=computed_days,
                # Push to visible coverage only if no manual override
                coverage=computed_cov,
                demand_days=computed_days,
                is_manual_override=0,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # CARD DATA
    # ══════════════════════════════════════════════════════════════════════════

    def get_card_data(self, portfolio_project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM card_data WHERE portfolio_project_id = ?', (portfolio_project_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {}

    def upsert_card_data(self, portfolio_project_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT id FROM card_data WHERE portfolio_project_id = ?', (portfolio_project_id,))
        row = c.fetchone()
        fields = ['start_date', 'end_date', 'owner', 'description']
        if row:
            updates = {f: data[f] for f in fields if f in data}
            if updates:
                set_clauses = ', '.join(f'{k} = ?' for k in updates)
                c.execute(f'UPDATE card_data SET {set_clauses} WHERE portfolio_project_id = ?',
                          list(updates.values()) + [portfolio_project_id])
        else:
            vals = {f: data.get(f, '') for f in fields}
            c.execute('''INSERT INTO card_data (portfolio_project_id, start_date, end_date, owner, description)
                         VALUES (?, ?, ?, ?, ?)''',
                      (portfolio_project_id, vals['start_date'], vals['end_date'],
                       vals['owner'], vals['description']))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # ACTION ITEMS
    # ══════════════════════════════════════════════════════════════════════════

    def get_action_items(self, portfolio_project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM action_items WHERE portfolio_project_id = ?
                     ORDER BY sort_order, id''', (portfolio_project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def create_action_item(self, portfolio_project_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO action_items
                     (portfolio_project_id, description, owner, start_date, due_date, status, notes, sort_order)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (portfolio_project_id,
                   data.get('description', ''),
                   data.get('owner', ''),
                   data.get('start_date', ''),
                   data.get('due_date', ''),
                   data.get('status', 'Not Started'),
                   data.get('notes', ''),
                   data.get('sort_order', 0)))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def update_action_item(self, item_id, data):
        allowed = ['description', 'owner', 'start_date', 'due_date', 'status', 'notes', 'sort_order']
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return
        conn = self.get_connection()
        c = conn.cursor()
        set_clauses = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [_now(), item_id]
        c.execute(f'UPDATE action_items SET {set_clauses}, updated_at = ? WHERE id = ?', values)
        conn.commit()
        conn.close()

    def delete_action_item(self, item_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM action_items WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # RISKS
    # ══════════════════════════════════════════════════════════════════════════

    def get_risks(self, portfolio_project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM risks WHERE portfolio_project_id = ?
                     ORDER BY CASE impact WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, id''',
                  (portfolio_project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def create_risk(self, portfolio_project_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO risks (portfolio_project_id, description, impact, probability, mitigation, status)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (portfolio_project_id,
                   data.get('description', ''),
                   data.get('impact', 'Medium'),
                   data.get('probability', 'Medium'),
                   data.get('mitigation', ''),
                   data.get('status', 'Open')))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def update_risk(self, risk_id, data):
        allowed = ['description', 'impact', 'probability', 'mitigation', 'status']
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return
        conn = self.get_connection()
        c = conn.cursor()
        set_clauses = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [_now(), risk_id]
        c.execute(f'UPDATE risks SET {set_clauses}, updated_at = ? WHERE id = ?', values)
        conn.commit()
        conn.close()

    def delete_risk(self, risk_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM risks WHERE id = ?', (risk_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # CERTIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════

    def get_certifications(self, portfolio_project_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM certifications WHERE portfolio_project_id = ? ORDER BY id',
                  (portfolio_project_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def create_certification(self, portfolio_project_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO certifications
                     (portfolio_project_id, agency, cert_name, cert_type, status, expected_date, actual_date, notes)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (portfolio_project_id,
                   data.get('agency', ''),
                   data.get('cert_name', ''),
                   data.get('cert_type', ''),
                   data.get('status', 'Planned'),
                   data.get('expected_date', ''),
                   data.get('actual_date', ''),
                   data.get('notes', '')))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def update_certification(self, cert_id, data):
        allowed = ['agency', 'cert_name', 'cert_type', 'status', 'expected_date', 'actual_date', 'notes']
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return
        conn = self.get_connection()
        c = conn.cursor()
        set_clauses = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [_now(), cert_id]
        c.execute(f'UPDATE certifications SET {set_clauses}, updated_at = ? WHERE id = ?', values)
        conn.commit()
        conn.close()

    def delete_certification(self, cert_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM certifications WHERE id = ?', (cert_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # UPDATES LOG
    # ══════════════════════════════════════════════════════════════════════════

    def get_updates_log(self, portfolio_project_id, limit=50):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''SELECT * FROM updates_log WHERE portfolio_project_id = ?
                     ORDER BY created_at DESC LIMIT ?''', (portfolio_project_id, limit))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def add_update(self, portfolio_project_id, author, content):
        conn = self.get_connection()
        conn.execute('''INSERT INTO updates_log (portfolio_project_id, author, content)
                        VALUES (?, ?, ?)''', (portfolio_project_id, author, content))
        conn.commit()
        conn.close()

    def delete_update(self, update_id):
        conn = self.get_connection()
        conn.execute('DELETE FROM updates_log WHERE id = ?', (update_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # PORTFOLIO OVERVIEW (aggregated resource table)
    # ══════════════════════════════════════════════════════════════════════════

    def get_portfolio_overview(self):
        """
        Returns list of projects with resource grid for the Priority Overview table.
        Each row: project meta + {discipline: {coverage, demand_days}} for all disciplines.
        Also returns resource contention flags.
        """
        conn = self.get_connection()
        c = conn.cursor()

        # All projects sorted by priority
        c.execute('''
            SELECT pp.*, gp.id AS gantt_id
            FROM portfolio_projects pp
            LEFT JOIN projects gp ON gp.id = pp.project_id
            ORDER BY pp.priority, pp.name
        ''')
        projects = [dict(r) for r in c.fetchall()]

        # All resource rows
        c.execute('SELECT * FROM project_resources')
        all_res = {}
        for r in c.fetchall():
            all_res.setdefault(r['portfolio_project_id'], {})[r['discipline']] = dict(r)

        conn.close()

        # Build contention map: discipline → [project_ids competing in next 60 days]
        contention = {}
        for disc in config.DISCIPLINES:
            competing = []
            for p in projects:
                res = all_res.get(p['id'], {}).get(disc, {})
                cov = res.get('coverage', 'N/A')
                if cov in ('Fully', 'Partially'):
                    competing.append(p['id'])
            if len(competing) > 1:
                for pid in competing[1:]:   # first (highest priority) gets priority
                    contention.setdefault(pid, set()).add(disc)

        result = []
        for p in projects:
            resources = {}
            for disc in config.DISCIPLINES:
                res = all_res.get(p['id'], {}).get(disc, {})
                resources[disc] = {
                    'coverage':    res.get('coverage', 'N/A'),
                    'demand_days': res.get('demand_days', 0),
                    'is_override': res.get('is_manual_override', 0),
                    'computed':    res.get('computed_coverage', 'N/A'),
                    'contention':  disc in contention.get(p['id'], set()),
                }
            p['resources'] = resources
            result.append(p)

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # MONTHLY SNAPSHOTS
    # ══════════════════════════════════════════════════════════════════════════

    def save_snapshot(self, source='manual'):
        overview = self.get_portfolio_overview()
        conn = self.get_connection()
        conn.execute('''INSERT INTO monthly_snapshots (snapshot_date, source, data_json)
                        VALUES (?, ?, ?)''',
                     (_today(), source, json.dumps(overview, default=str)))
        conn.commit()
        conn.close()

    def get_snapshots(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT id, snapshot_date, source, created_at FROM monthly_snapshots ORDER BY created_at DESC')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    def get_snapshot(self, snapshot_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM monthly_snapshots WHERE id = ?', (snapshot_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    # ══════════════════════════════════════════════════════════════════════════
    # GATE TIMELINE (for home page overview)
    # ══════════════════════════════════════════════════════════════════════════

    def get_overall_gate_timeline(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT pp.id AS portfolio_project_id,
                   pp.name AS project_name,
                   pp.priority,
                   pp.leader,
                   pp.next_gate,
                   pp.planned_launch,
                   pp.management_type,
                   t.name     AS gate_name,
                   t.end_date AS gate_date,
                   gb.baseline_date,
                   gso.sign_off_date,
                   gso.status AS sign_off_status
            FROM portfolio_projects pp
            JOIN projects gp ON gp.id = pp.project_id
            JOIN tasks t ON t.project_id = gp.id AND t.milestone = 1
            LEFT JOIN gate_baselines gb ON gb.project_name = gp.name AND gb.gate_name = t.name
            LEFT JOIN gate_sign_offs gso ON gso.project_name = gp.name AND gso.gate_name = t.name
            ORDER BY pp.priority, t.end_date
        ''')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
