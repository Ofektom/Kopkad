
from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from models.user import User, Role, Permission, user_permissions
from models.business import Business
from models.user_business import user_business
from models.settings import Settings, NotificationMethod
from schemas.user import SignupRequest, UserResponse
from utils.response import success_response, error_response
from utils.auth import hash_password, create_access_token
from utils.email_service import send_welcome_email
from datetime import datetime, timezone
from schemas.business import BusinessResponse
from schemas.user import SignupRequest, UserResponse, LoginRequest
from utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    refresh_access_token,
)
import httpx
from config.settings import settings
from datetime import datetime, timezone
from utils.email_service import send_welcome_email

import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def signup_unauthenticated(request: SignupRequest, db: Session):
    """Handle unauthenticated signup for CUSTOMER and AGENT with optional business_code."""
    input_phone = request.phone_number.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 10 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Phone number must be 10 digits (with or without leading 0) or include country code 234",
        )

    valid_roles = {
        Role.SUPER_ADMIN,
        Role.ADMIN,
        Role.AGENT,
        Role.SUB_AGENT,
        Role.CUSTOMER,
    }
    requested_role = request.role.lower()
    if requested_role not in valid_roles:
        return error_response(status_code=400, message="Invalid role specified")
    if requested_role not in {Role.CUSTOMER, Role.AGENT}:
        return error_response(
            status_code=403,
            message="Only CUSTOMER and AGENT can sign up without authentication",
        )

    if not phone_number:
        return error_response(status_code=400, message="Phone number is required")
    if db.query(User).filter(User.phone_number == phone_number).first():
        return error_response(
            status_code=status.HTTP_409_CONFLICT, message="Phone number already in use"
        )
    if db.query(User).filter(User.username == phone_number).first():
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Username (derived from phone number) already in use",
        )
    if not request.full_name:
        return error_response(status_code=400, message="Full name is required")

    if requested_role == Role.AGENT and request.business_code:
        return error_response(
            status_code=400,
            message="AGENT cannot sign up with a business_code; use /business/create to create a business after signup",
        )

    business = None
    if requested_role == Role.CUSTOMER:
        if request.business_code:
            business = (
                db.query(Business)
                .filter(Business.unique_code == request.business_code)
                .first()
            )
            if not business:
                return error_response(status_code=404, message="Invalid business code")
        else:
            business = (
                db.query(Business).filter(Business.unique_code == "CEN123").first()
            )
            if not business:
                return error_response(
                    status_code=500,
                    message="Default business CEN123 not found in database",
                )

    try:
        user = User(
            full_name=request.full_name,
            phone_number=phone_number,
            email=request.email,
            username=phone_number,
            location=request.location,
            pin=hash_password(request.pin),
            role=requested_role,
            is_active=True,
            created_by=1,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Assign permissions based on role
        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},  # Added
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]
        elif requested_role == Role.CUSTOMER:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]

        if permissions_to_assign:
            db.execute(insert(user_permissions).values(permissions_to_assign))
            db.commit()

        if requested_role == Role.CUSTOMER:
            db.execute(
                insert(user_business).values(user_id=user.id, business_id=business.id)
            )
            db.commit()

        settings_obj = Settings(
            user_id=user.id, notification_method=NotificationMethod.BOTH
        )
        db.add(settings_obj)
        db.commit()

        if request.email and settings_obj.notification_method in ["email", "both"]:
            email_result = await send_welcome_email(
                request.email, user.full_name, phone_number, requested_role
            )
            if email_result["status"] == "error":
                logger.error(email_result["message"])
            else:
                logger.info(f"Welcome email sent successfully to {request.email}")

        business_ids = [business.id] if requested_role == Role.CUSTOMER else []
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id}
        )
        user_response = UserResponse(
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            business_ids=business_ids,
            created_at=user.created_at,
            access_token=access_token,
            next_action="choose_action",
            location=user.location,
        )
        return success_response(
            status_code=201,
            message=f"Welcome, {user.full_name}!",
            data=user_response.dict(),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Signup failed: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to create user: {str(e)}"
        )


async def signup_authenticated(request: SignupRequest, db: Session, current_user: dict):
    """Handle authenticated signup, using current_user to determine business assignment."""
    input_phone = request.phone_number.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 10 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Phone number must be 10 digits (with or without leading 0) or include country code 234",
        )

    valid_roles = {
        Role.SUPER_ADMIN,
        Role.ADMIN,
        Role.AGENT,
        Role.SUB_AGENT,
        Role.CUSTOMER,
    }
    requested_role = request.role.lower()
    if requested_role not in valid_roles:
        return error_response(status_code=400, message="Invalid role specified")

    current_user_role = current_user.get("role")
    if current_user_role not in {Role.SUPER_ADMIN, Role.ADMIN, Role.AGENT}:
        return error_response(
            status_code=403, message="Insufficient permissions to create a user"
        )
    if requested_role != Role.SUB_AGENT and current_user_role not in {
        Role.ADMIN,
        Role.SUPER_ADMIN,
    }:
        return error_response(
            status_code=403,
            message="Only ADMIN or SUPER_ADMIN can create non-SUB_AGENT roles",
        )

    if not phone_number:
        return error_response(status_code=400, message="Phone number is required")
    if db.query(User).filter(User.phone_number == phone_number).first():
        return error_response(
            status_code=status.HTTP_409_CONFLICT, message="Phone number already in use"
        )
    if db.query(User).filter(User.username == phone_number).first():
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Username (derived from phone number) already in use",
        )
    if not request.full_name:
        return error_response(status_code=400, message="Full name is required")

    business = None
    if current_user_role == Role.AGENT:
        business = (
            db.query(Business)
            .filter(Business.agent_id == current_user["user_id"])
            .first()
        )
        if not business:
            return error_response(
                status_code=403,
                message="Agent must register a business before creating sub-agents",
            )
    else:  # SUPER_ADMIN or ADMIN
        business = db.query(Business).filter(Business.unique_code == "CEN123").first()
        if not business:
            return error_response(
                status_code=500, message="Default business CEN123 not found in database"
            )

    try:
        user = User(
            full_name=request.full_name,
            phone_number=phone_number,
            email=request.email,
            username=phone_number,
            location=request.location,
            pin=hash_password(request.pin),
            role=requested_role,
            is_active=True,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Assign permissions based on role
        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},  # Added
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]
        elif requested_role == Role.ADMIN and current_user_role == Role.SUPER_ADMIN:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]
        elif requested_role == Role.CUSTOMER:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]
        elif requested_role == Role.SUB_AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},  # Added
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS},
            ]

        if permissions_to_assign:
            db.execute(insert(user_permissions).values(permissions_to_assign))
            db.commit()

        db.execute(
            insert(user_business).values(user_id=user.id, business_id=business.id)
        )
        db.commit()

        settings_obj = Settings(
            user_id=user.id, notification_method=NotificationMethod.BOTH
        )
        db.add(settings_obj)
        db.commit()

        if request.email and (settings_obj.notification_method in ["email", "both"]):
            await send_welcome_email(
                request.email, user.full_name, phone_number, requested_role
            )

        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id}
        )
        user_response = UserResponse(
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            business_ids=[business.id],
            created_at=user.created_at,
            access_token=access_token,
            next_action="choose_action",
            location=user.location,
        )
        return success_response(
            status_code=201,
            message=f"Welcome, {user.full_name}!",
            data=user_response.dict(),
        )
    except Exception as e:
        db.rollback()
        return error_response(
            status_code=500, message=f"Failed to create user: {str(e)}"
        )


async def login(request: LoginRequest, db: Session):
    """Handle user login with username in various phone number formats."""
    input_username = request.username.replace("+", "")
    if input_username.startswith("234") and len(input_username) == 13:
        normalized_username = "0" + input_username[3:]
    elif len(input_username) == 10 and input_username.startswith("0"):
        normalized_username = input_username
    elif len(input_username) == 10 and not input_username.startswith("0"):
        normalized_username = "0" + input_username
    else:
        return error_response(
            status_code=400,
            message="Username must be a valid phone number format (e.g., +2348000000003, 2348000000003, 8000000003)",
        )

    user = db.query(User).filter(User.username == normalized_username).first()
    if not user or not verify_password(request.pin, user.pin):
        return error_response(status_code=401, message="Invalid credentials")
    if not user.is_active:
        return error_response(status_code=403, message="Account is inactive")

    # Fetch full business objects instead of just IDs
    businesses = (
        db.query(Business)
        .join(user_business, Business.id == user_business.c.business_id)
        .filter(user_business.c.user_id == user.id)
        .all()
    )
    if not businesses:
        return error_response(
            status_code=403,
            message="User must be associated with at least one business",
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.id}
    )
    user_response = UserResponse(
        full_name=user.full_name,
        phone_number=user.phone_number,
        email=user.email,
        role=user.role,
        businesses=[BusinessResponse.model_validate(business) for business in user.businesses],
        created_at=user.created_at,
        access_token=access_token,
        next_action="choose_action",
        location=user.location,
    )
    return success_response(
        status_code=200, message="Login successful", data=user_response.model_dump()
    )


async def handle_oauth_callback(provider: str, code: str, state: str, db: Session):
    """Handle OAuth callback to extract raw user data from provider and return it to frontend."""
    async with httpx.AsyncClient() as client:
        if provider == "google":
            logger.info(
                f"Processing Google OAuth callback with code: {code}, state: {state}"
            )
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            token_data = token_response.json()
            logger.info(f"Google token response: {token_data}")
            if "error" in token_data:
                return error_response(
                    status_code=400,
                    message=f"Failed to authenticate with Google: {token_data.get('error_description', 'No details provided')}",
                )
            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            user_info = user_info_response.json()
            return success_response(
                status_code=200,
                message="Google OAuth data retrieved successfully",
                data=user_info,
            )
        elif provider == "facebook":
            token_response = await client.get(
                f"https://graph.facebook.com/v20.0/oauth/access_token",
                params={
                    "client_id": settings.FACEBOOK_CLIENT_ID,
                    "client_secret": settings.FACEBOOK_CLIENT_SECRET,
                    "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
                    "code": code,
                },
            )
            token_data = token_response.json()
            if "error" in token_data:
                return error_response(
                    status_code=400, message="Failed to authenticate with Facebook"
                )
            user_info_response = await client.get(
                f"https://graph.facebook.com/me?fields=id,name,email&access_token={token_data['access_token']}"
            )
            user_info = user_info_response.json()
            return success_response(
                status_code=200,
                message="Facebook OAuth data retrieved successfully",
                data=user_info,
            )
        else:
            return error_response(status_code=400, message="Unsupported OAuth provider")


async def get_refresh_token(refresh_token: str):
    """Refresh access token."""
    refresh_data = refresh_access_token(refresh_token)
    if not refresh_data:
        return error_response(
            status_code=401, message="Invalid or expired refresh token"
        )
    return success_response(
        status_code=status.HTTP_200_OK,
        message="Access token refreshed successfully",
        data={"access_token": refresh_data},
    )