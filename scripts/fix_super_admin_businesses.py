"""
Script to unlink super_admin users from all businesses.
Super admin should not be linked to any business - they are universal.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text
from database.postgres_optimized import get_db
from store.repositories.user_business import UserBusinessRepository


def fix_super_admin_businesses():
    """Unlink all super_admin users from businesses."""
    db: Session = next(get_db())
    user_business_repo = UserBusinessRepository(db)
    
    try:
        # Find all super_admin users using raw SQL to avoid model import issues
        result = db.execute(
            text("SELECT id, full_name, active_business_id FROM users WHERE role = 'super_admin'")
        )
        super_admins = result.fetchall()
        
        if not super_admins:
            print("No super_admin users found.")
            return
        
        print(f"Found {len(super_admins)} super_admin user(s).")
        
        for admin_row in super_admins:
            admin_id = admin_row[0]
            admin_name = admin_row[1]
            active_business_id = admin_row[2]
            
            # Check if linked to any businesses
            business_ids = user_business_repo.get_business_ids_for_user(admin_id)
            
            if business_ids:
                print(f"Super admin {admin_id} ({admin_name}) is linked to {len(business_ids)} business(es): {business_ids}")
                # Unlink from all businesses
                user_business_repo.unlink_user_from_all_businesses(admin_id)
                db.commit()
                print(f"  ✓ Unlinked super admin {admin_id} from all businesses.")
            else:
                print(f"Super admin {admin_id} ({admin_name}) is not linked to any businesses. ✓")
            
            # Also clear active_business_id for super_admins
            if active_business_id:
                print(f"Super admin {admin_id} has active_business_id={active_business_id}, clearing it...")
                db.execute(
                    text("UPDATE users SET active_business_id = NULL WHERE id = :user_id"),
                    {"user_id": admin_id}
                )
                db.commit()
                print(f"  ✓ Cleared active_business_id for super admin {admin_id}.")
        
        print("\n✓ All super_admin users have been unlinked from businesses.")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting super_admin business cleanup...")
    fix_super_admin_businesses()
    print("Done!")

