"""
Business repository for business-related database operations.
"""
from typing import Optional, List, Dict
from decimal import Decimal
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, case
from models.business import Business, Unit, AdminCredentials, BusinessPermission
from models.user_business import user_business
from store.repositories.base import BaseRepository


class BusinessRepository(BaseRepository[Business]):
    """Repository for Business model"""
    
    def __init__(self, db: Session):
        super().__init__(Business, db)
    
    def get_by_unique_code(self, unique_code: str) -> Optional[Business]:
        """Get business by unique code"""
        return self.find_one_by(unique_code=unique_code)
    
    def get_by_agent_id(self, agent_id: int) -> Optional[Business]:
        """Get business by agent ID"""
        return self.find_one_by(agent_id=agent_id)
    
    def get_by_admin_id(self, admin_id: int) -> Optional[Business]:
        """Get business by admin ID"""
        return self.find_one_by(admin_id=admin_id)
    
    def get_with_admin(self, business_id: int) -> Optional[Business]:
        """Get business with admin user loaded"""
        return (
            self.db.query(Business)
            .options(joinedload(Business.admin))
            .filter(Business.id == business_id)
            .first()
        )
    
    def get_with_units(self, business_id: int) -> Optional[Business]:
        """Get business with units loaded"""
        return (
            self.db.query(Business)
            .options(joinedload(Business.units))
            .filter(Business.id == business_id)
            .first()
        )
    
    def get_user_businesses_with_units(self, user_id: int) -> List[Business]:
        """
        Get all businesses for a user with units loaded.
        
        Handles different relationship types:
        - Customers: via user_business table (many-to-many)
        - Sub-agents: via user_business table (one-to-one, but table allows many)
        - Admins: via business.admin_id (one-to-one)
        - Agents: via business.agent_id (one-to-one)
        - Super Admins: no businesses (returns empty list)
        """
        from models.user_business import user_business
        from sqlalchemy import or_
        
        # Query businesses from all possible relationships
        businesses = (
            self.db.query(Business)
            .options(joinedload(Business.units))
            .filter(
                or_(
                    # Customers and sub-agents: via user_business table
                    Business.id.in_(
                        self.db.query(user_business.c.business_id)
                        .filter(user_business.c.user_id == user_id)
                    ),
                    # Admins: via business.admin_id
                    Business.admin_id == user_id,
                    # Agents: via business.agent_id
                    Business.agent_id == user_id,
                )
            )
            .all()
        )
        
        return businesses
    
    def get_admin_credentials(self, business_id: int) -> Optional[AdminCredentials]:
        """Get admin credentials for business"""
        return (
            self.db.query(AdminCredentials)
            .filter(AdminCredentials.business_id == business_id)
            .first()
        )
    
    def get_all_admin_credentials(self) -> List[AdminCredentials]:
        """Get all admin credentials"""
        return self.db.query(AdminCredentials).all()
    
    def unique_code_exists(self, unique_code: str) -> bool:
        """Check if unique code already exists"""
        return self.exists(unique_code=unique_code)

    def list_all(self) -> List[Business]:
        """Return all businesses."""
        return self.db.query(Business).all()

    def get_unassigned_businesses(self) -> List[Business]:
        """Return businesses that do not currently have an assigned admin (is_assigned=False)."""
        return (
            self.db.query(Business)
            .outerjoin(AdminCredentials, AdminCredentials.business_id == Business.id)
            .filter(
                or_(
                    AdminCredentials.id.is_(None),
                    AdminCredentials.is_assigned.is_(False),
                )
            )
            .order_by(Business.created_at.desc())
            .all()
        )

    def set_admin(self, business_id: int, admin_user_id: int) -> Optional[Business]:
        """Update the admin assigned to a business."""
        business = self.get_by_id(business_id)
        if not business:
            return None
        business.admin_id = admin_user_id
        self.db.flush()
        return business

    def update_admin_credentials(self, business_id: int, admin_user_id: int, is_assigned: bool = True) -> Optional[AdminCredentials]:
        """Update admin credentials metadata for a business."""
        creds = self.get_admin_credentials(business_id)
        if not creds:
            return None
        creds.admin_user_id = admin_user_id
        creds.is_assigned = is_assigned
        self.db.flush()
        return creds

    def get_business_performance_metrics(self) -> List[Dict[str, object]]:
        """Aggregate savings, user, and unit metrics for every business."""
        from models.savings import SavingsAccount, SavingsMarking

        total_volume = func.coalesce(func.sum(SavingsMarking.amount), 0)
        paid_volume = func.coalesce(
            func.sum(
                case(
                    (SavingsMarking.status == "paid", SavingsMarking.amount),
                    else_=0,
                )
            ),
            0,
        )
        pending_volume = func.coalesce(
            func.sum(
                case(
                    (SavingsMarking.status == "pending", SavingsMarking.amount),
                    else_=0,
                )
            ),
            0,
        )

        results = (
            self.db.query(
                Business.id.label("business_id"),
                Business.name.label("name"),
                Business.unique_code.label("unique_code"),
                func.count(func.distinct(user_business.c.user_id)).label("total_users"),
                func.count(func.distinct(Unit.id)).label("total_units"),
                func.count(func.distinct(SavingsAccount.id)).label(
                    "total_savings_accounts"
                ),
                total_volume.label("total_volume"),
                paid_volume.label("paid_volume"),
                pending_volume.label("pending_volume"),
            )
            .outerjoin(user_business, user_business.c.business_id == Business.id)
            .outerjoin(Unit, Unit.business_id == Business.id)
            .outerjoin(SavingsAccount, SavingsAccount.business_id == Business.id)
            .outerjoin(
                SavingsMarking, SavingsMarking.savings_account_id == SavingsAccount.id
            )
            .group_by(Business.id)
            .order_by(Business.created_at.desc())
            .all()
        )

        metrics: List[Dict[str, object]] = []
        for row in results:
            metrics.append(
                {
                    "business_id": row.business_id,
                    "name": row.name,
                    "unique_code": row.unique_code,
                    "total_users": int(row.total_users or 0),
                    "total_units": int(row.total_units or 0),
                    "total_savings_accounts": int(row.total_savings_accounts or 0),
                    "total_volume": Decimal(row.total_volume or 0),
                    "paid_volume": Decimal(row.paid_volume or 0),
                    "pending_volume": Decimal(row.pending_volume or 0),
                }
            )
        return metrics

    def get_units_by_business(self) -> List[Dict[str, object]]:
        """Return unit counts grouped by business."""
        results = (
            self.db.query(
                Business.id.label("business_id"),
                Business.name.label("name"),
                Business.unique_code.label("unique_code"),
                func.count(Unit.id).label("unit_count"),
            )
            .outerjoin(Unit, Unit.business_id == Business.id)
            .group_by(Business.id)
            .order_by(Business.created_at.desc())
            .all()
        )
        return [
            {
                "business_id": row.business_id,
                "name": row.name,
                "unique_code": row.unique_code,
                "unit_count": int(row.unit_count or 0),
            }
            for row in results
        ]

    def count_total_units(self) -> int:
        """Return total number of units across all businesses."""
        return self.db.query(func.count(Unit.id)).scalar() or 0


class UnitRepository(BaseRepository[Unit]):
    """Repository for Unit model"""
    
    def __init__(self, db: Session):
        super().__init__(Unit, db)
    
    def get_by_business_id(self, business_id: int) -> List[Unit]:
        """Get all units for a business"""
        return self.find_by(business_id=business_id)

    def count_all_units(self) -> int:
        """Return total number of units in the system."""
        return self.db.query(func.count(Unit.id)).scalar() or 0

    def count_units_by_business(self) -> Dict[int, int]:
        """Return mapping of business_id to the number of units."""
        rows = (
            self.db.query(Unit.business_id, func.count(Unit.id))
            .group_by(Unit.business_id)
            .all()
        )
        return {business_id: count for business_id, count in rows if business_id is not None}

    def get_units_per_business(self) -> List[Dict[str, object]]:
        """Return unit counts with business metadata."""
        rows = (
            self.db.query(
                Business.id.label("business_id"),
                Business.name.label("name"),
                Business.unique_code.label("unique_code"),
                func.count(Unit.id).label("unit_count"),
            )
            .join(Business, Unit.business_id == Business.id)
            .group_by(Business.id)
            .all()
        )
        return [
            {
                "business_id": row.business_id,
                "name": row.name,
                "unique_code": row.unique_code,
                "unit_count": int(row.unit_count or 0),
            }
            for row in rows
        ]


class BusinessPermissionRepository(BaseRepository[BusinessPermission]):
    """Repository for BusinessPermission model"""
    
    def __init__(self, db: Session):
        super().__init__(BusinessPermission, db)
    
    def get_user_permissions(self, user_id: int, business_id: int) -> List[BusinessPermission]:
        """Get all permissions for user in specific business"""
        return (
            self.db.query(BusinessPermission)
            .filter(
                BusinessPermission.user_id == user_id,
                BusinessPermission.business_id == business_id
            )
            .all()
        )
    
    def has_permission(self, user_id: int, business_id: int, permission: str) -> bool:
        """Check if user has specific permission for business"""
        return self.exists(
            user_id=user_id,
            business_id=business_id,
            permission=permission
        )
    
    def grant_permission(self, user_id: int, business_id: int, permission: str, granted_by: int):
        """Grant permission to user for business"""
        from datetime import datetime, timezone
        
        # Check if already exists
        if self.has_permission(user_id, business_id, permission):
            return self.find_one_by(
                user_id=user_id,
                business_id=business_id,
                permission=permission
            )
        
        return self.create({
            "user_id": user_id,
            "business_id": business_id,
            "permission": permission,
            "granted_by": granted_by,
            "created_at": datetime.now(timezone.utc)
        })
    
    def revoke_permission(self, user_id: int, business_id: int, permission: str) -> bool:
        """Revoke permission from user for business"""
        perm = self.find_one_by(
            user_id=user_id,
            business_id=business_id,
            permission=permission
        )
        if perm:
            self.db.delete(perm)
            self.db.flush()
            return True
        return False
    
    def revoke_all_permissions(self, user_id: int, business_id: int) -> int:
        """Revoke all permissions for user in business"""
        count = (
            self.db.query(BusinessPermission)
            .filter(
                BusinessPermission.user_id == user_id,
                BusinessPermission.business_id == business_id
            )
            .delete()
        )
        self.db.flush()
        return count

