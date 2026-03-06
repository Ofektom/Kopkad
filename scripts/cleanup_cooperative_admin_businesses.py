"""
Cleanup script: removes all user_business entries for the cooperative_admin.

The cooperative_admin is the agent (owner) of COOPX1, so their business
relationship is via Business.agent_id — they do NOT need user_business entries.
Removing these prevents them from appearing in multiple businesses on the sidebar.

Run from the savings-system directory:
    python -m scripts.cleanup_cooperative_admin_businesses
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models.business
import models.payments
import models.savings
import models.savings_group
import models.expenses
import models.deposits
import models.notifications
import models.financial_advisor
import models.token
import models.settings

from database.postgres_optimized import SessionLocal
from models.user import User
from models.user_business import user_business

COOP_ADMIN_USERNAME = "08000000015"


def run():
    db = SessionLocal()
    try:
        coop_admin = db.query(User).filter(User.username == COOP_ADMIN_USERNAME).first()
        if not coop_admin:
            print(f"ERROR: Cooperative Admin (username='{COOP_ADMIN_USERNAME}') not found.")
            return

        result = db.execute(
            user_business.delete().where(user_business.c.user_id == coop_admin.id)
        )
        removed = result.rowcount
        db.commit()

        print(
            f"Removed {removed} user_business entry/entries for cooperative_admin "
            f"(id={coop_admin.id}, username={COOP_ADMIN_USERNAME}).\n"
            f"Their business relationship is now solely via Business.agent_id (COOPX1)."
        )
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
