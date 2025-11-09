"""
User controller - following Showroom360 pattern.
Controllers contain business logic with dependency injection.
"""
from typing import Optional
from fastapi import Depends, Query, Body
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from schemas.user import SignupRequest, LoginRequest, ChangePasswordRequest, AdminUpdateRequest
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
    get_current_user_info_service,
    update_admin_details,
)
from database.postgres_optimized import get_db
from utils.auth import get_current_user, oauth2_scheme
from utils.auth_context import UserContext, require_super_admin, require_business_access
from utils.dependencies import get_repository
from store.enums import Resource, Action
from store.repositories import (
    UserRepository,
    BusinessRepository,
    SettingsRepository,
    UserBusinessRepository,
    SavingsRepository,
    PermissionRepository,
)


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

async def signup_controller(
    request: SignupRequest,
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    settings_repo: SettingsRepository = Depends(get_repository(SettingsRepository)),
):
    """User signup (unauthenticated)"""
    return await signup_unauthenticated(
        request=request,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
        settings_repo=settings_repo,
    )


async def signup_authenticated_controller(
    request: SignupRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    settings_repo: SettingsRepository = Depends(get_repository(SettingsRepository)),
):
    """User signup (authenticated - for agents creating customers)"""
    return await signup_authenticated(
        request=request,
        db=db,
        current_user=current_user,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
        settings_repo=settings_repo,
    )


async def login_controller(
    request: LoginRequest,
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    """User login"""
    return await login(
        request=request,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
    )


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
):
    """Refresh access token"""
    return await get_refresh_token(refresh_token)


async def logout_controller(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    """Logout current user"""
    return await logout(
        token=token,
        db=db,
        current_user=current_user,
        user_repo=user_repo,
    )


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
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    """Get all users with optional filters"""
    return await get_all_users(
        db=db,
        current_user=current_user,
        user_repo=user_repo,
        business_repo=business_repo,
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
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    """Get users in a specific business"""
    return await get_business_users(
        db=db,
        current_user=current_user,
        user_repo=user_repo,
        business_repo=business_repo,
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
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    """Change user password"""
    return await change_password(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
    )


async def toggle_user_status_controller(
    user_id: int,
    is_active: bool = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    """Toggle user active status"""
    return await toggle_user_status(
        user_id=user_id,
        is_active=is_active,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
    )


async def delete_user_controller(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    savings_repo: SavingsRepository = Depends(get_repository(SavingsRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    settings_repo: SettingsRepository = Depends(get_repository(SettingsRepository)),
):
    """Delete a user"""
    return await delete_user(
        user_id=user_id,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        savings_repo=savings_repo,
        user_business_repo=user_business_repo,
        settings_repo=settings_repo,
    )


async def switch_business_controller(
    business_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
):
    """Switch user's active business"""
    return await switch_business(
        business_id=business_id,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        business_repo=business_repo,
        user_business_repo=user_business_repo,
    )


# ============================================================================
# ADMIN MANAGEMENT ENDPOINTS (Super Admin Only)
# ============================================================================

async def assign_admin_controller(
    business_id: int = Query(..., description="Business ID"),
    person_user_id: int = Query(..., description="User ID of person to assign as admin"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    user_business_repo: UserBusinessRepository = Depends(get_repository(UserBusinessRepository)),
    permission_repo: PermissionRepository = Depends(get_repository(PermissionRepository)),
):
    """Assign admin to business (super_admin only)"""
    return await assign_admin_to_business(
        business_id=business_id,
        person_user_id=person_user_id,
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        user_repo=user_repo,
        user_business_repo=user_business_repo,
        permission_repo=permission_repo,
    )


async def get_admin_credentials_controller(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    """Get all admin credentials (super_admin only)"""
    return await get_business_admin_credentials(
        current_user=current_user,
        db=db,
        business_repo=business_repo,
        user_repo=user_repo,
    )


async def get_current_user_info_controller(
    current_user: dict = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    """Get the current authenticated user's information."""
    return await get_current_user_info_service(
        current_user=current_user,
        user_repo=user_repo,
        business_repo=business_repo,
    )


async def update_admin_details_controller(
    user_id: int,
    request: AdminUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    """Update an admin's profile details (super_admin only)."""
    return await update_admin_details(
        user_id=user_id,
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
    )

