"""
Installer first-division setup (run by post_install.ps1).

Given a division name, ensures the portal has a first division:
- If NO divisions exist yet and an existing single-tenant dashboards.db holds data,
  migrate that data into a division with the given name (keeps its existing discipline
  names; does NOT seed the predefined defaults).
- If no existing data, create an empty division with that name (seeded with the
  predefined default disciplines, via tenancy.create_division).
- If the name is blank, do nothing (vanilla / empty install for new divisions).
- If divisions already exist, do nothing (don't disturb an established install).

Idempotent and safe to re-run.
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import tenancy


def _project_count(db_path):
    if not Path(db_path).exists():
        return 0
    try:
        c = sqlite3.connect(str(db_path))
        try:
            return c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        finally:
            c.close()
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='', help='First division name (blank = vanilla)')
    parser.add_argument('--source-db', default=str(config.DATABASE_PATH))
    args = parser.parse_args()

    tenancy.init_control_db()

    name = (args.name or '').strip()
    if not name:
        print("No first-division name provided - starting empty (vanilla).")
        return

    if tenancy.list_divisions(include_inactive=True):
        print("Divisions already exist - leaving first-division setup unchanged.")
        return

    key = tenancy.slugify(name)
    db_filename = f"{key}.db"
    dest = Path(config.DIVISIONS_DIR) / db_filename
    src = Path(args.source_db)

    if _project_count(src) > 0:
        # Migrate existing single-tenant data into the new division.
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup = src.with_suffix(src.suffix + '.preseed.bak')
        if not backup.exists():
            shutil.copy2(src, backup)
            print(f"Backed up source DB -> {backup}")
        shutil.copy2(src, dest)
        tenancy.create_division_db(dest)  # ensure schema + migrations (disciplines from data)
        conn = tenancy.get_control_conn()
        try:
            conn.execute(
                "INSERT INTO divisions (key, name, db_filename) VALUES (?, ?, ?)",
                (key, name, db_filename))
            conn.commit()
        finally:
            conn.close()
        tenancy._division_db_cache.pop(key, None)
        print(f"Migrated existing data into division '{name}' ({key}).")
    else:
        # No existing data: create an empty division (seeds predefined disciplines).
        tenancy.create_division(name)
        print(f"Created empty division '{name}' ({key}).")


if __name__ == '__main__':
    main()
