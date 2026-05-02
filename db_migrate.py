"""
Applies pending SQL migrations to dashboards.db.
Each migration is a numbered .sql file in the migrations/ folder.
Applied migrations are tracked in the schema_migrations table.
"""
import sqlite3
from pathlib import Path


def run_migrations(db_path, migrations_dir=None):
    db_path = Path(db_path)
    if not db_path.exists():
        return

    if migrations_dir is None:
        migrations_dir = Path(__file__).parent / 'migrations'
    migrations_dir = Path(migrations_dir)
    if not migrations_dir.exists():
        return

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        applied = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}

        for mf in sorted(migrations_dir.glob('*.sql')):
            if mf.name in applied:
                continue
            print(f'Applying migration: {mf.name}')
            sql = mf.read_text(encoding='utf-8')
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (mf.name,))
            conn.commit()
            print(f'  OK: {mf.name}')
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        db = sys.argv[1]
    else:
        import config
        db = config.DATABASE_PATH
    run_migrations(db)
    print('Migrations complete.')
