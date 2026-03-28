"""
Configuration for the aggregate portfolio dashboard.
"""

from pathlib import Path

import config

BASE_DIR = Path(__file__).parent
AGGREGATE_HOST = "127.0.0.1"
AGGREGATE_PORT = 5002
AGGREGATE_DEBUG = False

SOURCE_DATABASE_PATH   = config.DATABASE_PATH
PORTFOLIO_DATABASE_PATH = config.PORTFOLIO_DATABASE_PATH

DB_TIMEOUT = config.DB_TIMEOUT
DEFAULT_TEAM_CAPACITY_HOURS = 37.5
FISCAL_YEAR_START_MONTH = 10
BOOTSTRAP_PROGRAMME_ID_OFFSET = 1000000
BOOTSTRAP_DIVISION_NAME = "Imported from 5001"

PORTFOLIO_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
