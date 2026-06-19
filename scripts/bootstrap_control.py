"""
Bootstrap the control database for a fresh (vanilla) install.

Creates the control schema and, if no users exist yet, a single super-admin.
Idempotent: if any user already exists it leaves the control DB untouched (so an
upgrade never resets credentials). Prints the super-admin's temporary password so
the installer can surface it to the operator.

Usage (run with the install venv python):
    python scripts/bootstrap_control.py --admin-username admin --admin-email "" [--admin-password X]
"""

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tenancy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--admin-username', default='admin')
    parser.add_argument('--admin-email', default='')
    parser.add_argument('--admin-password', default=None)
    args = parser.parse_args()

    tenancy.init_control_db()

    # Only seed a super-admin on a truly fresh control DB.
    conn = tenancy.get_control_conn()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()

    admin_email = (args.admin_email or '').strip() or None

    if user_count > 0:
        print("Control DB already has users - leaving credentials unchanged.")
        # Upgrade backfill: a super-admin created before email was mandatory cannot
        # self-serve a password reset. If an admin email was supplied and any active
        # super-admin still lacks one, fill it in (don't clobber existing emails).
        if admin_email:
            conn = tenancy.get_control_conn()
            try:
                cur = conn.execute(
                    """UPDATE users SET email = ?
                       WHERE role = 'superadmin' AND is_active = 1
                         AND (email IS NULL OR email = '')""",
                    (admin_email,))
                conn.commit()
                if cur.rowcount:
                    print(f"Backfilled email for {cur.rowcount} super-admin(s): {admin_email}")
            finally:
                conn.close()
        return

    password = args.admin_password or ('Tmp-' + secrets.token_urlsafe(9))
    tenancy.create_user(args.admin_username, password,
                        email=admin_email, role='superadmin',
                        division_id=None, must_change_password=True)
    print("=" * 60)
    print("Created initial super-admin account")
    print(f"  Username : {args.admin_username}")
    print(f"  Password : {password}")
    print("  (must be changed at first sign-in)")
    print("=" * 60)


if __name__ == '__main__':
    main()
