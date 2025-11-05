from fastapi import status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func
from sqlalchemy.sql import insert
from models.user import User, Role, Permission, user_permissions
from models.business import Business, Unit, AdminCredentials, BusinessPermission
from models.user_business import user_business
from utils.password_utils import decrypt_password
from utils.permissions import grant_admin_permissions, revoke_admin_permissions
from models.settings import Settings, NotificationMethod
from schemas.user import SignupRequest, UserResponse, LoginRequest, ChangePasswordRequest
from schemas.business import BusinessResponse
from utils.response import success_response, error_response
from utils.auth import hash_password, verify_password, create_access_token, refresh_access_token
from utils.email_service import send_welcome_email
from models.savings import SavingsAccount, SavingsMarking, SavingsType, SavingsStatus, PaymentMethod
from datetime import datetime, timezone
import httpx
from config.settings import settings
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def signup_unauthenticated(request: SignupRequest, db: Session):
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
    if request.email and db.query(User).filter(User.email == request.email).first():
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
            business = (
                db.query(Business)
                .filter(Business.unique_code == request.business_code)
                .first()
            )
            if not business:
                return error_response(status_code=404, message="Invalid business code")
            existing_user = db.query(User).filter(User.phone_number == phone_number).first()
            if existing_user:
                business_association = (
                    db.query(user_business)
                    .filter(
                        user_business.c.user_id == existing_user.id,
                        user_business.c.business_id == business.id
                    )
                    .first()
                )
                if business_association:
                    return error_response(
                        status_code=status.HTTP_409_CONFLICT,
                        message="User is already registered with this business",
                    )
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
        full_name = request.full_name if request.full_name else "No Name"
        user = User(
            full_name=full_name,
            phone_number=phone_number,
            email=request.email,
            username=phone_number,
            pin=hash_password(request.pin),
            role=requested_role,
            is_active=True,
            created_by=1,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},
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

async def signup_authenticated(request: SignupRequest, db: Session, current_user: dict):
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
    if request.email and db.query(User).filter(User.email == request.email).first():
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            message="Email already in use",
        )

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
    else:
        business = db.query(Business).filter(Business.unique_code == "CEN123").first()
        if not business:
            return error_response(
                status_code=500, message="Default business CEN123 not found in database"
            )

    existing_user = db.query(User).filter(User.phone_number == phone_number).first()
    if existing_user:
        business_association = (
            db.query(user_business)
            .filter(
                user_business.c.user_id == existing_user.id,
                user_business.c.business_id == business.id
            )
            .first()
        )
        if business_association:
            return error_response(
                status_code=status.HTTP_409_CONFLICT,
                message="User is already registered with this business",
            )

    try:
        full_name = request.full_name if request.full_name else "No Name"
        user = User(
            full_name=full_name,
            phone_number=phone_number,
            email=request.email,
            username=phone_number,
            pin=hash_password(request.pin),
            role=requested_role,
            is_active=True,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        permissions_to_assign = []
        if requested_role == Role.AGENT:
            permissions_to_assign = [
                {"user_id": user.id, "permission": Permission.CREATE_SUB_AGENT},
                {"user_id": user.id, "permission": Permission.CREATE_BUSINESS},
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},
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
                {"user_id": user.id, "permission": Permission.ASSIGN_BUSINESS},
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

async def login(request: LoginRequest, db: Session):
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

    user = db.query(User).filter(User.username == normalized_username).first()
    if not user or not verify_password(request.pin, user.pin):
        return error_response(status_code=401, message="Invalid credentials")
    if not user.is_active:
        return error_response(status_code=403, message="Account is inactive")

    businesses = (
        db.query(Business)
        .options(joinedload(Business.units))
        .join(user_business, Business.id == user_business.c.business_id)
        .filter(user_business.c.user_id == user.id)
        .all()
    )

    business_responses = [
        BusinessResponse.model_validate(business, from_attributes=True)
        for business in businesses
    ] if businesses else []

    # Set default active business (user's saved preference or first business)
    active_business_id = None
    if businesses:
        active_business_id = user.active_business_id if user.active_business_id else businesses[0].id
        # Update user's active business if not set
        if not user.active_business_id:
            user.active_business_id = active_business_id
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

async def change_password(request: ChangePasswordRequest, user: User, db: Session):
    """Service to change the user's pin."""
    if not user or not request.old_pin or not request.new_pin:
        return error_response(status_code=400, message="User, old pin, and new pin are required")

    if not verify_password(request.old_pin, user.pin):
        return error_response(status_code=401, message="Invalid old pin")
    
    if request.old_pin == request.new_pin:
        return error_response(status_code=400, message="New pin cannot be the same as old pin")
    
    try:
        user.pin = hash_password(request.new_pin)
        user.updated_at = datetime.now(timezone.utc)
        user.updated_by = user.id
        db.commit()
        db.refresh(user)
        logger.info(f"User {user.full_name} with email: {user.email or 'N/A'} has reset their pin")
        return success_response(status_code=200, message="Pin reset successful")
    except Exception as e:
        db.rollback()
        logger.error(f"Pin change failed for user {user.id}: {str(e)}")
        return error_response(status_code=500, message=f"Failed to change pin: {str(e)}")

async def get_all_users(
    db: Session,
    current_user: dict,
    limit: int = 10,
    offset: int = 0,
    role: Optional[str] = None,
    business_name: Optional[str] = None,
    unique_code: Optional[str] = None,
    is_active: Optional[bool] = None
):
    """Retrieve all users with pagination and filtering by role, business name, unique code, and active status."""
    if current_user.get("role") not in {"super_admin", "admin"}:
        return error_response(status_code=403, message="Only SUPER_ADMIN or ADMIN can retrieve all users")

    try:
        query = select(User)
        if role:
            if role.lower() not in {r.value for r in Role}:
                return error_response(status_code=400, message="Invalid role specified")
            query = query.filter(User.role == role.lower())

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if business_name or unique_code:
            query = (
                query
                .join(user_business, User.id == user_business.c.user_id, isouter=True)
                .join(Business, Business.id == user_business.c.business_id, isouter=True)
            )
            if business_name:
                query = query.filter(Business.name.ilike(f"%{business_name}%"))
            if unique_code:
                query = query.filter(Business.unique_code == unique_code)

        total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
        users = db.execute(
            query.order_by(User.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all()

        user_responses: List[UserResponse] = []
        for user in users:
            businesses = (
                db.query(Business)
                .options(joinedload(Business.units).joinedload(Unit.members))
                .join(user_business, Business.id == user_business.c.business_id)
                .filter(user_business.c.user_id == user.id)
                .all()
            )
            business_responses = [BusinessResponse.model_validate(business) for business in businesses]

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
    limit: int = 10,
    offset: int = 0,
    role: Optional[str] = None,
    savings_type: Optional[str] = None,
    savings_status: Optional[str] = None,
    payment_method: Optional[str] = None,
    is_active: Optional[bool] = None
):
    """Retrieve users associated with a business, filtered by role, savings type, savings status, payment method, and active status."""
    if current_user["role"] not in [Role.AGENT, Role.SUB_AGENT]:
        return error_response(status_code=403, message="Only AGENT and SUB AGENT can retrieve business users")

    try:
        business = db.query(Business).filter(
            Business.id == business_id,
        ).first()
        
        if not business:
            return error_response(
                status_code=403,
                message="Business not found or you do not have access to it"
            )

        query = (
            select(User)
            .join(user_business, User.id == user_business.c.user_id)
            .filter(user_business.c.business_id == business_id)
        )
        
        if role:
            if role.lower() not in {r.value for r in Role}:
                return error_response(status_code=400, message="Invalid role specified")
            query = query.filter(User.role == role.lower())
        
        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if savings_type:
            if savings_type.lower() not in {e.value for e in SavingsType}:
                return error_response(status_code=400, message="Invalid savings type specified")
            query = (
                query
                .join(SavingsAccount, SavingsAccount.customer_id == User.id, isouter=True)
                .filter(SavingsAccount.savings_type == savings_type.lower())
            )

        if savings_status:
            if savings_status.lower() not in {e.value for e in SavingsStatus}:
                return error_response(status_code=400, message="Invalid savings status specified")
            query = (
                query
                .join(SavingsAccount, SavingsAccount.customer_id == User.id, isouter=True)
                .join(SavingsMarking, SavingsMarking.savings_account_id == SavingsAccount.id, isouter=True)
                .filter(SavingsMarking.status == savings_status.lower())
            )

        if payment_method:
            if payment_method.lower() not in {e.value for e in PaymentMethod}:
                return error_response(status_code=400, message="Invalid payment method specified")
            query = (
                query
                .join(SavingsAccount, SavingsAccount.customer_id == User.id, isouter=True)
                .join(SavingsMarking, SavingsMarking.savings_account_id == SavingsAccount.id, isouter=True)
                .filter(SavingsMarking.payment_method == payment_method.lower())
            )

        total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
        users = db.execute(
            query.order_by(User.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all()

        user_responses: List[UserResponse] = []
        for user in users:
            business_response = BusinessResponse.model_validate(business)
            
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


async def toggle_user_status(user_id: int, is_active: bool, current_user: dict, db: Session):
    """Toggle a user's active status."""
    current_user_role = current_user.get("role")
    if current_user_role not in {"super_admin", "agent"}:
        return error_response(
            status_code=403,
            message="Only SUPER_ADMIN or AGENT can toggle user status"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return error_response(status_code=404, message="User not found")

    if user.role == Role.SUPER_ADMIN:
        return error_response(
            status_code=403,
            message="Super admin users cannot be deactivated or reactivated"
        )

    if current_user_role == "agent":
        # Check if the user is associated with the agent's business
        business = db.query(Business).filter(Business.agent_id == current_user["user_id"]).first()
        if not business:
            return error_response(
                status_code=403,
                message="Agent has no associated business"
            )
        user_business_association = db.query(user_business).filter(
            user_business.c.user_id == user_id,
            user_business.c.business_id == business.id
        ).first()
        if not user_business_association:
            return error_response(
                status_code=403,
                message="User is not associated with your business"
            )

    try:
        user.is_active = is_active
        user.updated_at = datetime.now(timezone.utc)
        user.updated_by = current_user["user_id"]
        db.commit()
        db.refresh(user)
        user_response = UserResponse(
            user_id=user.id,
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            businesses=[],
            created_at=user.created_at,
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

async def delete_user(user_id: int, current_user: dict, db: Session):
    """Delete an inactive user without savings accounts."""
    if current_user.get("role") != "super_admin":
        return error_response(
            status_code=403,
            message="Only SUPER_ADMIN can delete users"
        )

    user = db.query(User).filter(User.id == user_id).first()
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
    savings_accounts = db.query(SavingsAccount).filter(SavingsAccount.customer_id == user_id).all()
    if savings_accounts:
        return error_response(
            status_code=400,
            message="Cannot delete user with savings accounts; deactivate instead"
        )

    try:
        # Delete associated records
        db.execute(user_business.delete().where(user_business.c.user_id == user_id))
        db.execute(user_permissions.delete().where(user_permissions.c.user_id == user_id))
        db.query(Settings).filter(Settings.user_id == user_id).delete()
        db.delete(user)
        db.commit()
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



# service/user.py
async def logout(token: str, db: Session, current_user: dict):
    """Logout user by incrementing token_version."""
    try:
        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        if not user:
            return error_response(status_code=404, message="User not found")
        user.token_version += 1
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


async def switch_business(business_id: int, current_user: dict, db: Session):
    """Switch user's active business and return new token."""
    try:
        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        if not user:
            return error_response(status_code=404, message="User not found")
        
        # Verify business belongs to user
        user_business_ids = [b.id for b in user.businesses]
        if business_id not in user_business_ids:
            return error_response(
                status_code=403,
                message="You do not have access to this business"
            )
        
        # Update user's active business
        user.active_business_id = business_id
        db.commit()
        
        logger.info(f"User {user.id} switched to business {business_id}")
        
        # Fetch businesses for response
        businesses = (
            db.query(Business)
            .options(joinedload(Business.units))
            .join(user_business, Business.id == user_business.c.business_id)
            .filter(user_business.c.user_id == user.id)
            .all()
        )
        
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
    db: Session
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
    
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return error_response(status_code=404, message="Business not found")
    
    person = db.query(User).filter(User.id == person_user_id).first()
    if not person:
        return error_response(status_code=404, message="Person not found")
    
    # Get the auto-created admin
    auto_admin = db.query(User).filter(User.id == business.admin_id).first()
    
    # Check if already assigned
    creds = db.query(AdminCredentials).filter(
        AdminCredentials.business_id == business_id
    ).first()
    
    if creds and creds.is_assigned:
        return error_response(
            status_code=400, 
            message=f"This business already has an active admin assigned: {auto_admin.full_name if auto_admin else 'Unknown'}"
        )
    
    try:
        # Store old role for response
        old_role = person.role
        
        # Transfer admin role to the assigned person
        person.role = Role.ADMIN
        person.is_active = True
        
        # Update business admin_id to point to new person
        business.admin_id = person.id
        
        # Transfer business permissions from auto-admin to person
        if auto_admin:
            # Revoke old admin's permissions
            revoke_admin_permissions(auto_admin.id, business_id, db)
            
            # Deactivate and archive auto-created admin
            auto_admin.is_active = False
            auto_admin.full_name = f"[ARCHIVED] {auto_admin.full_name}"
        
        # Grant permissions to new admin
        grant_admin_permissions(person.id, business_id, current_user["user_id"], db)
        
        # Link person to business
        existing_link = db.query(user_business).filter(
            user_business.c.user_id == person.id,
            user_business.c.business_id == business_id
        ).first()
        
        if not existing_link:
            db.execute(
                insert(user_business).values(user_id=person.id, business_id=business_id)
            )
        
        # Update credentials record
        if creds:
            creds.admin_user_id = person.id
            creds.is_assigned = True
        
        db.commit()
        
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


async def get_business_admin_credentials(current_user: dict, db: Session):
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
    
    businesses = db.query(Business).all()
    credentials_list = []
    
    for business in businesses:
        admin = db.query(User).filter(User.id == business.admin_id).first()
        creds = db.query(AdminCredentials).filter(
            AdminCredentials.business_id == business.id
        ).first()
        
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
