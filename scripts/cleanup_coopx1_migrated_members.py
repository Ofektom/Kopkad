"""
Cleanup script: removes the 3 incorrectly migrated members from COOPX1's user_business.

The seed_central_cooperative.py step 4 migrated ALL cooperative members system-wide
into COOPX1, but only Ofofon Test and Fonfon Tommy genuinely belong to the Central
Cooperative. The other 3 belong to the external cooperative (business 4).

Members to REMOVE from COOPX1:
  - Invited Member   (phone: 08064774837)
  - Goodnews Udotong (phone: 08149023271)
  - Nyakno Ofofonono (phone: 09026279856)

Run from the savings-system directory:
    python -m scripts.cleanup_coopx1_migrated_members
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
from models.business import Business
from models.user_business import user_business

CENTRAL_COOP_CODE = "COOPX1"

# Phone numbers of the 3 members that do NOT belong to COOPX1
PHONES_TO_REMOVE = [
    "08064774837",  # Invited Member
    "08149023271",  # Goodnews Udotong
    "09026279856",  # Nyakno Ofofonono
]


def run():
    db = SessionLocal()
    try:
        central_coop = (
            db.query(Business)
            .filter(Business.unique_code == CENTRAL_COOP_CODE)
            .first()
        )
        if not central_coop:
            print(f"ERROR: Central Cooperative (code='{CENTRAL_COOP_CODE}') not found.")
            return

        print(f"Central Cooperative: id={central_coop.id}, name={central_coop.name}\n")

        removed = 0
        not_found = 0

        for phone in PHONES_TO_REMOVE:
            user = db.query(User).filter(User.username == phone).first()
            if not user:
                # Try by phone_number field (stored with country code prefix)
                normalized = "234" + phone[1:] if phone.startswith("0") else phone
                user = db.query(User).filter(User.phone_number == normalized).first()
            if not user:
                print(f"  SKIP: No user found for phone {phone}")
                not_found += 1
                continue

            result = db.execute(
                user_business.delete().where(
                    (user_business.c.user_id == user.id)
                    & (user_business.c.business_id == central_coop.id)
                )
            )
            count = result.rowcount
            if count:
                print(f"  Removed {count} user_business entry for {user.full_name} (id={user.id}, phone={phone}) from COOPX1.")
                removed += 1
            else:
                print(f"  SKIP: {user.full_name} (id={user.id}) was not linked to COOPX1.")

        db.commit()
        print(
            f"\nDone. Removed {removed} member(s) from COOPX1's user_business. "
            f"{not_found} user(s) not found."
        )
        print("Their cooperative_status and other business memberships are unchanged.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
