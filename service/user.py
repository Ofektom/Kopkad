from fastapi import status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func
from sqlalchemy.sql import insert
from models.user import User, Role, Permission, user_permissions
from models.business import Business, Unit
from models.user_business import user_business
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
            data={"sub": user.username, "role": user.role, "user_id": user.id}
        )
        user_response = UserResponse(
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
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
            data={"sub": user.username, "role": user.role, "user_id": user.id}
        )
        user_response = UserResponse(
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            role=user.role,
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

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.id}
    )
    user_response = UserResponse(
        full_name=user.full_name,
        phone_number=user.phone_number,
        email=user.email,
        role=user.role,
        businesses=business_responses,
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
                full_name=user.full_name,
                phone_number=user.phone_number,
                email=user.email,
                role=user.role,
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
                full_name=user.full_name,
                phone_number=user.phone_number,
                email=user.email,
                role=user.role,
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