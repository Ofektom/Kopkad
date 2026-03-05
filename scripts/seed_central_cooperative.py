"""
One-time seed script: creates the Central Cooperative business, links the
Cooperative Admin to it, and migrates all existing cooperative members and
savings groups.

Run manually from the savings-system directory:
    python -m scripts.seed_central_cooperative

What this does:
1. Creates a new Business record (unique_code='COOPX1', business_type=cooperative)
2. Sets cooperative_admin as the owner (agent_id) of the Central Cooperative
3. Re-links cooperative_admin to COOPX1 and sets it as their active_business_id
4. Migrates all existing users with cooperative_status in ('requested', 'approved')
   from CEN123 into COOPX1 (adds them to user_business for COOPX1)
5. Migrates all savings groups owned by the cooperative_admin from CEN123 to COOPX1
   by updating their business_id

Prerequisites:
- The Cooperative Admin user must already exist (run script_cooperative_admin.py first).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models.payments
import models.savings
import models.savings_group
import models.expenses
import models.deposits
import models.notifications
import models.financial_advisor
import models.token
import models.settings

from datetime import datetime, timezone
from database.postgres_optimized import SessionLocal
from models.business import Business, BusinessType
from models.user import User, Role
from models.user_business import user_business
from models.savings_group import SavingsGroup


COOP_ADMIN_USERNAME = "08000000015"
CENTRAL_COOP_CODE = "COOPX1"
CENTRAL_COOP_NAME = "Central Cooperative"


def _is_linked(db, user_id: int, business_id: int) -> bool:
    return db.execute(
        user_business.select().where(
            (user_business.c.user_id == user_id)
            & (user_business.c.business_id == business_id)
        )
    ).first() is not None


def seed():
    db = SessionLocal()
    try:
        # 1. Find the cooperative admin
        coop_admin = (
            db.query(User)
            .filter(User.username == COOP_ADMIN_USERNAME)
            .first()
        )
        if not coop_admin:
            print(
                f"ERROR: Cooperative Admin (username='{COOP_ADMIN_USERNAME}') not found. "
                "Run script_cooperative_admin.py first."
            )
            return

        # 2. Create Central Cooperative (idempotent)
        central_coop = (
            db.query(Business)
            .filter(Business.unique_code == CENTRAL_COOP_CODE)
            .first()
        )
        if central_coop:
            print(f"Central Cooperative already exists (id={central_coop.id}). Skipping creation.")
        else:
            central_coop = Business(
                name=CENTRAL_COOP_NAME,
                agent_id=coop_admin.id,
                address=None,
                unique_code=CENTRAL_COOP_CODE,
                is_default=True,
                business_type=BusinessType.COOPERATIVE,
                created_by=coop_admin.id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(central_coop)
            db.commit()
            db.refresh(central_coop)
            print(
                f"Created Central Cooperative:\n"
                f"  ID          : {central_coop.id}\n"
                f"  Name        : {central_coop.name}\n"
                f"  Unique Code : {central_coop.unique_code}\n"
                f"  Type        : {central_coop.business_type}\n"
            )

        # 3. Link cooperative_admin to COOPX1 and update their active business
        if not _is_linked(db, coop_admin.id, central_coop.id):
            db.execute(
                user_business.insert().values(
                    user_id=coop_admin.id,
                    business_id=central_coop.id,
                )
            )
            print(f"Linked cooperative_admin (id={coop_admin.id}) to Central Cooperative.")
        coop_admin.active_business_id = central_coop.id
        db.commit()
        print(f"Set cooperative_admin active_business_id → {central_coop.id}.")

        # 4. Migrate existing cooperative members (requested / approved) into COOPX1
        coop_members = (
            db.query(User)
            .filter(User.cooperative_status.in_(["requested", "approved"]))
            .filter(User.id != coop_admin.id)
            .all()
        )

        migrated = 0
        already = 0
        for member in coop_members:
            if _is_linked(db, member.id, central_coop.id):
                already += 1
            else:
                db.execute(
                    user_business.insert().values(
                        user_id=member.id,
                        business_id=central_coop.id,
                    )
                )
                migrated += 1

        db.commit()
        print(
            f"\nCooperative member migration:\n"
            f"  Total found   : {len(coop_members)}\n"
            f"  Migrated      : {migrated}\n"
            f"  Already linked: {already}\n"
        )

        # 5. Migrate savings groups owned by cooperative_admin from CEN123 → COOPX1
        cen_business = (
            db.query(Business)
            .filter(Business.unique_code == "CEN123")
            .first()
        )
        groups_migrated = 0
        groups_already = 0
        if cen_business:
            groups = (
                db.query(SavingsGroup)
                .filter(
                    SavingsGroup.business_id == cen_business.id,
                    SavingsGroup.created_by == coop_admin.id,
                )
                .all()
            )
            for g in groups:
                if g.business_id == central_coop.id:
                    groups_already += 1
                else:
                    g.business_id = central_coop.id
                    groups_migrated += 1
            db.commit()

        print(
            f"Savings group migration:\n"
            f"  Total found   : {groups_migrated + groups_already}\n"
            f"  Migrated      : {groups_migrated}\n"
            f"  Already linked: {groups_already}\n"
        )

        print("Done.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
