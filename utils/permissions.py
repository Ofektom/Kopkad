"""
Business-scoped permission validation utilities for Enhanced Native RBAC.
"""
from sqlalchemy.orm import Session
from models.user import User, Permission
from models.business import BusinessPermission
import logging

logger = logging.getLogger(__name__)


def has_global_permission(user: User, permission: str) -> bool:
    """
    Check if user has a global permission (not business-scoped).
    
    Args:
        user: User object
        permission: Permission string from Permission class
        
    Returns:
        bool: True if user has the permission
    """
    return permission in user.permissions


def has_business_permission(user_id: int, business_id: int, permission: str, db: Session) -> bool:
    """
    Check if user has permission for a specific business.
    
    Args:
        user_id: User ID
        business_id: Business ID
        permission: Permission string
        db: Database session
        
    Returns:
        bool: True if user has business-scoped permission
    """
    perm = db.query(BusinessPermission).filter(
        BusinessPermission.user_id == user_id,
        BusinessPermission.business_id == business_id,
        BusinessPermission.permission == permission
    ).first()
    
    has_perm = perm is not None
    logger.debug(f"Business permission check: user={user_id}, business={business_id}, permission={permission}, result={has_perm}")
    return has_perm


def can_approve_payment(current_user: dict, savings_business_id: int, db: Session) -> bool:
    """
    Check if user can approve payments for a specific business.
    
    Rules:
    - Super admin: View only, CANNOT approve
    - Admin: Can approve ONLY for their assigned business
    - Agent/Sub-agent: Can approve for their businesses
    - Customer: CANNOT approve
    
    Args:
        current_user: Current user dict from JWT
        savings_business_id: Business ID of the savings account
        db: Database session
        
    Returns:
        bool: True if user can approve payments for this business
    """
    
    role = current_user.get("role")
    user_id = current_user.get("user_id")
    
    # Super admin cannot approve (view-only access)
    if role == "super_admin":
        logger.info(f"Super admin {user_id} cannot approve payments - view only")
        return False
    
    # Admin can approve only for their assigned business
    if role == "admin":
        has_perm = has_business_permission(
            user_id, 
            savings_business_id, 
            Permission.APPROVE_PAYMENTS, 
            db
        )
        logger.info(f"Admin {user_id} approval check for business {savings_business_id}: {has_perm}")
        return has_perm
    
    # Agent/Sub-agent can approve for their businesses
    if role in ["agent", "sub_agent"]:
        business_ids = current_user.get("business_ids", [])
        can_approve = savings_business_id in business_ids
        logger.info(f"{role.capitalize()} {user_id} approval check: business {savings_business_id} in {business_ids} = {can_approve}")
        return can_approve
    
    # Customer cannot approve
    logger.info(f"User {user_id} with role {role} cannot approve payments")
    return False


def can_reject_payment(current_user: dict, savings_business_id: int, db: Session) -> bool:
    """
    Check if user can reject payments for a specific business.
    Uses same logic as can_approve_payment.
    
    Args:
        current_user: Current user dict from JWT
        savings_business_id: Business ID of the savings account
        db: Database session
        
    Returns:
        bool: True if user can reject payments for this business
    """
    return can_approve_payment(current_user, savings_business_id, db)


def can_view_payments(current_user: dict, business_id: int = None) -> bool:
    """
    Check if user can view payments.
    
    Rules:
    - Super admin: Can view ALL payments (no business filter required)
    - Admin: Can view only their business's payments
    - Agent/Sub-agent: Can view their businesses' payments
    - Customer: Can view only their own payments
    
    Args:
        current_user: Current user dict from JWT
        business_id: Optional business ID filter
        
    Returns:
        bool: True if user can view payments
    """
    
    role = current_user.get("role")
    
    # Super admin can view all
    if role == "super_admin":
        return True
    
    # Admin/Agent/Sub-agent can view if business matches theirs
    if role in ["admin", "agent", "sub_agent"]:
        if business_id is None:
            return True  # Can request, will be filtered by their businesses
        business_ids = current_user.get("business_ids", [])
        return business_id in business_ids
    
    # Customer can view own
    if role == "customer":
        return True
    
    return False


def grant_admin_permissions(user_id: int, business_id: int, granted_by: int, db: Session):
    """
    Grant all standard admin permissions for a specific business.
    
    Permissions granted:
    - approve_payments
    - reject_payments
    - manage_business
    - view_business_analytics
    
    Args:
        user_id: Admin user ID
        business_id: Business ID
        granted_by: User ID who granted the permissions
        db: Database session
    """
    from datetime import datetime, timezone
    
    admin_permissions = [
        Permission.APPROVE_PAYMENTS,
        Permission.REJECT_PAYMENTS,
        Permission.MANAGE_BUSINESS,
        Permission.VIEW_BUSINESS_ANALYTICS,
    ]
    
    for perm in admin_permissions:
        # Check if permission already exists
        existing = db.query(BusinessPermission).filter(
            BusinessPermission.user_id == user_id,
            BusinessPermission.business_id == business_id,
            BusinessPermission.permission == perm
        ).first()
        
        if not existing:
            db.add(BusinessPermission(
                user_id=user_id,
                business_id=business_id,
                permission=perm,
                granted_by=granted_by,
                created_at=datetime.now(timezone.utc),
            ))
    
    logger.info(f"Granted admin permissions to user {user_id} for business {business_id}")


def revoke_admin_permissions(user_id: int, business_id: int, db: Session):
    """
    Revoke all admin permissions for a specific business.
    
    Args:
        user_id: Admin user ID
        business_id: Business ID
        db: Database session
    """
    
    db.query(BusinessPermission).filter(
        BusinessPermission.user_id == user_id,
        BusinessPermission.business_id == business_id
    ).delete()
    
    logger.info(f"Revoked admin permissions from user {user_id} for business {business_id}")

