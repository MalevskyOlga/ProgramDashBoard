"""
Configuration settings for Overall Programs Dashboard
"""

import os
from pathlib import Path

# Server settings
SERVER_HOST = '127.0.0.1'  # localhost only
SERVER_PORT = 5003  # Different port from DashboardGeneratorWeb
DEBUG_MODE = False  # ALWAYS False for stability - prevents crashes during code changes

# Paths
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / 'database' / 'dashboards.db'
PORTFOLIO_DATABASE_PATH = BASE_DIR / 'database' / 'portfolio.db'

# Multi-division (multi-tenant) settings
# Control DB holds users, divisions and password-reset tokens (separate from division data).
CONTROL_DATABASE_PATH = BASE_DIR / 'database' / 'control.db'
# Per-division SQLite files live here (one .db per division).
DIVISIONS_DIR = BASE_DIR / 'database' / 'divisions'
# Flask session signing key. Overridden per-install by post_install.ps1 in production.
SECRET_KEY = 'dev-only-insecure-secret-change-me'
# Password-reset token lifetime (minutes).
RESET_TOKEN_TTL_MINUTES = 60

# SMTP settings for self-service password reset email.
# Emerson internal relay (INETMAIL.EMRSN.NET) - unauthenticated, no TLS, port 25.
# Leave SMTP_HOST blank to disable email; reset then falls back to admin-issued codes.
SMTP_HOST = 'INETMAIL.EMRSN.NET'
SMTP_PORT = 25
SMTP_USE_TLS = False
SMTP_USER = ''
SMTP_PASSWORD = ''
SMTP_FROM = 'OverallDashboard-noreply@emerson.com'
# Base URL used to build reset links in emails (e.g. http://server:8092).
APP_BASE_URL = 'http://localhost:5003'

# Excel file locations (not used for auto-import, but for manual export)
EXCEL_OUTPUT_FOLDER = BASE_DIR / 'exports'

# Database settings
DB_TIMEOUT = 30  # seconds

# Resource load settings
PM_LOAD_PER_PROJECT = 5       # task-equivalent weight per managed project for PM overhead
FULL_TIME_CAPACITY_HRS = 37.5 # standard full-time weekly hours (used as baseline)
OVERLOAD_TASK_THRESHOLD = 5   # concurrent tasks = overloaded at full capacity
RESOURCE_LOAD_LOOKBACK_MONTHS = 6  # exclude tasks ending more than this many months ago

# Excel parsing settings
EXCEL_PROJECT_NAME_ROW = 3
EXCEL_PROJECT_NAME_COL = 'C'
EXCEL_MANAGER_ROW = 5
EXCEL_MANAGER_COL = 'C'
EXCEL_HEADER_ROW = 10
EXCEL_DATA_START_ROW = 11

# Column mapping
EXCEL_COLUMNS = {
    'reference_id': 'A',
    'name': 'B',
    'phase': 'C',
    'owner': 'D',
    'start_date': 'E',
    'status': 'F',
    'end_date': 'G',
    'date_closed': 'H',
    'result': 'I'
}

# Ensure directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
EXCEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
CONTROL_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
DIVISIONS_DIR.mkdir(parents=True, exist_ok=True)
