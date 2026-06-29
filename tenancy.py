"""
Tenancy layer for the multi-division portal.

Holds the *control* database (users, divisions, password-reset tokens) and resolves
the active division's data database per logged-in user. Division data lives in one
SQLite file per division under config.DIVISIONS_DIR; each is created from the same
"vanilla" schema as the original single-tenant database (DatabaseManager.initialize_database).

This module is deliberately independent of Flask request state except for the small
current_division_key() helper, so it can also be driven by scripts (e.g. seeding).
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

import config
from database_manager import DatabaseManager

try:
    from db_migrate import run_migrations as _run_migrations
except Exception:  # pragma: no cover - migrations are optional
    _run_migrations = None


# Cache of DatabaseManager instances keyed by division key. DatabaseManager opens a
# fresh connection per operation, so a single instance per division is safe to reuse.
_division_db_cache = {}

# Predefined disciplines seeded into NEWLY created divisions only (via create_division).
# Existing divisions (e.g. Flame & Gas) are never seeded with these — they keep their own
# discipline names (imported from their data by migrations/001_disciplines.sql).
DEFAULT_DISCIPLINES = [
    'Electrical Engineer',
    'Mechanical Engineer',
    'SW Engineer',
    'System Engineer',
    'Product Manager',
    'Project Manager',
    'Electro Optical Engineer',
    'Manufacturing Engineer',
    'Planning',
    'Purchasing',
]


def seed_default_disciplines(db_path):
    """Insert the predefined discipline list into a division DB (idempotent)."""
    conn = sqlite3.connect(str(db_path), timeout=config.DB_TIMEOUT)
    try:
        for i, name in enumerate(DEFAULT_DISCIPLINES, start=1):
            conn.execute(
                "INSERT OR IGNORE INTO disciplines (name, sort_order) VALUES (?, ?)",
                (name, i))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Control database
# ---------------------------------------------------------------------------

def get_control_conn():
    conn = sqlite3.connect(str(config.CONTROL_DATABASE_PATH), timeout=config.DB_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_control_db():
    """Create the control schema if it does not already exist."""
    conn = get_control_conn()
    try:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS divisions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key         TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                db_filename TEXT NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                username             TEXT UNIQUE NOT NULL,
                email                TEXT UNIQUE,
                password_hash        TEXT NOT NULL,
                role                 TEXT NOT NULL DEFAULT 'user',
                division_id          INTEGER,
                is_active            INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (division_id) REFERENCES divisions(id)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                token_hash TEXT,
                code       TEXT,
                expires_at TEXT NOT NULL,
                used_at    TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Divisions
# ---------------------------------------------------------------------------

def _division_db_path(db_filename):
    return Path(config.DIVISIONS_DIR) / db_filename


def create_division_db(db_path):
    """Create a fresh (vanilla) division database with the full schema, no data."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    DatabaseManager(str(db_path)).initialize_database()
    if _run_migrations is not None:
        try:
            _run_migrations(str(db_path))
        except Exception as exc:  # pragma: no cover
            print(f"Warning: migrations failed for {db_path}: {exc}")


def list_divisions(include_inactive=False):
    conn = get_control_conn()
    try:
        sql = "SELECT * FROM divisions"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY name COLLATE NOCASE"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_division_by_key(key):
    conn = get_control_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_division_by_id(division_id):
    conn = get_control_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def slugify(name):
    slug = ''.join(c.lower() if c.isalnum() else '_' for c in name.strip())
    while '__' in slug:
        slug = slug.replace('__', '_')
    return slug.strip('_') or 'division'


def create_division(name, key=None, db_filename=None):
    """Register a new division and create its (empty) data database."""
    key = key or slugify(name)
    db_filename = db_filename or f"{key}.db"
    conn = get_control_conn()
    try:
        conn.execute(
            "INSERT INTO divisions (key, name, db_filename) VALUES (?, ?, ?)",
            (key, name, db_filename),
        )
        conn.commit()
    finally:
        conn.close()
    div_db = _division_db_path(db_filename)
    create_division_db(div_db)
    # Newly created divisions start with the predefined discipline list.
    seed_default_disciplines(div_db)
    _division_db_cache.pop(key, None)
    return get_division_by_key(key)


def set_division_active(division_id, is_active):
    conn = get_control_conn()
    try:
        conn.execute("UPDATE divisions SET is_active = ? WHERE id = ?",
                     (1 if is_active else 0, division_id))
        conn.commit()
    finally:
        conn.close()


def get_division_db(division_key):
    """Return a cached DatabaseManager for the division. None if no/unknown division."""
    if not division_key:
        return None
    if division_key in _division_db_cache:
        return _division_db_cache[division_key]
    division = get_division_by_key(division_key)
    if not division:
        return None
    db_path = _division_db_path(division['db_filename'])
    if not db_path.exists():
        create_division_db(db_path)
    else:
        # Ensure schema + migrations are current on existing division DBs (idempotent).
        # Runs once per division per process thanks to the cache below.
        DatabaseManager(str(db_path)).initialize_database()
        if _run_migrations is not None:
            try:
                _run_migrations(str(db_path))
            except Exception as exc:  # pragma: no cover
                print(f"Warning: migrations failed for {db_path}: {exc}")
    dbm = DatabaseManager(str(db_path))
    _division_db_cache[division_key] = dbm
    return dbm


def current_division_key():
    """Active division for the current request, read from the Flask session."""
    from flask import session
    if session.get('role') == 'superadmin':
        return session.get('active_division')
    return session.get('division')


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _user_row_to_dict(row):
    return dict(row) if row else None


def create_user(username, password, email=None, role='user', division_id=None,
                must_change_password=False):
    conn = get_control_conn()
    try:
        conn.execute(
            """INSERT INTO users (username, email, password_hash, role, division_id,
                                  must_change_password)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, email, generate_password_hash(password), role, division_id,
             1 if must_change_password else 0),
        )
        conn.commit()
        return get_user_by_username(username)
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_control_conn()
    try:
        # Case-insensitive so login/duplicate checks aren't tripped by casing.
        row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                           ((username or '').strip(),)).fetchone()
        return _user_row_to_dict(row)
    finally:
        conn.close()


def get_user_by_email(email):
    if not email:
        return None
    conn = get_control_conn()
    try:
        # Case-insensitive: users naturally type their email with different casing
        # (e.g. Outlook shows "Olga.Malevsky@Emerson.com" but it's stored lowercase).
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE AND is_active = 1",
            (email.strip(),)).fetchone()
        return _user_row_to_dict(row)
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_control_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _user_row_to_dict(row)
    finally:
        conn.close()


def list_users():
    conn = get_control_conn()
    try:
        rows = conn.execute(
            """SELECT u.*, d.name AS division_name, d.key AS division_key
               FROM users u LEFT JOIN divisions d ON u.division_id = d.id
               ORDER BY u.username COLLATE NOCASE"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def authenticate(username, password):
    """Return the user dict on success, else None.

    Accepts either the username or the account email as the identifier. Password
    reset is keyed on email, so users naturally try their email at login after a
    reset; treat both the same. Emails are unique (enforced at user creation)."""
    identifier = (username or '').strip()
    user = get_user_by_username(identifier)
    if not user and '@' in identifier:
        user = get_user_by_email(identifier)
    if not user or not user['is_active']:
        return None
    if not check_password_hash(user['password_hash'], password):
        return None
    return user


def set_password(user_id, new_password, clear_must_change=True):
    conn = get_control_conn()
    try:
        if clear_must_change:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (generate_password_hash(new_password), user_id))
        else:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(new_password), user_id))
        conn.commit()
    finally:
        conn.close()


def update_user(user_id, email=None, role=None, division_id=None, is_active=None):
    fields, params = [], []
    if email is not None:
        fields.append("email = ?"); params.append(email or None)
    if role is not None:
        fields.append("role = ?"); params.append(role)
    if division_id is not None:
        # division_id may legitimately be set to NULL (superadmin / unassigned)
        fields.append("division_id = ?"); params.append(division_id or None)
    if is_active is not None:
        fields.append("is_active = ?"); params.append(1 if is_active else 0)
    if not fields:
        return
    params.append(user_id)
    conn = get_control_conn()
    try:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Password resets
# ---------------------------------------------------------------------------

def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _now():
    return datetime.now()


def create_reset(user_id):
    """Create a reset record. Returns (raw_token, code). Token is for emailed links;
    code is the short value a super admin can hand a user when email is unavailable."""
    raw_token = secrets.token_urlsafe(32)
    code = ''.join(secrets.choice('0123456789') for _ in range(6))
    expires_at = (_now() + timedelta(minutes=config.RESET_TOKEN_TTL_MINUTES))
    conn = get_control_conn()
    try:
        # Invalidate prior unused tokens for this user.
        conn.execute("UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL",
                     (_now().isoformat(timespec='seconds'), user_id))
        conn.execute(
            """INSERT INTO password_resets (user_id, token_hash, code, expires_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, _hash_token(raw_token), code, expires_at.isoformat(timespec='seconds')))
        conn.commit()
    finally:
        conn.close()
    return raw_token, code


def _valid_reset_row(row):
    if not row or row['used_at']:
        return False
    try:
        return datetime.fromisoformat(row['expires_at']) >= _now()
    except Exception:
        return False


def verify_reset(token=None, code=None):
    """Return the matching unused, unexpired reset row (with user_id) or None."""
    conn = get_control_conn()
    try:
        if token:
            row = conn.execute(
                "SELECT * FROM password_resets WHERE token_hash = ?",
                (_hash_token(token),)).fetchone()
        elif code:
            row = conn.execute(
                """SELECT * FROM password_resets WHERE code = ? AND used_at IS NULL
                   ORDER BY id DESC LIMIT 1""", (code,)).fetchone()
        else:
            return None
        return dict(row) if _valid_reset_row(row) else None
    finally:
        conn.close()


def consume_reset(reset_id):
    conn = get_control_conn()
    try:
        conn.execute("UPDATE password_resets SET used_at = ? WHERE id = ?",
                     (_now().isoformat(timespec='seconds'), reset_id))
        conn.commit()
    finally:
        conn.close()
