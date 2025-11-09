from sqlalchemy.orm import Session
from models.user import User, Role, Permission, user_permissions
from models.business import Business
from models.user_business import user_business
from models.settings import Settings, NotificationMethod
from utils.auth import hash_password
from sqlalchemy.sql import insert
from datetime import datetime, timezone


def bootstrap_super_admin(db: Session):
    """Bootstrap the SUPER_ADMIN user and default business if not already seeded."""
    print("Starting SUPER_ADMIN bootstrap process...")

    # Check if SUPER_ADMIN already exists
    super_admin = db.query(User).filter(User.role == Role.SUPER_ADMIN).first()
    if super_admin:
        print("SUPER_ADMIN already seeded. Skipping bootstrap.")
        return

    # Create SUPER_ADMIN user
    super_admin = User(
        full_name="Super Admin",
        phone_number="2348000000000",
        email="superadmin@example.com",
        username="08000000000",
        pin=hash_password("51985"),
        role=Role.SUPER_ADMIN,
        is_active=True,
        created_by=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(super_admin)
    db.commit()
    db.refresh(super_admin)

    # Update created_by to self-reference
    super_admin.created_by = super_admin.id
    db.commit()

    # Note: SUPER_ADMIN should NOT be linked to any business
    # They are universal and can manage all businesses

    # Create settings for SUPER_ADMIN
    settings = db.query(Settings).filter(Settings.user_id == super_admin.id).first()
    if not settings:
        settings = Settings(
            user_id=super_admin.id,
            notification_method=NotificationMethod.BOTH,
            created_by=super_admin.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(settings)
        db.commit()

    # Assign permissions to SUPER_ADMIN
    existing_perms = {
        row.permission
        for row in db.query(user_permissions)
        .filter(user_permissions.c.user_id == super_admin.id)
        .all()
    }
    required_perms = {
        Permission.CREATE_ADMIN,
        Permission.CREATE_AGENT,
        Permission.ASSIGN_BUSINESS,
        Permission.CREATE_CUSTOMER,  # Add new permission here
    }
    if not existing_perms.issuperset(required_perms):
        permissions_to_add = [
            {"user_id": super_admin.id, "permission": perm}
            for perm in required_perms - existing_perms
        ]
        db.execute(insert(user_permissions).values(permissions_to_add))
        db.commit()

    print(
        f"SUPER_ADMIN seeded with ID {super_admin.id}. Super admin is universal and not linked to any business."
    )
