"""Provision government officials (administrative use only).

Creates a government_users row (or resets the password of an existing one)
using the application's secure password hashing. There is no public
signup path to this table and no email/OTP involved.

Password sourcing (never hardcoded, never logged):
  1. --password flag, or
  2. GOV_PROVISION_PASSWORD environment variable, or
  3. interactive getpass prompt.

Usage:
  python scripts/provision_government_user.py --employee-id GOV-0001
      --full-name "Review Officer" --designation "Review Officer"
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.government import GovernmentUser  # noqa: E402


def _resolve_password(flag_value: str | None) -> str:
    if flag_value:
        return flag_value
    env_value = os.environ.get("GOV_PROVISION_PASSWORD", "")
    if env_value:
        return env_value
    return getpass.getpass("Official password: ")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision a government official (employee_id + password)."
    )
    parser.add_argument("--employee-id", required=True)
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--designation", default=None)
    parser.add_argument("--inactive", action="store_true")
    parser.add_argument("--reset-password", action="store_true",
                        help="Reset password of an existing employee_id.")
    parser.add_argument("--password", default=None,
                        help="Password (prefer env GOV_PROVISION_PASSWORD "
                             "or interactive prompt).")
    args = parser.parse_args()

    employee_id = args.employee_id.strip()
    if not employee_id or len(employee_id) > 64:
        print("error: employee_id must be 1-64 characters.", flush=True)
        return 2
    password = _resolve_password(args.password)
    if len(password) < 8:
        print("error: password must be at least 8 characters.", flush=True)
        return 2

    session = SessionLocal()
    try:
        existing = (
            session.query(GovernmentUser)
            .filter_by(employee_id=employee_id)
            .first()
        )
        if existing is not None and not args.reset_password:
            print("error: employee_id already provisioned "
                  "(use --reset-password to rotate).", flush=True)
            return 1
        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.is_active = not args.inactive
            session.add(existing)
            session.commit()
            print(f"password rotated for {employee_id}", flush=True)
            return 0
        session.add(GovernmentUser(
            employee_id=employee_id,
            password_hash=hash_password(password),
            full_name=args.full_name,
            designation=args.designation,
            is_active=not args.inactive,
        ))
        session.commit()
        print(f"provisioned {employee_id}", flush=True)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
