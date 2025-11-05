"""
User context and permission checking utilities.
Following Showroom360 pattern for context-aware authentication and authorization.
"""
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.user import User
from models.business import Business
from store.repositories import UserRepository, BusinessRepository, PermissionRepository
from store.enums import Role, Permission
from utils.auth import get_current_user
from database.postgres_optimized import get_db
import logging

logger = logging.getLogger(__name__)


class UserContext(BaseModel):
    """
    User context bundling user, business, and permissions.
    Similar to Showroom360's UserContext pattern.
    """
    user: User
    business: Optional[Business] = None
    current_business_id: Optional[int] = None
    is_business_owner: bool = False
    is_super_admin: bool = False
    permissions: List[str] = []
    roles: List[str] = []
    business_ids: List[int] = []
    
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class PermissionChecker:
    """Static permission checking utilities"""
    
    @staticmethod
    def has_permission(user_context: UserContext, resource: str, action: str) -> bool:
        """Check if user has permission for resource/action"""
        # Super admin has view-only access
        if user_context.is_super_admin:
            if action in ["read", "view"]:
                return True
            # Super admin cannot perform operational tasks
            return False
        
        # Check if permission exists in user's permissions
        permission_str = f"{resource}:{action}"
        return permission_str in user_context.permissions
    
    @staticmethod
    def has_business_permission(
        user_context: UserContext, 
        business_id: int, 
        permission: str
    ) -> bool:
        """Check if user has permission for specific business"""
        if not user_context.current_business_id:
            return False
        
        # User must be operating in the correct business context
        if user_context.current_business_id != business_id:
            return False
        
        return permission in user_context.permissions
    
    @staticmethod
    def require_permission(
        user_context: UserContext, 
        resource: str, 
        action: str
    ) -> None:
        """Require permission or raise HTTP exception"""
        if not PermissionChecker.has_permission(user_context, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You don't have permission to {action} {resource}"
            )
    
    @staticmethod
    def require_business_permission(
        user_context: UserContext,
        business_id: int,
        permission: str
    ) -> None:
        """Require business-scoped permission or raise HTTP exception"""
        if not PermissionChecker.has_business_permission(user_context, business_id, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You don't have permission '{permission}' for this business"
            )


async def get_user_context(
    current_user: dict = Depends(get_current_user),
    business_id: Optional[int] = None,
    db: Session = Depends(get_db)
) -> UserContext:
    """
    Get user context with business and permissions loaded.
    Similar to Showroom360's get_user_context.
    """
    try:
        user_repo = UserRepository(db)
        user = user_repo.get_with_businesses(current_user["user_id"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Build context
        context = UserContext(
            user=user,
            is_super_admin=(user.role == Role.SUPER_ADMIN),
            roles=[user.role],
            business_ids=[b.id for b in user.businesses] if user.businesses else []
        )
        
        # Load business context if business_id provided or user has active_business_id
        target_business_id = business_id or user.active_business_id
        
        if target_business_id:
            business_repo = BusinessRepository(db)
            business = business_repo.get_by_id(target_business_id)
            
            if business:
                context.business = business
                context.current_business_id = business.id
                context.is_business_owner = (
                    user.role == Role.ADMIN and 
                    business.admin_id == user.id
                )
                
                # Load business-scoped permissions for admins
                if user.role == Role.ADMIN:
                    perm_repo = PermissionRepository(db)
                    perms = perm_repo.get_user_permissions(user.id, business.id)
                    context.permissions = [p.permission for p in perms]
        
        # Add global permissions based on role
        if user.role == Role.SUPER_ADMIN:
            context.permissions.extend([
                Permission.MANAGE_USERS.value,
                Permission.CREATE_ADMIN.value,
                Permission.VIEW_ADMIN_CREDENTIALS.value,
                Permission.ASSIGN_ADMIN.value,
            ])
        elif user.role in [Role.AGENT, Role.SUB_AGENT]:
            context.permissions.extend([
                Permission.CREATE_BUSINESS.value,
                Permission.CREATE_CUSTOMER.value,
                Permission.MARK_SAVINGS.value,
            ])
        
        return context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting user context: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user context"
        )


async def require_business_access(
    user_context: UserContext = Depends(get_user_context)
) -> UserContext:
    """Require business context to be present"""
    if not user_context.business:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business context is required"
        )
    
    # Super admin can view all businesses
    if user_context.is_super_admin:
        return user_context
    
    # Admin can access their assigned business
    if user_context.is_business_owner:
        return user_context
    
    # Check if user belongs to this business
    if user_context.current_business_id in user_context.business_ids:
        return user_context
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this business"
    )


def require_user_permission(resource: str, action: str):
    """
    Dependency factory for permission checking.
    Similar to Showroom360's require_user_permission.
    """
    async def dependency(user_context: UserContext = Depends(require_business_access)):
        PermissionChecker.require_permission(user_context, resource, action)
        return user_context
    return dependency


# Convenience dependencies for common permissions
async def require_super_admin(user_context: UserContext = Depends(get_user_context)):
    """Require super admin role"""
    if not user_context.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return user_context


async def require_admin(user_context: UserContext = Depends(get_user_context)):
    """Require admin role"""
    if user_context.user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user_context

