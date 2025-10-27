from fastapi import APIRouter, Depends, Query, Body, HTTPException
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
    logout,  # Assumes this function blocklists the token
)
from database.postgres import get_db
from utils.auth import get_current_user, oauth2_scheme
from models.user import User
from typing import Optional
import logging

logger = logging.getLogger(__name__)

user_router = APIRouter(tags=["auth"], prefix="/api/v1/auth")  # Updated prefix to /api/v1/auth

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
    """Resets a user's password"""
    return await change_password(request, current_user, db)

@user_router.get("/me", response_model=dict)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get the current authenticated user's information."""
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
    """
    Logout user by blocklisting their access token and incrementing token_version.
    This invalidates all existing JWT tokens for the user.
    """
    try:
        user_id = current_user["user_id"]
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"Logout attempt for non-existent user ID: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        # Increment token_version to invalidate all tokens
        user.token_version += 1
        db.commit()
        
        # Blocklist the current access token
        await logout(token, db, current_user)
        
        logger.info(f"User {user.username} (ID: {user_id}) logged out successfully. Token version: {user.token_version}")
        
        return {
            "success": True,
            "message": "Logged out successfully. All active sessions have been terminated.",
            "data": {
                "user_id": user_id,
                "username": user.username
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during logout for user {current_user.get('user_id')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")