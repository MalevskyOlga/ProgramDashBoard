"""
SQLite helpers for the aggregate portfolio dashboard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

import aggregate_config as aggregate_config


def _sqlite_file_uri(path: Path, *, read_only: bool) -> str:
    quoted_path = quote(str(path.resolve()).replace("\\", "/"), safe="/:")
    mode = "ro" if read_only else "rwc"
    return f"file:{quoted_path}?mode={mode}"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        _sqlite_file_uri(aggregate_config.PORTFOLIO_DATABASE_PATH, read_only=False),
        timeout=aggregate_config.DB_TIMEOUT,
        uri=True,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {aggregate_config.DB_TIMEOUT * 1000}")
    conn.execute("PRAGMA journal_mode = WAL")

    source_uri = _sqlite_file_uri(aggregate_config.SOURCE_DATABASE_PATH, read_only=True)
    escaped_source_uri = source_uri.replace("'", "''")
    conn.execute(f"ATTACH DATABASE '{escaped_source_uri}' AS src")
    return conn


def initialize_portfolio_database() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS programmes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            division TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'hold', 'complete'))
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS programme_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programme_id INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
            project_name TEXT NOT NULL UNIQUE,
            display_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            owner_name TEXT NOT NULL UNIQUE,
            capacity_hrs_per_week REAL NOT NULL DEFAULT 37.5
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS programme_escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programme_id INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
            project_name TEXT,
            gate_name TEXT,
            issue TEXT NOT NULL,
            owner TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'A' CHECK (severity IN ('R', 'A')),
            raised_date TEXT NOT NULL,
            target_decision_date TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS milestone_baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            task_name TEXT NOT NULL,
            baseline_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_name, task_name)
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_programme_projects_programme_id ON programme_projects(programme_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_resource_teams_team_name ON resource_teams(team_name)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_milestone_baselines_project ON milestone_baselines(project_name)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_programme_escalations_programme_id ON programme_escalations(programme_id)"
    )

    conn.commit()
    conn.close()
