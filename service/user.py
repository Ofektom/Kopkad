from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from datetime import datetime, timezone
from typing import List, Optional
import httpx
import logging

from models.user import user_permissions, PasswordResetOtp, PasswordResetToken
from utils.password_utils import generate_otp, hash_otp, decrypt_password
from datetime import datetime, timezone, timedelta
from utils.email_service import send_reset_password_email_async, send_welcome_email, send_email_async
from utils.sms_service import send_termii_sms_async
from schemas.user import ForgotPasswordRequest, ResetPasswordRequest
import os

# Repositories (for data access)
from store.repositories import (
    UserRepository,
    BusinessRepository,
    SettingsRepository,
    UserBusinessRepository,
    SavingsRepository,
    PermissionRepository,
    UserNotificationRepository,
)

# Enums (centralized)
from store.enums import (
    Role, Permission, SavingsType, SavingsStatus, 
    PaymentMethod, NotificationMethod
)

# Schemas
from schemas.user import (
    SignupRequest,
    UserResponse,
    LoginRequest,
    ChangePasswordRequest,
    AdminUpdateRequest,
    UserUpdateRequest,
)
from schemas.business import BusinessResponse

# Utilities
from utils.response import success_response, error_response
from utils.auth import hash_password, verify_password, create_access_token, refresh_access_token
from utils.permissions import grant_admin_permissions
from sqlalchemy.sql import select
from config.settings import settings
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _normalize_phone_number(raw_phone: str) -> Optional[str]:
    """Normalize phone number to 11-digit format starting with 0; return None if invalid."""
    if not raw_phone:
        return None

    cleaned = raw_phone.strip().replace(" ", "").replace("-", "")
    digits = cleaned.replace("+", "")

    if digits.startswith("234") and len(digits) == 13:
        return "0" + digits[3:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits
    if len(digits) == 10 and not digits.startswith("0"):
        return "0" + digits

    return None

async def signup_unauthenticated(
    request: SignupRequest,
    db: Session,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    user_business_repo: UserBusinessRepository,
    settings_repo: SettingsRepository,
):
    """Handle unauthenticated signup for CUSTOMER and AGENT with optional business_code."""

    input_phone = request.phone_number.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 11 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Phone number must be 10 digits except with leading 0(zero) or include country code 234",
        )

    try:
        requested_role = Role(request.role.lower())
    except ValueError:
        return error_response(status_code=400, message="Invalid role specified")

    if requested_role not in {Role.CUSTOMER, Role.AGENT}:
        return error_response(
            status_code=403,
            message="Only CUSTOMER and AGENT can sign up without authentication",
        )

    if user_repo.exists_by_phone(phone_number):
        return error_response(
            status_code=status.HTTP_409_CONFLICT, message="Phone number already in use"
        )
    if user_repo.exists_by_username(phone_number):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Username (derived from phone number) already in use",
        )
    if request.email and user_repo.exists_by_email(request.email):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Email already in use",
        )

    if requested_role == Role.AGENT and request.business_code:
        return error_response(
            status_code=400,
            message="AGENT cannot sign up with a business_code; use /business/create to create a business after signup",
        )

    business = None
    if requested_role == Role.CUSTOMER:
        if request.business_code:
            business = business_repo.get_by_unique_code(request.business_code)
            if not business:
                return error_response(status_code=404, message="Invalid business code")

            existing_user = user_repo.get_by_phone(phone_number)
            if existing_user and user_business_repo.is_user_in_business(existing_user.id, business.id):
                return error_response(
                    status_code=status.HTTP_409_CONFLICT,
                    message="User is already registered with this business",
                )
        else:
            business = business_repo.get_by_unique_code("CEN123")
            if not business:
                return error_response(
                    status_code=500,
                    message="Default business CEN123 not found in database",
                )

    try:
        full_name = request.full_name if request.full_name else "No Name"
        user_data = {
            "full_name": full_name,
            "phone_number": phone_number,
            "email": request.email,
            "username": phone_number,
            "pin": hash_password(request.pin),
            "role": requested_role.value,
            "is_active": True,
            "created_by": 1,
            "created_at": datetime.now(timezone.utc),
        }
        user = user_repo.create_user(user_data)
        db.commit()
        db.refresh(user)

        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT.value},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS.value},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS.value},
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]
        elif requested_role == Role.CUSTOMER:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]

        if permissions_to_assign:
            db.execute(insert(user_permissions).values(permissions_to_assign))
            db.commit()

        if requested_role == Role.CUSTOMER and business:
            user_business_repo.link_user_to_business(user.id, business.id)
            db.commit()

        settings_obj = settings_repo.create_default_settings(user.id)
        db.commit()

        if request.email and settings_obj.notification_method in [NotificationMethod.EMAIL.value, NotificationMethod.BOTH.value]:
            email_result = await send_welcome_email(
                request.email, user.full_name, phone_number, requested_role.value
            )
            if email_result["status"] == "error":
                logger.error(email_result["message"])
            else:
                logger.info(f"Welcome email sent successfully to {request.email}")

        businesses = [BusinessResponse.model_validate(business)] if requested_role == Role.CUSTOMER and business else []
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id}, db=db
        )
        user_response = UserResponse(
            user_id=user.id,
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            businesses=businesses,
            created_at=user.created_at,
            access_token=access_token,
            next_action="choose_action",
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

async def signup_authenticated(
    request: SignupRequest,
    db: Session,
    current_user: dict,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    user_business_repo: UserBusinessRepository,
    settings_repo: SettingsRepository,
):
    """Handle authenticated signup, using current_user to determine business assignment."""
    input_phone = request.phone_number.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 11 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Phone number must be 10 digits except with leading 0(zero) or include country code 234",
        )

    try:
        requested_role = Role(request.role.lower())
    except ValueError:
        return error_response(status_code=400, message="Invalid role specified")

    try:
        current_user_role = Role(current_user.get("role"))
    except ValueError:
        return error_response(status_code=403, message="Invalid role for current user")

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
    if user_repo.exists_by_phone(phone_number):
        return error_response(
            status_code=status.HTTP_409_CONFLICT, message="Phone number already in use"
        )
    if user_repo.exists_by_username(phone_number):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Username (derived from phone number) already in use",
        )
    if request.email and user_repo.exists_by_email(request.email):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Email already in use",
        )

    business = None
    if current_user_role == Role.AGENT:
        business = business_repo.get_by_agent_id(current_user["user_id"])
        if not business:
            return error_response(
                status_code=403,
                message="Agent must register a business before creating sub-agents",
            )
    else:
        business = business_repo.get_by_unique_code("CEN123")
        if not business:
            return error_response(
                status_code=500, message="Default business CEN123 not found in database"
            )

    existing_user = user_repo.get_by_phone(phone_number)
    if existing_user:
        if user_business_repo.is_user_in_business(existing_user.id, business.id):
            return error_response(
                status_code=status.HTTP_409_CONFLICT,
                message="User is already registered with this business",
            )

    try:
        full_name = request.full_name if request.full_name else "No Name"
        user = user_repo.create_user({
            "full_name": full_name,
            "phone_number": phone_number,
            "email": request.email,
            "username": phone_number,
            "pin": hash_password(request.pin),
            "role": requested_role.value,
            "is_active": True,
            "created_by": current_user["user_id"],
            "created_at": datetime.now(timezone.utc),
        })
        db.commit()
        db.refresh(user)

        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT.value},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS.value},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS.value},
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]
        elif requested_role == Role.ADMIN and current_user_role == Role.SUPER_ADMIN:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]
        elif requested_role == Role.CUSTOMER:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]
        elif requested_role == Role.SUB_AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS.value},
                {"user_id": user.id, "permission": Permission.CREATE_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.MARK_SAVINGS.value},
                {"user_id": user.id, "permission": Permission.UPDATE_SAVINGS.value},
            ]

        if permissions_to_assign:
            db.execute(insert(user_permissions).values(permissions_to_assign))
            db.commit()

        user_business_repo.link_user_to_business(user.id, business.id)
        db.commit()

        settings_obj = settings_repo.create_default_settings(user.id)
        db.commit()

        # Notify creator about user creation
        from service.notifications import notify_user
        from models.financial_advisor import NotificationType, NotificationPriority
        await notify_user(
            user_id=current_user["user_id"],
            notification_type=NotificationType.USER_CREATED,
            title="User Created",
            message=f"New {requested_role.value} account has been created for {user.full_name}",
            priority=NotificationPriority.LOW,
            db=db,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=user.id,
            related_entity_type="user",
        )
        
        # Notify new user about account creation
        await notify_user(
            user_id=user.id,
            notification_type=NotificationType.USER_CREATED,
            title="Account Created",
            message=f"New {requested_role.value} account has been created for you",
            priority=NotificationPriority.LOW,
            db=db,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=user.id,
            related_entity_type="user",
        )

        if request.email and (settings_obj.notification_method in [NotificationMethod.EMAIL.value, NotificationMethod.BOTH.value]):
            await send_welcome_email(
                request.email, user.full_name, phone_number, requested_role.value
            )

        businesses = [BusinessResponse.model_validate(business)] if business else []
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id}, db=db
        )
        user_response = UserResponse(
            user_id=user.id,
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            businesses=businesses,
            created_at=user.created_at,
            access_token=access_token,
            next_action="choose_action",
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

async def login(
    request: LoginRequest,
    db: Session,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
):
    """Handle user login with username in various phone number formats."""
    input_username = request.username.replace("+", "")
    if input_username.startswith("234") and len(input_username) == 13:
        normalized_username = "0" + input_username[3:]
    elif len(input_username) == 11 and input_username.startswith("0"):
        normalized_username = input_username
    elif len(input_username) == 10 and not input_username.startswith("0"):
        normalized_username = "0" + input_username
    else:
        return error_response(
            status_code=400,
            message="Username must be a valid phone number format (e.g., +2348000000003, 2348000000003, 8000000003, 08000000003)",
        )

    user = user_repo.get_by_username(normalized_username)
    if not user or not verify_password(request.pin, user.pin):
        return error_response(status_code=401, message="Invalid credentials")
    if not user.is_active:
        return error_response(status_code=403, message="Account is inactive")

    user_role_value = getattr(user.role, "value", user.role)

    business_responses = []
    active_business_id = None

    if user_role_value != Role.SUPER_ADMIN.value:
        # get_user_businesses_with_units now handles all relationship types:
        # - Customers: via user_business table (many-to-many)
        # - Sub-agents: via user_business table (one-to-one)
        # - Admins: via business.admin_id (one-to-one)
        # - Agents: via business.agent_id (one-to-one)
        businesses = business_repo.get_user_businesses_with_units(user.id)
        
        if businesses:
            business_responses = [
                BusinessResponse.model_validate(business, from_attributes=True)
                for business in businesses
            ]

            # Determine active business based on role
            if user_role_value == Role.ADMIN.value:
                # For admins, prioritize their assigned business (via admin_id)
                admin_business = business_repo.get_by_admin_id(user.id)
                active_business_id = (
                    admin_business.id if admin_business 
                    else (user.active_business_id if user.active_business_id else businesses[0].id)
                )
            elif user_role_value == Role.AGENT.value:
                # For agents, prioritize their owned business (via agent_id)
                agent_business = business_repo.get_by_agent_id(user.id)
                active_business_id = (
                    agent_business.id if agent_business
                    else (user.active_business_id if user.active_business_id else businesses[0].id)
                )
            else:
                # For customers and sub-agents, use stored active_business_id or first business
                active_business_id = (
                    user.active_business_id if user.active_business_id else businesses[0].id
                )
            
            # Update user's active business if not set
            if not user.active_business_id:
                user_repo.update_active_business(user.id, active_business_id)
                db.commit()

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.id}, 
        db=db,
        active_business_id=active_business_id
    )
    user_response = UserResponse(
        user_id=user.id,
        full_name=user.full_name,
        phone_number=user.phone_number,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        businesses=business_responses,
        active_business_id=active_business_id,
        created_at=user.created_at,
        access_token=access_token,
        next_action="choose_action",
        address=None
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

async def change_password(
    request: ChangePasswordRequest,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
):
    """Service to change the user's pin."""
    if not current_user or "user_id" not in current_user:
        return error_response(status_code=401, message="Authentication required")

    if not request.old_pin or not request.new_pin:
        return error_response(status_code=400, message="Old pin and new pin are required")

    user = user_repo.get_by_id(current_user["user_id"])
    if not user:
        return error_response(status_code=404, message="User not found")

    if not verify_password(request.old_pin, user.pin):
        return error_response(status_code=401, message="Invalid old pin")
    
    if request.old_pin == request.new_pin:
        return error_response(status_code=400, message="New pin cannot be the same as old pin")
    
    try:
        updated_user = user_repo.update_password(user.id, hash_password(request.new_pin), user.id)
        db.commit()
        if updated_user:
            db.refresh(updated_user)
        logger.info(
            "User %s with email: %s has reset their pin",
            user.full_name,
            user.email or "N/A",
        )
        return success_response(status_code=200, message="Pin reset successful")
    except Exception as e:
        db.rollback()
        logger.error(f"Pin change failed for user {user.id}: {str(e)}")
        return error_response(status_code=500, message=f"Failed to change pin: {str(e)}")


async def forgot_password_service(request: ForgotPasswordRequest, db: Session, user_repo: UserRepository):
    """Initiate password reset: send link (email) or OTP (SMS)."""
    # Find user by username (email or phone)
    user = user_repo.get_by_email_or_phone_or_username(
        email=request.username,
        phone=request.username,
        username=request.username
    )

    if not user:
        # Don't leak existence
        return success_response(
            status_code=200,
            message="If your account is registered, a reset link or code has been sent."
        )

    # Decide delivery method
    if user.email:
        # Prefer email → magic link
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            is_used=False
        )
        db.add(reset_token)

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        reset_url = f"{frontend_url}/reset-pin?token={token}"

        email_body = f"""
        <html>
            <body>
                <h2>Password Reset Request</h2>
                <p>Hi {user.full_name or 'User'},</p>
                <p>Click the link below to reset your PIN:</p>
                <p><a href="{reset_url}">Reset PIN</a></p>
                <p>This link expires in 15 minutes.</p>
                <p>If you didn't request this, ignore this email.</p>
            </body>
        </html>
        """

        await send_reset_password_email_async(user.email, user.full_name, reset_url)

        logger.info(f"Reset link sent to email {user.email}")

    else:
        # Phone only → OTP via Termii
        otp = generate_otp(6)
        otp_hash = hash_otp(otp)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        reset_otp = PasswordResetOtp(
            user_id=user.id,
            otp_hash=otp_hash,
            expires_at=expires_at,
            is_used=False
        )
        db.add(reset_otp)

        sms_text = (
            f"Kopkad reset code: {otp}\n"
            f"Enter this code to reset your PIN. Valid for 10 minutes.\n"
            f"Do not share this code."
        )

        sms_result = await send_termii_sms_async(user.phone_number, sms_text)

        if sms_result["status"] == "error":
            logger.error(f"SMS failed for {user.phone_number}: {sms_result['message']}")
            # Still return generic success (don't block user)
        else:
            logger.info(f"OTP sent to {user.phone_number}")

    db.commit()

    return success_response(
        status_code=200,
        message="If your account is registered, a reset link or code has been sent."
    )

async def reset_password_service(request: ResetPasswordRequest, db: Session, user_repo: UserRepository):
    token = request.token
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token == token,
        PasswordResetToken.is_used == False,
        PasswordResetToken.expires_at > datetime.now(timezone.utc)
    )
    token_record = db.execute(stmt).scalar_one_or_none()

    if not token_record:
        return error_response(status_code=400, message="Invalid or expired reset token")

    user = user_repo.get_by_id(token_record.user_id)
    if not user:
        return error_response(status_code=404, message="User not found")

    user.pin = hash_password(request.new_pin)
    token_record.is_used = True
    db.commit()

    return success_response(status_code=200, message="PIN reset successful. You can now login.")

async def verify_reset_otp_service(
    request: dict,
    db: Session,
    user_repo: UserRepository,
):
    
    otp = request.get("otp")
    if not otp or len(otp) != 6 or not otp.isdigit():
        return error_response(status_code=400, message="Invalid OTP format")

    otp_hash = hash_otp(otp)

    stmt = select(PasswordResetOtp).where(
        PasswordResetOtp.otp_hash == otp_hash,
        PasswordResetOtp.is_used == False,
        PasswordResetOtp.expires_at > datetime.now(timezone.utc)
    )
    otp_record = db.execute(stmt).scalar_one_or_none()

    if not otp_record:
        return error_response(status_code=400, message="Invalid or expired OTP")

    # Mark as used
    otp_record.is_used = True
    db.commit()

    # Generate short-lived reset token for PIN change
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    reset_token_record = PasswordResetToken(
        user_id=otp_record.user_id,
        token=reset_token,
        expires_at=expires_at,
        is_used=False
    )
    db.add(reset_token_record)
    db.commit()

    return success_response(
        status_code=200,
        message="OTP verified successfully",
        data={"reset_token": reset_token}
    )

async def resend_reset_otp_service(
    request: dict,
    db: Session,
    user_repo: UserRepository,
):
    username = request.get("username")
    if not username:
        return error_response(status_code=400, message="Username required")

    user = user_repo.get_by_email_or_phone_or_username(username=username)
    if not user or not user.phone_number:
        return success_response(200, "If account exists, OTP sent")  # generic

    # Rate limit check (simple: last OTP < 60s ago)
    last_otp = db.query(PasswordResetOtp).filter(
        PasswordResetOtp.user_id == user.id
    ).order_by(PasswordResetOtp.created_at.desc()).first()

    if last_otp and (datetime.now(timezone.utc) - last_otp.created_at) < timedelta(seconds=60):
        return error_response(status_code=429, message="Please wait before requesting new OTP")

    otp = generate_otp(6)
    otp_hash = hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    new_otp = PasswordResetOtp(
        user_id=user.id,
        otp_hash=otp_hash,
        expires_at=expires_at,
        is_used=False
    )
    db.add(new_otp)
    db.commit()

    sms_text = f"Kopkad reset code: {otp}\nValid for 10 minutes. Do not share."
    await send_termii_sms_async(user.phone_number, sms_text)

    return success_response(200, "New OTP sent if account exists")

async def get_all_users(
    db: Session,
    current_user: dict,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    limit: int = 10,
    offset: int = 0,
    role: Optional[str] = None,
    business_name: Optional[str] = None,
    unique_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    """Retrieve all users with pagination and filtering by role, business name, unique code, and active status."""
    if current_user.get("role") not in {"super_admin", "admin"}:
        return error_response(status_code=403, message="Only SUPER_ADMIN or ADMIN can retrieve all users")

    try:
        # For admins, restrict to their assigned business
        admin_business_id = None
        if current_user.get("role") == "admin":
            admin_business = business_repo.get_by_admin_id(current_user["user_id"])
            if not admin_business:
                return error_response(status_code=403, message="Admin is not assigned to any business")
            admin_business_id = admin_business.id
            # Force filter by admin's business unique_code
            unique_code = admin_business.unique_code

        normalized_role = None
        if role:
            normalized_role = role.lower()
            if normalized_role not in {r.value for r in Role}:
                return error_response(status_code=400, message="Invalid role specified")

        # For admins, use business-specific user query
        if admin_business_id:
            users, total = user_repo.get_business_users_with_filters(
                business_id=admin_business_id,
                limit=limit,
                offset=offset,
                role=normalized_role,
                is_active=is_active,
                search=search,
            )
        else:
            users, total = user_repo.get_users_with_filters(
                limit=limit,
                offset=offset,
                role=normalized_role,
                business_name=business_name,
                unique_code=unique_code,
                is_active=is_active,
                search=search,
            )

        user_responses: List[UserResponse] = []
        for user in users:
            businesses = business_repo.get_user_businesses_with_units(user.id)
            business_responses = [
                BusinessResponse.model_validate(business, from_attributes=True)
                for business in businesses
            ]

            user_response = UserResponse(
                user_id=user.id,
                full_name=user.full_name,
                phone_number=user.phone_number,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                businesses=business_responses,
                created_at=user.created_at,
                access_token=None,
                next_action="choose_action",
            )
            user_responses.append(user_response)

        return success_response(
            status_code=200,
            message="Users retrieved successfully",
            data={
                "users": [user_response.model_dump() for user_response in user_responses],
                "total": total,
                "limit": limit,
                "offset": offset
            }
        )
    except Exception as e:
        logger.error(f"Failed to retrieve users: {str(e)}")
        return error_response(status_code=500, message=f"Failed to retrieve users: {str(e)}")

async def get_business_users(
    db: Session,
    current_user: dict,
    business_id: int,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    limit: int = 10,
    offset: int = 0,
    role: Optional[str] = None,
    savings_type: Optional[str] = None,
    savings_status: Optional[str] = None,
    payment_method: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """Retrieve users associated with a business, filtered by role, savings type, savings status, payment method, and active status."""
    if current_user["role"] not in [Role.AGENT, Role.SUB_AGENT]:
        return error_response(status_code=403, message="Only AGENT and SUB AGENT can retrieve business users")

    try:
        business = business_repo.get_by_id(business_id)
        if not business:
            return error_response(
                status_code=403,
                message="Business not found or you do not have access to it"
            )

        normalized_role = None
        if role:
            normalized_role = role.lower()
            if normalized_role not in {r.value for r in Role}:
                return error_response(status_code=400, message="Invalid role specified")

        normalized_savings_type = None
        if savings_type:
            normalized_savings_type = savings_type.lower()
            if normalized_savings_type not in {e.value for e in SavingsType}:
                return error_response(status_code=400, message="Invalid savings type specified")

        normalized_savings_status = None
        if savings_status:
            normalized_savings_status = savings_status.lower()
            if normalized_savings_status not in {e.value for e in SavingsStatus}:
                return error_response(status_code=400, message="Invalid savings status specified")

        normalized_payment_method = None
        if payment_method:
            normalized_payment_method = payment_method.lower()
            if normalized_payment_method not in {e.value for e in PaymentMethod}:
                return error_response(status_code=400, message="Invalid payment method specified")

        users, total = user_repo.get_business_users_with_filters(
            business_id=business_id,
            limit=limit,
            offset=offset,
            role=normalized_role,
            is_active=is_active,
            savings_type=normalized_savings_type,
            savings_status=normalized_savings_status,
            payment_method=normalized_payment_method,
        )

        user_responses: List[UserResponse] = []
        for user in users:
            business_response = BusinessResponse.model_validate(business, from_attributes=True)
            user_response = UserResponse(
                user_id=user.id,
                full_name=user.full_name,
                phone_number=user.phone_number,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                businesses=[business_response],
                created_at=user.created_at,
                access_token=None,
                next_action="choose_action",
            )
            user_responses.append(user_response)

        return success_response(
            status_code=200,
            message="Business users retrieved successfully",
            data={
                "users": [user_response.model_dump() for user_response in user_responses],
                "total": total,
                "limit": limit,
                "offset": offset
            }
        )
    except Exception as e:
        logger.error(f"Failed to retrieve business users: {str(e)}")
        return error_response(status_code=500, message=f"Failed to retrieve business users: {str(e)}")


async def toggle_user_status(
    user_id: int,
    is_active: bool,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    user_business_repo: UserBusinessRepository,
):
    """Toggle a user's active status."""
    current_user_role = current_user.get("role")
    if current_user_role not in {"super_admin", "agent"}:
        return error_response(
            status_code=403,
            message="Only SUPER_ADMIN or AGENT can toggle user status"
        )

    user = user_repo.get_by_id(user_id)
    if not user:
        return error_response(status_code=404, message="User not found")

    if user.role == Role.SUPER_ADMIN.value or user.role == Role.SUPER_ADMIN:
        return error_response(
            status_code=403,
            message="Super admin users cannot be deactivated or reactivated"
        )

    if current_user_role == "agent":
        # Check if the user is associated with the agent's business
        business = business_repo.get_by_agent_id(current_user["user_id"])
        if not business:
            return error_response(
                status_code=403,
                message="Agent has no associated business"
            )
        if not user_business_repo.is_user_in_business(user_id, business.id):
            return error_response(
                status_code=403,
                message="User is not associated with your business"
            )

    try:
        updated_user = user_repo.set_active_status(user_id, is_active, current_user["user_id"])
        db.commit()
        if updated_user:
            db.refresh(updated_user)
        target_user = updated_user or user_repo.get_by_id(user_id)
        
        # Notify user about status change
        from service.notifications import notify_user, notify_super_admins
        from models.financial_advisor import NotificationType, NotificationPriority
        status_text = "activated" if is_active else "deactivated"
        await notify_user(
            user_id=user_id,
            notification_type=NotificationType.USER_STATUS_CHANGED,
            title="Account Status Changed",
            message=f"Your account has been {status_text}",
            priority=NotificationPriority.HIGH,
            db=db,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=user_id,
            related_entity_type="user",
        )
        
        # Notify super admins if user was deactivated
        if not is_active:
            await notify_super_admins(
                notification_type=NotificationType.USER_DEACTIVATED,
                title="User Deactivated",
                message=f"User {target_user.full_name} has been deactivated",
                priority=NotificationPriority.HIGH,
                db=db,
                user_repo=user_repo,
                notification_repo=UserNotificationRepository(db),
                related_entity_id=user_id,
                related_entity_type="user",
            )
        
        user_response = UserResponse(
            user_id=target_user.id,
            full_name=target_user.full_name,
            phone_number=target_user.phone_number,
            email=target_user.email,
            role=target_user.role,
            is_active=target_user.is_active,
            businesses=[],
            created_at=target_user.created_at,
            access_token=None,
            next_action="",
        )
        return success_response(
            status_code=200,
            message=f"User {'activated' if is_active else 'deactivated'} successfully",
            data=user_response.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to toggle user status: {str(e)}")
        return error_response(
            status_code=500,
            message=f"Failed to toggle user status: {str(e)}"
        )

async def delete_user(
    user_id: int,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
    savings_repo: "SavingsRepository",
    user_business_repo: UserBusinessRepository,
    settings_repo: SettingsRepository,
):
    """Delete an inactive user without savings accounts."""
    if current_user.get("role") != "super_admin":
        return error_response(
            status_code=403,
            message="Only SUPER_ADMIN can delete users"
        )

    user = user_repo.get_by_id(user_id)
    if not user:
        return error_response(status_code=404, message="User not found")

    if user.is_active:
        return error_response(
            status_code=400,
            message="Cannot delete active user; deactivate first"
        )

    if user.role == Role.SUPER_ADMIN:
        return error_response(
            status_code=403,
            message="Super admin users cannot be deleted"
        )

    # Check for savings accounts
    if savings_repo.customer_has_accounts(user_id):
        return error_response(
            status_code=400,
            message="Cannot delete user with savings accounts; deactivate instead"
        )

    try:
        user_name = user.full_name
        user_role = user.role
        
        # Delete associated records via repositories
        user_business_repo.unlink_user_from_all_businesses(user_id)
        user_repo.delete_user_permissions(user_id)
        settings_repo.delete_by_user_id(user_id)
        user_repo.delete(user_id)
        db.commit()
        
        # Notify super admins about user deletion
        from service.notifications import notify_super_admins
        from models.financial_advisor import NotificationType, NotificationPriority
        await notify_super_admins(
            notification_type=NotificationType.USER_DELETED,
            title="User Deleted",
            message=f"User {user_name} ({user_role}) has been deleted from the system",
            priority=NotificationPriority.HIGH,
            db=db,
            user_repo=user_repo,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=user_id,
            related_entity_type="user",
        )
        
        return success_response(
            status_code=200,
            message="User deleted successfully",
            data={}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete user: {str(e)}")
        return error_response(
            status_code=500,
            message=f"Failed to delete user: {str(e)}"
        )


async def update_current_user_profile(
    request: UserUpdateRequest,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
):
    """Update current authenticated user's own profile (PATCH /auth/me)."""
    user = user_repo.get_by_id(current_user["user_id"])
    if not user:
        return error_response(status_code=404, message="User not found")

    updated = False

    if request.full_name is not None and request.full_name.strip():
        user.full_name = request.full_name.strip()
        updated = True

    if request.email is not None:
        email_lower = request.email.lower().strip()
        if email_lower != (user.email or "").lower():
            if user_repo.email_in_use(email_lower, exclude_user_id=user.id):
                return error_response(status_code=409, message="Email already in use")
            user.email = email_lower
            updated = True

    if request.phone_number is not None:
        normalized_phone = _normalize_phone_number(request.phone_number)
        if not normalized_phone:
            return error_response(status_code=400, message="Invalid phone number format")
        if normalized_phone != user.phone_number:
            if user_repo.phone_in_use(normalized_phone, exclude_user_id=user.id):
                return error_response(status_code=409, message="Phone number already in use")
            if user_repo.username_in_use(normalized_phone, exclude_user_id=user.id):
                return error_response(status_code=409, message="Username already in use")
            user.phone_number = normalized_phone
            user.username = normalized_phone  # keep username in sync
            updated = True

    if not updated:
        return success_response(
            status_code=200,
            message="No changes to apply",
            data=UserResponse.from_orm(user).model_dump()
        )

    user.updated_at = datetime.now(timezone.utc)
    user.updated_by = current_user["user_id"]

    try:
        db.commit()
        db.refresh(user)

        # Return fresh token (phone/email may affect auth)
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id},
            db=db,
            active_business_id=user.active_business_id
        )

        return success_response(
            status_code=200,
            message="Profile updated successfully",
            data=UserResponse(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,
                phone_number=user.phone_number,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                access_token=access_token,
            ).model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Profile update failed for user {user.id}: {str(e)}")
        return error_response(status_code=500, message="Failed to update profile")


async def logout(
    token: str,
    db: Session,
    current_user: dict,
    user_repo: UserRepository,
):
    """Logout user by incrementing token_version."""
    try:
        user = user_repo.increment_token_version(current_user["user_id"])
        if not user:
            return error_response(status_code=404, message="User not found")
        db.commit()
        logger.info(f"User {user.id} logged out, token_version incremented to {user.token_version}")
        return success_response(
            status_code=200,
            message="Logged out successfully",
            data={
                "user_id": user.id,
                "username": user.username
            }
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Logout failed: {str(e)}")
        return error_response(
            status_code=500,
            message=f"Failed to logout: {str(e)}"
        )


async def switch_business(
    business_id: int,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
    user_business_repo: UserBusinessRepository,
):
    """Switch user's active business and return new token."""
    try:
        user = user_repo.get_with_businesses(current_user["user_id"])
        if not user:
            return error_response(status_code=404, message="User not found")
        
        # Verify business belongs to user
        if not user_business_repo.is_user_in_business(user.id, business_id):
            return error_response(
                status_code=403,
                message="You do not have access to this business"
            )
        
        # Get business name before switching
        business = business_repo.get_by_id(business_id)
        business_name = business.name if business else f"Business {business_id}"
        
        # Update user's active business
        user_repo.update_active_business(user.id, business_id)
        db.commit()
        
        logger.info(f"User {user.id} switched to business {business_id}")
        
        # Notify user about business switch
        from service.notifications import notify_user
        from models.financial_advisor import NotificationType, NotificationPriority
        await notify_user(
            user_id=user.id,
            notification_type=NotificationType.BUSINESS_SWITCHED,
            title="Business Switched",
            message=f"You've switched to '{business_name}'",
            priority=NotificationPriority.LOW,
            db=db,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=business_id,
            related_entity_type="business",
        )
        
        # Fetch businesses for response
        businesses = business_repo.get_user_businesses_with_units(user.id)
        
        business_responses = [
            BusinessResponse.model_validate(business, from_attributes=True)
            for business in businesses
        ]
        
        # Create new token with updated active_business_id
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id},
            db=db,
            active_business_id=business_id
        )
        
        user_response = UserResponse(
            user_id=user.id,
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            businesses=business_responses,
            active_business_id=business_id,
            created_at=user.created_at,
            access_token=access_token,
            next_action="choose_action",
            address=None
        )
        
        return success_response(
            status_code=200,
            message="Business switched successfully",
            data=user_response.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Switch business error: {str(e)}")
        return error_response(status_code=500, message=f"Failed to switch business: {str(e)}")

async def assign_admin_to_business(
    business_id: int,
    person_user_id: int,
    current_user: dict,
    db: Session,
    business_repo: BusinessRepository,
    user_repo: UserRepository,
    user_business_repo: UserBusinessRepository,
    permission_repo: "PermissionRepository",
):
    """
    Super admin assigns a real person to manage a business as admin.
    Transfers admin role and permissions from auto-created account to the assigned person.
    
    Args:
        business_id: Business ID
        person_user_id: User ID of person to assign as admin
        current_user: Current user dict (must be super_admin)
        db: Database session
    """
    
    # Only super_admin can assign
    if current_user["role"] != "super_admin":
        return error_response(status_code=403, message="Only super admin can assign admins")
    
    business = business_repo.get_by_id(business_id)
    if not business:
        return error_response(status_code=404, message="Business not found")
    
    person = user_repo.get_by_id(person_user_id)
    if not person:
        return error_response(status_code=404, message="Person not found")
    
    # Get the auto-created admin
    auto_admin = user_repo.get_by_id(business.admin_id) if business.admin_id else None
    
    # Check if already assigned
    creds = business_repo.get_admin_credentials(business_id)
    
    if creds and creds.is_assigned:
        return error_response(
            status_code=400, 
            message=f"This business already has an active admin assigned: {auto_admin.full_name if auto_admin else 'Unknown'}"
        )
    
    try:
        # Store old role for response
        old_role = person.role
        
        # Transfer admin role to the assigned person
        person.role = Role.ADMIN.value
        person.is_active = True
        
        # Update business admin_id to point to new person
        business_repo.set_admin(business_id, person.id)
        
        # Transfer business permissions from auto-admin to person
        if auto_admin:
            # Revoke old admin's permissions using repository
            permission_repo.revoke_all_permissions(auto_admin.id, business_id)
            
            # Deactivate and archive auto-created admin
            auto_admin.is_active = False
            auto_admin.full_name = f"[ARCHIVED] {auto_admin.full_name}"
        
        # Grant permissions to new admin
        grant_admin_permissions(person.id, business_id, current_user["user_id"], db)
        
        # Link person to business
        if not user_business_repo.is_user_in_business(person.id, business_id):
            user_business_repo.link_user_to_business(person.id, business_id)
        
        # Update credentials record
        if creds:
            business_repo.update_admin_credentials(business_id, person.id, True)
        
        db.commit()
        
        # Notify assigned admin
        from service.notifications import notify_user, notify_super_admins, notify_business_admin
        from models.financial_advisor import NotificationType, NotificationPriority
        await notify_user(
            user_id=person.id,
            notification_type=NotificationType.ADMIN_ASSIGNED,
            title="Admin Assignment",
            message=f"You have been assigned as admin for '{business.name}'. Please change your password.",
            priority=NotificationPriority.HIGH,
            db=db,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=business_id,
            related_entity_type="business",
        )
        
        # Notify agent (owner) about admin assignment
        if business.agent_id:
            await notify_user(
                user_id=business.agent_id,
                notification_type=NotificationType.ADMIN_ASSIGNED,
                title="Admin Assigned",
                message=f"{person.full_name} has been assigned as admin for '{business.name}'",
                priority=NotificationPriority.HIGH,
                db=db,
                notification_repo=UserNotificationRepository(db),
                related_entity_id=business_id,
                related_entity_type="business",
            )
        
        # Notify super admins
        await notify_super_admins(
            notification_type=NotificationType.NEW_ADMIN_CREATED,
            title="New Admin Created",
            message=f"New admin account has been created: {person.full_name} for '{business.name}'",
            priority=NotificationPriority.MEDIUM,
            db=db,
            user_repo=user_repo,
            notification_repo=UserNotificationRepository(db),
            related_entity_id=person.id,
            related_entity_type="user",
        )
        
        logger.info(f"Assigned {person.full_name} (ID: {person.id}) as admin for business {business.id}")
        
        return success_response(
            status_code=200,
            message=f"{person.full_name} successfully assigned as admin for {business.name}",
            data={
                "business_id": business_id,
                "business_name": business.name,
                "admin_id": person.id,
                "admin_name": person.full_name,
                "previous_role": old_role,
                "new_role": "admin"
            }
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to assign admin: {str(e)}")
        return error_response(status_code=500, message=f"Failed to assign admin: {str(e)}")


async def update_admin_details(
    user_id: int,
    request: AdminUpdateRequest,
    current_user: dict,
    db: Session,
    user_repo: UserRepository,
):
    """Update profile details for an admin (super_admin only)."""
    if current_user.get("role") != "super_admin":
        return error_response(status_code=403, message="Only super admin can update admin details")

    admin = user_repo.get_by_id(user_id)
    if not admin or admin.role not in {Role.ADMIN.value, Role.ADMIN}:
        return error_response(status_code=404, message="Admin not found")

    updated = False

    if request.full_name is not None:
        admin.full_name = request.full_name.strip()
        updated = True

    if request.email is not None:
        email_lower = request.email.lower()
        if user_repo.email_in_use(email_lower, exclude_user_id=user_id):
            return error_response(status_code=409, message="Email already in use by another user")
        admin.email = email_lower
        updated = True

    if request.phone_number is not None:
        normalized_phone = _normalize_phone_number(request.phone_number)
        if not normalized_phone:
            return error_response(status_code=400, message="Invalid phone number format. Use Nigerian phone numbers.")
        if user_repo.phone_in_use(normalized_phone, exclude_user_id=user_id):
            return error_response(status_code=409, message="Phone number already in use by another user")
        if user_repo.username_in_use(normalized_phone, exclude_user_id=user_id):
            return error_response(status_code=409, message="Username already in use by another user")
        admin.phone_number = normalized_phone
        admin.username = normalized_phone
        updated = True

    if not updated:
        return success_response(
            status_code=200,
            message="No changes applied",
            data={
                "user_id": admin.id,
                "full_name": admin.full_name,
                "email": admin.email,
                "phone_number": admin.phone_number,
            },
        )

    admin.updated_at = datetime.now(timezone.utc)
    admin.updated_by = current_user.get("user_id")

    try:
        db.commit()
        admin_with_businesses = user_repo.get_with_businesses(admin.id)
        businesses = []
        if admin_with_businesses and admin_with_businesses.businesses:
            businesses = [
                {
                    "id": business.id,
                    "name": business.name,
                    "unique_code": business.unique_code,
                }
                for business in admin_with_businesses.businesses
            ]

        logger.info("Admin %s updated by super admin %s", admin.id, current_user["user_id"])

        return success_response(
            status_code=200,
            message="Admin details updated successfully",
            data={
                "user_id": admin.id,
                "full_name": admin.full_name,
                "email": admin.email,
                "phone_number": admin.phone_number,
                "businesses": businesses,
            },
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to update admin {user_id}: {str(exc)}")
        return error_response(status_code=500, message=f"Failed to update admin: {str(exc)}")


async def get_business_admin_credentials(
    current_user: dict,
    db: Session,
    business_repo: BusinessRepository,
    user_repo: UserRepository,
):
    """
    Get all business admin credentials (super_admin only).
    Shows temporary passwords for unassigned admin accounts.
    
    Args:
        current_user: Current user dict (must be super_admin)
        db: Database session
        
    Returns:
        Success response with list of admin credentials
    """
    
    if current_user["role"] != "super_admin":
        return error_response(status_code=403, message="Only super admin can view credentials")
    
    businesses = business_repo.list_all()
    credentials_list = []
    
    for business in businesses:
        admin = user_repo.get_by_id(business.admin_id) if business.admin_id else None
        creds = business_repo.get_admin_credentials(business.id)
        
        if admin and creds:
            # Only decrypt password if not assigned yet
            temp_password = None
            temp_pin = None
            if not creds.is_assigned:
                try:
                    decrypted_pwd = decrypt_password(creds.temp_password)
                    temp_password = decrypted_pwd
                    temp_pin = decrypted_pwd[:5]
                except Exception as e:
                    logger.error(f"Failed to decrypt password for business {business.id}: {str(e)}")
                    temp_password = "[DECRYPTION ERROR]"
                    temp_pin = "[ERROR]"
            
            credentials_list.append({
                "business_id": business.id,
                "business_name": business.name,
                "unique_code": business.unique_code,
                "admin_id": admin.id,
                "admin_name": admin.full_name,
                "admin_username": admin.username,
                "admin_email": admin.email,
                "is_assigned": creds.is_assigned,
                "temp_password": temp_password if not creds.is_assigned else None,
                "temp_pin": temp_pin if not creds.is_assigned else None,
                "password_changed": creds.is_password_changed,
                "expires_at": creds.expires_at.isoformat() if creds.expires_at else None,
                "created_at": creds.created_at.isoformat() if creds.created_at else None,
            })
    
    logger.info(f"Retrieved {len(credentials_list)} admin credentials for super admin {current_user['user_id']}")
    
    return success_response(
        status_code=200,
        message="Admin credentials retrieved successfully",
        data={"credentials": credentials_list, "total": len(credentials_list)}
    )


async def get_current_user_info_service(
    current_user: dict,
    user_repo: UserRepository,
    business_repo: BusinessRepository,
):
    """Return profile information for the currently authenticated user."""
    if not current_user or "user_id" not in current_user:
        return error_response(status_code=401, message="Authentication required")

    user = user_repo.get_with_businesses(current_user["user_id"])
    if not user:
        return error_response(status_code=404, message="User not found")

    user_role_value = getattr(user.role, "value", user.role)

    business_payload = []
    if user_role_value != Role.SUPER_ADMIN.value:
        businesses = business_repo.get_user_businesses_with_units(user.id)
        business_payload = [
            {
                "id": business.id,
                "name": business.name,
                "unique_code": business.unique_code,
                "is_default": getattr(business, "is_default", False),
            }
            for business in businesses
        ]

    return success_response(
        status_code=200,
        message="User information retrieved successfully",
        data={
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "username": user.username,
            "role": getattr(user.role, "value", user.role),
            "is_active": user.is_active,
            "location": getattr(user, "location", None),
            "businesses": business_payload,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    )
