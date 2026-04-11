"""
Configuration settings for Overall Programs Dashboard
"""

import os
from pathlib import Path

# Server settings
SERVER_HOST = '127.0.0.1'  # localhost only
SERVER_PORT = 5003  # Unified server port
DEBUG_MODE = False  # ALWAYS False for stability - prevents crashes during code changes

# Paths
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / 'database' / 'dashboards.db'
PORTFOLIO_DATABASE_PATH = BASE_DIR / 'database' / 'portfolio.db'

# Excel file locations (not used for auto-import, but for manual export)
EXCEL_OUTPUT_FOLDER = BASE_DIR / 'exports'

# Database settings
DB_TIMEOUT = 30  # seconds

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

# Disciplines list (must match Excel column headers)
DISCIPLINES = [
    'Proj. Mgmt', 'Optics', 'EE', 'ME', 'SW DEV', 'R&D QA',
    'Sderot Cert.', 'RSK Cert.', 'ATE', 'NPD & Main.',
    'FCT', 'RSK Ops', 'Sderot', 'RSK', 'Product Mgmt',
]

# Demand thresholds (working days in next 60 days)
DEMAND_LARGE_DAYS  = 16   # > 16 days  → Large  (≈ >120 hr)
DEMAND_MEDIUM_DAYS = 5    # 5–16 days  → Medium (≈ 40–120 hr)
                          # < 5 days   → Small  (≈ <40 hr)

# Ensure directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
EXCEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
LOG_FOLDER = BASE_DIR / 'logs'
LOG_FOLDER.mkdir(parents=True, exist_ok=True)
