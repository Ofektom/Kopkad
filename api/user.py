from fastapi import APIRouter, Depends, Query, Body
from typing import List
from sqlalchemy.orm import Session
from schemas.user import SignupRequest, LoginRequest, ChangePasswordRequest, UserResponse
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
)
from database.postgres import get_db
from utils.auth import get_current_user, oauth2_scheme
from typing import Optional

user_router = APIRouter(tags=["auth"], prefix="/auth")


@user_router.post("/signup", response_model=UserResponse)
async def signup_unauthenticated_endpoint(
    request: SignupRequest, db: Session = Depends(get_db)
):
    return await signup_unauthenticated(request, db)


@user_router.post("/signup-authenticated", response_model=UserResponse)
async def signup_authenticated_endpoint(
    request: SignupRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await signup_authenticated(request, db, current_user)


@user_router.post("/login", response_model=UserResponse)
async def login_endpoint(request: LoginRequest, db: Session = Depends(get_db)):
    return await login(request, db)


@user_router.get("/oauth/callback/{provider}", response_model=UserResponse)
async def oauth_callback(
    provider: str, code: str, state: str, db: Session = Depends(get_db)
):
    return await handle_oauth_callback(provider, code, state, db)


@user_router.post("/refresh", response_model=UserResponse)
async def refresh_token(refresh_token: str):
    return await get_refresh_token(refresh_token)

@user_router.post("/change_password", response_model=UserResponse)
async def change_user_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    ):
    """Resets a users password"""
    return await change_password(request, current_user, db)

@user_router.get("/users", response_model=List[UserResponse])
async def list_all_users(
    limit: int = Query(8, ge=1, le=100, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    role: Optional[str] = Query(None, description="Filter by user role (e.g., 'customer', 'agent')"),
    business_name: Optional[str] = Query(None, description="Filter by partial business name"),
    unique_code: Optional[str] = Query(None, description="Filter by exact business unique code"),
    is_active: Optional[bool] = Query(None, description="Filter by active/inactive status"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve all users with pagination and filtering, restricted to SUPER_ADMIN or ADMIN."""
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

@user_router.get("/business/{business_id}/users", response_model=List[UserResponse])
async def list_business_users(
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
    """Retrieve users associated with a business, restricted to AGENT who owns the business and SUB_AGENTS."""
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

@user_router.patch("/users/{user_id}/status", response_model=dict)
async def toggle_user_status_route(
    user_id: int,
    is_active: bool = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await toggle_user_status(user_id, is_active, current_user, db)

@user_router.delete("/users/{user_id}", response_model=dict)
async def delete_user_route(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return await delete_user(user_id, current_user, db)

@user_router.post("/logout")
async def logout_endpoint(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Logout the current user by blocklisting their access token."""
    return await logout(token, db)