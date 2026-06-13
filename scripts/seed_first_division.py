"""
One-time seed: turn the existing single-tenant data into division #1 and create
the first super-admin. Safe to re-run (idempotent): it won't duplicate the division
or overwrite an existing division DB or user.

Usage:
    python scripts/seed_first_division.py \
        --division "Flame & Gas" \
        --admin-username olga \
        --admin-email olga.malevsky@emerson.com \
        --admin-password "<temp password>"

If --admin-password is omitted a random temporary one is generated and printed.
The super-admin is created with must_change_password=1, so they set their own
password on first sign-in.
"""

import argparse
import secrets
import shutil
import sys
from pathlib import Path

# Make project root importable when run as scripts/seed_first_division.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import tenancy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--division', default='Flame & Gas')
    parser.add_argument('--key', default='flame_gas')
    parser.add_argument('--admin-username', default='olga')
    parser.add_argument('--admin-email', default='olga.malevsky@emerson.com')
    parser.add_argument('--admin-password', default=None)
    parser.add_argument('--source-db', default=str(config.DATABASE_PATH))
    args = parser.parse_args()

    tenancy.init_control_db()

    # 1. Create the division record + its data DB from the existing dashboards.db.
    db_filename = f"{args.key}.db"
    dest = Path(config.DIVISIONS_DIR) / db_filename
    existing = tenancy.get_division_by_key(args.key)

    if existing:
        print(f"Division '{args.key}' already exists - leaving it as is.")
    else:
        source = Path(args.source_db)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            backup = source.with_suffix(source.suffix + '.preseed.bak')
            if not backup.exists():
                shutil.copy2(source, backup)
                print(f"Backed up source DB -> {backup}")
            shutil.copy2(source, dest)
            print(f"Copied existing data {source} -> {dest}")
            # Ensure schema/migrations are current on the new division DB.
            tenancy.create_division_db(dest)
        else:
            print(f"Source DB {source} not found - creating an empty division DB.")
            tenancy.create_division_db(dest)

        # Register the division row (points at the file we just created).
        conn = tenancy.get_control_conn()
        try:
            conn.execute(
                "INSERT INTO divisions (key, name, db_filename) VALUES (?, ?, ?)",
                (args.key, args.division, db_filename))
            conn.commit()
        finally:
            conn.close()
        print(f"Registered division: {args.division} ({args.key})")

    # 2. Create the super-admin (if not present).
    if tenancy.get_user_by_username(args.admin_username):
        print(f"User '{args.admin_username}' already exists - leaving it as is.")
    else:
        password = args.admin_password or ('Tmp-' + secrets.token_urlsafe(8))
        tenancy.create_user(args.admin_username, password,
                            email=args.admin_email, role='superadmin',
                            division_id=None, must_change_password=True)
        print("-" * 60)
        print(f"Created super-admin: {args.admin_username}")
        print(f"Temporary password : {password}")
        print("They will be required to set a new password at first sign-in.")
        print("-" * 60)

    print("Seed complete.")


if __name__ == '__main__':
    main()
