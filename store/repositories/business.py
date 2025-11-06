"""
Business repository for business-related database operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from models.business import Business, Unit, AdminCredentials, BusinessPermission
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
        """Get all businesses for a user with units loaded"""
        from models.user_business import user_business
        return (
            self.db.query(Business)
            .options(joinedload(Business.units))
            .join(user_business, Business.id == user_business.c.business_id)
            .filter(user_business.c.user_id == user_id)
            .all()
        )
    
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


class UnitRepository(BaseRepository[Unit]):
    """Repository for Unit model"""
    
    def __init__(self, db: Session):
        super().__init__(Unit, db)
    
    def get_by_business_id(self, business_id: int) -> List[Unit]:
        """Get all units for a business"""
        return self.find_by(business_id=business_id)


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

