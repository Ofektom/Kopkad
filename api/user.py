from fastapi import APIRouter, Depends, Query, Body
from typing import List
from sqlalchemy.orm import Session
from schemas.user import SignupRequest, LoginRequest, ChangePasswordRequest, UserResponse, AdminUpdateRequest
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
    update_admin_details,
)
from database.postgres_optimized import get_db
from utils.auth import get_current_user, oauth2_scheme
from typing import Optional
from store.repositories import UserRepository

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

@user_router.post("/switch-business", response_model=UserResponse)
async def switch_business_endpoint(
    business_id: int = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Switch user's active business context and get new token"""
    return await switch_business(business_id, current_user, db)

@user_router.post("/change_password", response_model=UserResponse)
async def change_user_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    ):
    """Resets a users password"""
    return await change_password(request, current_user, db)

@user_router.get("/me", response_model=dict)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get the current authenticated user's information."""
    from models.user import User, Role
    from models.business import Business
    
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        return {
            "success": False,
            "message": "User not found"
        }
    
    user_role_value = getattr(user.role, "value", user.role)
    
    # Super admin should not have businesses - they are universal
    businesses = []
    if user_role_value != Role.SUPER_ADMIN.value:
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
            "role": user_role_value,
            "is_active": user.is_active,
            "location": getattr(user, 'location', None),
            "businesses": businesses,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    }

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
    return await logout(token, db, current_user)

@user_router.post("/assign-admin", response_model=dict)
async def assign_admin_endpoint(
    business_id: int = Query(..., description="Business ID"),
    person_user_id: int = Query(..., description="User ID of person to assign as admin"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Super admin assigns a person to be admin of a business."""
    return await assign_admin_to_business(business_id, person_user_id, current_user, db)


@user_router.get("/admin-credentials", response_model=dict)
async def get_admin_credentials_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all business admin credentials (super_admin only)."""
    return await get_business_admin_credentials(current_user, db)


@user_router.patch("/admin/{user_id}", response_model=dict)
async def update_admin_endpoint(
    user_id: int,
    request: AdminUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update admin profile details (super_admin only)."""
    user_repo = UserRepository(db)
    return await update_admin_details(user_id, request, current_user, db, user_repo)
