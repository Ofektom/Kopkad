"""
User controller - following Showroom360 pattern.
Controllers contain business logic with dependency injection.
"""
from typing import Optional
from fastapi import Depends, Query
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from schemas.user import SignupRequest, LoginRequest, ChangePasswordRequest
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
    role: Optional[str] = Query(None),
    business_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all users with optional filters"""
    return await get_all_users(role, business_id, is_active, page, limit, current_user, db)


async def get_business_users_controller(
    business_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get users in a specific business"""
    return await get_business_users(business_id, page, limit, current_user, db)


async def change_password_controller(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Change user password"""
    return await change_password(request, current_user, db)


async def toggle_user_status_controller(
    user_id: int,
    is_active: bool,
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
    business_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Switch user's active business"""
    return await switch_business(business_id, current_user, db)


# ============================================================================
# ADMIN MANAGEMENT ENDPOINTS (Super Admin Only)
# ============================================================================

async def assign_admin_controller(
    business_id: int,
    person_user_id: int,
    user_context: UserContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Assign admin to business (super_admin only)"""
    return await assign_admin_to_business(business_id, person_user_id, user_context.user.__dict__, db)


async def get_admin_credentials_controller(
    user_context: UserContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Get all admin credentials (super_admin only)"""
    return await get_business_admin_credentials(user_context.user.__dict__, db)

