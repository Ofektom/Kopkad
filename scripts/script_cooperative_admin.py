"""
One-time seed script: creates the Cooperative Admin user.

Run manually from the savings-system directory:
    python -m scripts.script_cooperative_admin

Prerequisites:
- The database must already have the 'cooperative_admin' enum value
  (run migrate_add_cooperative_admin_role.sql first).
- The central business (unique_code='CEN123') must already exist.
"""

import sys
import os

# Allow running from the savings-system directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.sql import insert
from datetime import datetime, timezone

from database.postgres_optimized import SessionLocal

# Import all models so SQLAlchemy can resolve all relationships before querying
import models.payments
import models.savings
import models.savings_group
import models.expenses
import models.deposits
import models.notifications
import models.financial_advisor
import models.token

from models.user import User, Role, Permission, user_permissions
from models.business import Business
from models.user_business import user_business
from models.settings import Settings, NotificationMethod
from utils.auth import hash_password


PHONE_NUMBER = "2348000000015"
USERNAME = "08000000015"
PIN = "54321"
FULL_NAME = "Cooperative Admin"
EMAIL = "cooperative.admin@kopkad.com"
CENTRAL_BUSINESS_CODE = "CEN123"


def seed_cooperative_admin():
    db = SessionLocal()
    try:
        # Idempotency check
        existing = db.query(User).filter(User.username == USERNAME).first()
        if existing:
            print(f"Cooperative Admin already exists (id={existing.id}). Skipping.")
            return

        # Find the central business
        central_business = (
            db.query(Business)
            .filter(Business.unique_code == CENTRAL_BUSINESS_CODE)
            .first()
        )
        if not central_business:
            print(
                f"ERROR: Central business with code '{CENTRAL_BUSINESS_CODE}' not found. "
                "Create it first before running this script."
            )
            return

        # Create the cooperative admin user
        coop_admin = User(
            full_name=FULL_NAME,
            phone_number=PHONE_NUMBER,
            email=EMAIL,
            username=USERNAME,
            pin=hash_password(PIN),
            role=Role.COOPERATIVE_ADMIN,
            is_active=True,
            created_by=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(coop_admin)
        db.commit()
        db.refresh(coop_admin)

        # Self-reference created_by
        coop_admin.created_by = coop_admin.id
        db.commit()

        # Link to the central business
        db.execute(
            user_business.insert().values(
                user_id=coop_admin.id,
                business_id=central_business.id,
            )
        )
        coop_admin.active_business_id = central_business.id
        db.commit()

        # Create user settings
        settings = db.query(Settings).filter(Settings.user_id == coop_admin.id).first()
        if not settings:
            settings = Settings(
                user_id=coop_admin.id,
                notification_method=NotificationMethod.BOTH,
                created_by=coop_admin.id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(settings)
            db.commit()

        # Assign permissions
        perms_to_add = [
            {"user_id": coop_admin.id, "permission": Permission.CREATE_CUSTOMER},
            {"user_id": coop_admin.id, "permission": Permission.VIEW_OWN_CONTRIBUTIONS},
        ]
        db.execute(insert(user_permissions).values(perms_to_add))
        db.commit()

        print(
            f"Cooperative Admin seeded successfully:\n"
            f"  ID       : {coop_admin.id}\n"
            f"  Username : {USERNAME}\n"
            f"  Phone    : {PHONE_NUMBER}\n"
            f"  Business : {central_business.name} (code={CENTRAL_BUSINESS_CODE})\n"
        )
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_cooperative_admin()
