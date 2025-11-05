"""
User controller - following Showroom360 pattern.
Controllers contain business logic with dependency injection.
"""
from typing import Optional
from fastapi import Depends, Query, Body
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from schemas.user import SignupRequest, LoginRequest, ChangePasswordRequest
from typing import List
from service.user import (
    signup_unauthenticated,
    signup_authenticated,
    login,
    handle_oauth_callback,
    get_refresh_token,
    get_all_users,
    get_business_users,
    change_password,
    toggle_user_status,
    delete_user,
    logout,
    switch_business,
    assign_admin_to_business,
    get_business_admin_credentials,
)
from database.postgres_optimized import get_db
from utils.auth import get_current_user, oauth2_scheme
from utils.auth_context import UserContext, require_super_admin, require_business_access
from store.enums import Resource, Action


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

async def signup_controller(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """User signup (unauthenticated)"""
    return await signup_unauthenticated(request, db)


async def signup_authenticated_controller(
    request: SignupRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """User signup (authenticated - for agents creating customers)"""
    return await signup_authenticated(request, db, current_user)


async def login_controller(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """User login"""
    return await login(request, db)


async def oauth_callback_controller(
    provider: str,
    code: str = Query(...),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """OAuth callback handler"""
    return await handle_oauth_callback(provider, code, state, db)


async def refresh_token_controller(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """Refresh access token"""
    return await get_refresh_token(refresh_token, db)


async def logout_controller(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Logout current user"""
    return await logout(token, db, current_user)


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

async def get_users_controller(
    limit: int = Query(8, ge=1, le=100, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    role: Optional[str] = Query(None, description="Filter by user role (e.g., 'customer', 'agent')"),
    business_name: Optional[str] = Query(None, description="Filter by partial business name"),
    unique_code: Optional[str] = Query(None, description="Filter by exact business unique code"),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive status"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all users with optional filters"""
    return await get_all_users(
        db=db,
        current_user=current_user,
        limit=limit,
        offset=offset,
        role=role,
        business_name=business_name,
        unique_code=unique_code,
        is_active=is_active
    )


async def get_business_users_controller(
    business_id: int,
    limit: int = Query(8, ge=5, le=100, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    role: Optional[str] = Query(None, description="Filter by user role (e.g., 'customer', 'sub_agent')"),
    savings_type: Optional[str] = Query(None, description="Filter by savings type (e.g., 'daily', 'target')"),
    savings_status: Optional[str] = Query(None, description="Filter by savings status (e.g., 'pending', 'paid')"),
    payment_method: Optional[str] = Query(None, description="Filter by payment method (e.g., 'card', 'bank_transfer')"),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive status"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get users in a specific business"""
    return await get_business_users(
        db=db,
        current_user=current_user,
        business_id=business_id,
        limit=limit,
        offset=offset,
        role=role,
        savings_type=savings_type,
        savings_status=savings_status,
        payment_method=payment_method,
        is_active=is_active
    )


async def change_password_controller(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Change user password"""
    return await change_password(request, current_user, db)


async def toggle_user_status_controller(
    user_id: int,
    is_active: bool = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Toggle user active status"""
    return await toggle_user_status(user_id, is_active, current_user, db)


async def delete_user_controller(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a user"""
    return await delete_user(user_id, current_user, db)


async def switch_business_controller(
    business_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Switch user's active business"""
    return await switch_business(business_id, current_user, db)


# ============================================================================
# ADMIN MANAGEMENT ENDPOINTS (Super Admin Only)
# ============================================================================

async def assign_admin_controller(
    business_id: int = Query(..., description="Business ID"),
    person_user_id: int = Query(..., description="User ID of person to assign as admin"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign admin to business (super_admin only)"""
    return await assign_admin_to_business(business_id, person_user_id, current_user, db)


async def get_admin_credentials_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all admin credentials (super_admin only)"""
    return await get_business_admin_credentials(current_user, db)


async def get_current_user_info_controller(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get the current authenticated user's information."""
    from models.user import User
    from models.business import Business
    
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        return {
            "success": False,
            "message": "User not found"
        }
    
    # Get user's businesses
    businesses = [
        {
            "id": b.id,
            "name": b.name,
            "unique_code": b.unique_code,
            "is_default": b.is_default
        }
        for b in user.businesses
    ]
    
    return {
        "success": True,
        "message": "User information retrieved successfully",
        "data": {
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "username": user.username,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "is_active": user.is_active,
            "location": getattr(user, 'location', None),
            "businesses": businesses,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    }

