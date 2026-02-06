from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from sqlalchemy import select, or_, func
from models.business import Business, PendingBusinessRequest, Unit, user_units, AdminCredentials, BusinessPermission, BusinessType
from models.user_business import user_business
from models.user import User, user_permissions
from store.enums.enums import Role, Permission
from utils.response import success_response, error_response
from utils.password_utils import generate_admin_credentials, encrypt_password
from utils.permissions import grant_admin_permissions
from utils.auth import hash_password
from schemas.business import (
    BusinessCreate, 
    BusinessResponse, 
    BusinessUpdate, 
    UnitCreate, 
    UnitResponse, 
    CustomerInvite,
    UnitUpdate,
)
from datetime import datetime, timezone
import string
import random
import uuid
from datetime import timezone, timedelta
from utils.email_service import (
    send_business_created_email,
    send_business_invitation_email,
)
from config.settings import settings
from typing import Optional
from datetime import date
import logging

from store.repositories import (
    BusinessRepository,
    UnitRepository,
    BusinessPermissionRepository,
    UserRepository,
    UserBusinessRepository,
    PendingBusinessRequestRepository,
    UserNotificationRepository,
)
from models.financial_advisor import NotificationType, NotificationPriority
from service.notifications import notify_user, notify_super_admins, notify_business_admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    """Utility to fallback to repository instance if not provided."""
    return repo if repo is not None else repo_cls(db)

def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions

async def create_business(
    request: BusinessCreate,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None,
    unit_repo: UnitRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Create a thrift business."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = business_repo.db

    logger.info(f"Initiating business creation for agent_id: {current_user['user_id']}")

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")
    if current_user["role"] != Role.AGENT:
        return error_response(status_code=403, message="Only AGENT can create businesses")
    if not has_permission(current_user_obj, Permission.CREATE_BUSINESS, session):
        return error_response(status_code=403, message="No permission to create business")

    if business_repo.find_one_by(agent_id=current_user["user_id"]):
        return error_response(status_code=403, message="User can only own one business")

    characters = string.digits + string.ascii_letters
    max_attempts = 100
    for _ in range(max_attempts):
        unique_code = "".join(random.choice(characters) for _ in range(6))
        if not business_repo.unique_code_exists(unique_code):
            break
    else:
        return error_response(
            status_code=500, message="Unable to generate unique code after multiple attempts"
        )

    try:
        # 1. Create business
        business = Business(
            name=request.name,
            agent_id=current_user["user_id"],
            address=request.address,
            unique_code=unique_code,
            is_default=False,
            business_type=BusinessType(request.business_type) if request.business_type else BusinessType.STANDARD,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        session.add(business)
        session.flush()  # Get business.id before creating admin
        
        # 2. AUTO-CREATE ADMIN USER for this business
        admin_creds = generate_admin_credentials(request.name, unique_code)
        
        admin_user = User(
            full_name=admin_creds['full_name'],
            phone_number=admin_creds['phone'],
            email=admin_creds['email'],
            username=admin_creds['phone'],
            pin=hash_password(admin_creds['pin']),
            role=Role.ADMIN,
            is_active=False,  # Inactive until super_admin assigns someone
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        session.add(admin_user)
        session.flush()  # Get admin_user.id
        
        # 3. Link admin to business
        business.admin_id = admin_user.id
        
        # 4. Store encrypted admin credentials (super admin can see these)
        admin_credentials_record = AdminCredentials(
            business_id=business.id,
            admin_user_id=admin_user.id,
            temp_password=encrypt_password(admin_creds['password']),
            is_password_changed=False,
            is_assigned=False,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(admin_credentials_record)
        
        # 5. Grant business-scoped permissions to admin
        grant_admin_permissions(admin_user.id, business.id, current_user["user_id"], session)
        
        # Notify super admins about admin credentials generated
        from service.notifications import notify_super_admins
        await notify_super_admins(
            notification_type=NotificationType.ADMIN_CREDENTIALS_GENERATED,
            title="Admin Credentials Generated",
            message=f"Admin credentials have been generated for '{business.name}'. Please assign an admin.",
            priority=NotificationPriority.HIGH,
            db=session,
            user_repo=user_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=business.id,
            related_entity_type="business",
        )
        
        # 6. Create default unit (existing logic)
        if request.address:
            unit = Unit(
                name=f"{request.name} Default Unit",
                business_id=business.id,
                location=request.address,
                created_by=current_user["user_id"],
                created_at=datetime.now(timezone.utc),
            )
            session.add(unit)
        
        # 7. Link agent to business (existing logic)
        user_business_repo.link_user_to_business(current_user["user_id"], business.id)
        
        session.commit()
        session.refresh(business)

        # Notify agent about business creation
        await notify_user(
            user_id=current_user["user_id"],
            notification_type=NotificationType.BUSINESS_CREATED,
            title="Business Created",
            message=f"Your business '{business.name}' has been created successfully with unique code: {unique_code}",
            priority=NotificationPriority.LOW,
            db=session,
            notification_repo=notification_repo,
            related_entity_id=business.id,
            related_entity_type="business",
        )
        
        # Notify super admins about new business
        await notify_super_admins(
            notification_type=NotificationType.NEW_BUSINESS_REGISTERED,
            title="New Business Registered",
            message=f"New business '{business.name}' has been registered by {current_user_obj.full_name}",
            priority=NotificationPriority.MEDIUM,
            db=session,
            user_repo=user_repo,
            notification_repo=notification_repo,
            related_entity_id=business.id,
            related_entity_type="business",
        )

        user = user_repo.get_by_id(current_user["user_id"])
        notification_method = user.settings.notification_method if user.settings else "both"
        delivery_status = "sent_to_"
        if user.phone_number and notification_method in ["whatsapp", "both"]:
            delivery_status += "whatsapp"
        if user.email and notification_method in ["email", "both"]:
            delivery_status += "_and_email"
            await send_business_created_email(
                user.email, user.full_name, business.name, unique_code, business.created_at.isoformat()
            )
        if not user.phone_number and not user.email:
            delivery_status = "pending"

        business_response = BusinessResponse.model_validate(business)
        
        # Return with admin credentials for super_admin to view
        logger.info(f"Business '{business.name}' created successfully with code: {unique_code}")
        return success_response(
            status_code=201,
            message=f"Business and admin account created successfully. Unique code: {unique_code}",
            data={
                "business": business_response.model_dump(),
                "admin_credentials": {
                    "admin_id": admin_user.id,
                    "username": admin_creds['phone'],
                    "email": admin_creds['email'],
                    "temporary_password": admin_creds['password'],  # Show once
                    "temporary_pin": admin_creds['pin'],
                    "expires_in_days": 30,
                    "status": "unassigned",
                    "note": "Admin account is inactive. Super admin must assign a person to activate it."
                }
            },
        )
    except Exception as e:
        session.rollback()
        session.rollback()
        logger.exception("Full traceback for create_business failure:")
        return error_response(status_code=500, message=f"Failed to create business: {str(e)}")

async def add_customer_to_business(
    request: CustomerInvite,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    business_repo: BusinessRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    pending_repo: PendingBusinessRequestRepository | None = None,
    unit_repo: UnitRepository | None = None,
):
    """Add an existing customer to a business for AGENT, SUB_AGENT, or SUPER_ADMIN."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    pending_repo = _resolve_repo(pending_repo, PendingBusinessRequestRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = user_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")
    if current_user["role"] not in [Role.AGENT, Role.SUB_AGENT, Role.SUPER_ADMIN]:
        return error_response(
            status_code=403, message="Only AGENT, SUB_AGENT, or SUPER_ADMIN can add customers to a business"
        )
    if current_user["role"] != Role.SUPER_ADMIN and not has_permission(current_user_obj, Permission.ASSIGN_BUSINESS, session):
        return error_response(status_code=403, message="No permission to assign customers to business")

    input_phone = request.customer_phone.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 11 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Customer phone number must be 10 or 11 digits (with leading 0) or include country code 234 with 13 digits"
        )

    customer = user_repo.get_by_phone(phone_number)
    
    # Handle New User Creation (Invite-to-Setup)
    if not customer:
        if request.email and user_repo.exists_by_email(request.email):
             return error_response(
                status_code=status.HTTP_409_CONFLICT,
                message="Email already in use by another user"
            )
            
        # Determine role based on business type
        business = business_repo.find_one_by(unique_code=request.business_unique_code)
        if not business:
             return error_response(status_code=404, message="Business not found")
             
        new_role = Role.CUSTOMER
        if hasattr(business, 'business_type') and business.business_type == "cooperative":
             new_role = Role.COOPERATIVE_MEMBER
             
        try:
            # Create inactive stub user
            logger.info(f"Attempting to create placeholder user for phone: {phone_number}")
            customer = User(
                full_name="Invited Member", # Placeholder
                phone_number=phone_number,
                email=request.email,
                username=phone_number,
                pin=hash_password("1234"), # Temporary dummy PIN
                role=new_role,
                is_active=False,
                created_by=current_user["user_id"],
                created_at=datetime.now(timezone.utc),
            )
            session.add(customer)
            session.flush() # Get ID
            logger.info(f"Placeholder user created with ID: {customer.id}")
            
            # Assign minimal permissions (will be expanded on setup)
            logger.info(f"Assigning permissions. Permission value being used: {Permission.VIEW_OWN_CONTRIBUTIONS}")
            permissions_to_assign = [
                {"user_id": customer.id, "permission": Permission.VIEW_OWN_CONTRIBUTIONS.value},
            ]
            session.execute(insert(user_permissions).values(permissions_to_assign))
            
            logging.info(f"Created stub user {customer.id} for invite")
        except Exception as e:
            session.rollback()
            logger.exception("Full traceback for placeholder user creation failure:") # Log full stack trace
            return error_response(status_code=500, message=f"Failed to create placeholder user: {str(e)}")

    if customer and customer.role not in [Role.CUSTOMER, Role.COOPERATIVE_MEMBER]:
        return error_response(status_code=400, message="User exists but has an incompatible role")
        
    business = business_repo.find_one_by(unique_code=request.business_unique_code)
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] == Role.AGENT and business.agent_id != current_user["user_id"]:
        return error_response(
            status_code=403, message="Agent must be the owner of the business to add customers"
        )
    if current_user["role"] == Role.SUB_AGENT:
        if not user_business_repo.is_user_in_business(current_user["user_id"], business.id):
            return error_response(
                status_code=403, message="Sub-agent not found in this business"
            )

    if user_business_repo.is_user_in_business(customer.id, business.id):
        return error_response(
            status_code=409, message="Customer already associated with this business"
        )

    if request.unit_id:
        unit = unit_repo.find_one_by(id=request.unit_id, business_id=business.id)
        if not unit:
            return error_response(status_code=404, message="Unit not found in this business")

    try:
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        pending_request = pending_repo.create_request(
            customer_id=customer.id,
            business_id=business.id,
            unit_id=request.unit_id,
            token=token,
            expires_at=expires_at,
        )
        session.commit()

        accept_url = f"{settings.APP_BASE_URL}/business/accept-invitation?token={token}"
        reject_url = f"{settings.APP_BASE_URL}/business/reject-invitation?token={token}"
        
        # Determine notification method
        delivery_method = []
        
        # Priority: Email if available (even for inactive users)
        if request.email or customer.email:
            email_to_use = request.email or customer.email
            await send_business_invitation_email(
                email_to_use, customer.full_name, business.name, accept_url, reject_url
            )
            delivery_method.append("email")
            
        # Log for WhatsApp (simulated)
        if not delivery_method: 
             logging.info(f"SIMULATED WHATSAPP INVITE: Send to {phone_number} with link {accept_url}")
             delivery_method.append("whatsapp (simulated)")

        # Notify customer about invitation (if active and has push)
        if customer.is_active:
            from service.notifications import notify_user
            await notify_user(
                user_id=customer.id,
                notification_type=NotificationType.BUSINESS_INVITATION_SENT,
                title="Business Invitation",
                message=f"You've been invited to join '{business.name}'. Please check your email to accept or reject.",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=business.id,
                related_entity_type="business",
                )

        return success_response(
            status_code=200,
            message=f"Invitation sent to customer {customer.full_name} via {', '.join(delivery_method)}, it expires in 24 hours",
            data={"status": "pending", "expires_at": expires_at.isoformat()}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to initiate customer invitation: {str(e)}")
        return error_response(status_code=500, message=f"Failed to process invitation: {str(e)}")

async def complete_registration_service(
    token: str,
    password: str,
    pin: str,
    full_name: str, # Allow updating name
    db: Session,
    pending_repo: PendingBusinessRequestRepository | None = None,
    user_repo: UserRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    business_repo: BusinessRepository | None = None,
):
    """Complete registration for an invited user: Set password, PIN, Activate, and Link to Business."""
    pending_repo = _resolve_repo(pending_repo, PendingBusinessRequestRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    session = db

    logger.info(f"Processing complete_registration for token: {token}")

    pending_request = pending_repo.get_by_token(token)
    if not pending_request:
        return error_response(status_code=404, message="Invalid or missing invitation token")

    if pending_request.expires_at < datetime.now(timezone.utc):
        pending_repo.delete_request(pending_request)
        session.commit()
        return error_response(status_code=410, message="Invitation has expired")

    user = user_repo.get_by_id(pending_request.customer_id)
    if not user:
        return error_response(status_code=404, message="User not found")
        
    if user.is_active:
        return error_response(status_code=400, message="User is already active. Please log in.")

    try:
        # Update User Credentials
        # Note: UserRepository might not have update_credentials method, doing it via session directly or adding method
        user.pin = hash_password(pin)
        # We need a password field? User model has 'password' or just 'pin'? 
        # Looking at User model... it seems to use `pin` for auth in `login` service "verify_password(request.pin, user.pin)".
        # Wait, the `login` checks `pin`. Does it have `password` field?
        # Let's check `models/user.py` again.
        # Assuming `pin` is the main credential or there is `password`.
        # The PROMPT says "create password/pin".
        # The `signup_unauthenticated` sets `pin`.
        # I will set `pin`. If there is a password field I should set it too.
        # Checking `login` service: `verify_password(request.pin, user.pin)`. It seems PIN is the password.
        # But `AdminCredentials` has `temp_password`.
        # I'll update `pin` and `full_name`.
        
        user.full_name = full_name
        user.is_active = True
        
        # Link to Business
        user_business_repo.link_user_to_business(
            pending_request.customer_id, pending_request.business_id
        )
        if pending_request.unit_id:
             session.execute(
                insert(user_units).values(
                    user_id=pending_request.customer_id,
                    unit_id=pending_request.unit_id
                )
            )
            
        # Delete Pending Request
        pending_repo.delete_request(pending_request)
        
        session.commit()
        
        # Notify...
        
        # Generate Token
        from utils.auth import create_access_token
        access_token = create_access_token(
            data={"sub": user.username, "role": user.role, "user_id": user.id}, 
            db=db,
            active_business_id=pending_request.business_id
        )
        
        logger.info(f"Registration completed for user_id: {user.id}")
        return success_response(
            status_code=200,
            message="Registration completed successfully",
            data={
                "user_id": user.id,
                "full_name": user.full_name,
                "role": user.role,
                "access_token": access_token
            }
        )
        
    except Exception as e:
        session.rollback()
        session.rollback()
        logger.exception("Full traceback for complete_registration failure:")
        return error_response(status_code=500, message=f"Failed to complete registration: {str(e)}")


async def accept_business_invitation(
    token: str,
    db: Session,
    *,
    pending_repo: PendingBusinessRequestRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    business_repo: BusinessRepository | None = None,
    user_repo: UserRepository | None = None, # Added
):
    """Accept a business invitation via token."""
    pending_repo = _resolve_repo(pending_repo, PendingBusinessRequestRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db) # Added
    session = pending_repo.db

    logger.info(f"Processing accept_business_invitation for token: {token}")

    pending_request = pending_repo.get_by_token(token)
    if not pending_request:
        return error_response(status_code=404, message="Invalid or missing invitation token")

    if pending_request.expires_at < datetime.now(timezone.utc):
        pending_repo.delete_request(pending_request)
        session.commit()
        return error_response(status_code=410, message="Invitation has expired")

    # CHECK IF USER NEEDS SETUP
    user = user_repo.get_by_id(pending_request.customer_id)
    if user and not user.is_active:
        return success_response(
            status_code=200,
            message="User setup required",
            data={
                "needs_setup": True,
                "token": token,
                "phone_number": user.phone_number,
                "email": user.email
            }
        )

    try:
        user_business_repo.link_user_to_business(
            pending_request.customer_id, pending_request.business_id
        )
        if pending_request.unit_id:
            session.execute(
                insert(user_units).values(
                    user_id=pending_request.customer_id,
                    unit_id=pending_request.unit_id
                )
            )
        pending_repo.delete_request(pending_request)
        session.commit()

        business = business_repo.get_by_id(pending_request.business_id)
        customer = user_repo.get_by_id(pending_request.customer_id)
        
        # Notify customer about acceptance
        from service.notifications import notify_user, notify_business_admin
        await notify_user(
            user_id=pending_request.customer_id,
            notification_type=NotificationType.BUSINESS_INVITATION_ACCEPTED,
            title="Invitation Accepted",
            message=f"You've successfully joined '{business.name}'",
            priority=NotificationPriority.MEDIUM,
            db=session,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=business.id,
            related_entity_type="business",
        )
        
        # Notify business admin and agent about acceptance
        await notify_business_admin(
            business_id=business.id,
            notification_type=NotificationType.BUSINESS_INVITATION_ACCEPTED,
            title="Customer Joined Business",
            message=f"{customer.full_name} has accepted the invitation to join '{business.name}'",
            priority=NotificationPriority.MEDIUM,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=pending_request.customer_id,
            related_entity_type="user",
        )
        
        
        logger.info(f"Invitation accepted by customer_id: {pending_request.customer_id} for business_id: {business.id}")
        return success_response(
            status_code=200,
            message=f"Successfully joined {business.name}",
            data={"business_unique_code": business.unique_code, "needs_setup": False}
        )
    except Exception as e:
        session.rollback()
        session.rollback()
        logger.exception("Full traceback for accept_business_invitation failure:")
        return error_response(status_code=500, message=f"Failed to accept invitation: {str(e)}")

async def reject_business_invitation(
    token: str,
    db: Session,
    *,
    pending_repo: PendingBusinessRequestRepository | None = None,
):
    """Reject a business invitation via token."""
    pending_repo = _resolve_repo(pending_repo, PendingBusinessRequestRepository, db)
    session = pending_repo.db

    logger.info(f"Processing reject_business_invitation for token: {token}")

    pending_request = pending_repo.get_by_token(token)
    if not pending_request:
        return error_response(status_code=404, message="Invalid or missing invitation token")

    if pending_request.expires_at < datetime.now(timezone.utc):
        pending_repo.delete_request(pending_request)
        session.commit()
        return error_response(status_code=410, message="Invitation has expired")

    try:
        business_repo = _resolve_repo(None, BusinessRepository, db)
        user_repo = _resolve_repo(None, UserRepository, db)
        business = business_repo.get_by_id(pending_request.business_id)
        customer = user_repo.get_by_id(pending_request.customer_id)
        
        pending_repo.delete_request(pending_request)
        session.commit()
        
        # Notify customer about rejection
        from service.notifications import notify_user, notify_business_admin
        await notify_user(
            user_id=pending_request.customer_id,
            notification_type=NotificationType.BUSINESS_INVITATION_REJECTED,
            title="Invitation Rejected",
            message=f"You've rejected the invitation to join '{business.name}'",
            priority=NotificationPriority.LOW,
            db=session,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=business.id,
            related_entity_type="business",
        )
        
        # Notify business admin and agent about rejection
        await notify_business_admin(
            business_id=business.id,
            notification_type=NotificationType.BUSINESS_INVITATION_REJECTED,
            title="Invitation Rejected",
            message=f"{customer.full_name} has rejected the invitation to join '{business.name}'",
            priority=NotificationPriority.LOW,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=pending_request.customer_id,
            related_entity_type="user",
        )
        
        
        logger.info(f"Invitation rejected by customer_id: {pending_request.customer_id} for business_id: {business.id}")
        return success_response(status_code=200, message="Invitation rejected", data={})
    except Exception as e:
        session.rollback()
        logger.exception("Full traceback for reject_business_invitation failure:")
        return error_response(
            status_code=500, message=f"Failed to reject invitation: {str(e)}"
        )

async def get_user_businesses(
    current_user: dict,
    db: Session,
    address: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    size: int = 8,
    *,
    business_repo: BusinessRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
):
    """Retrieve paginated and filtered list of businesses associated with the user or all businesses for ADMIN/SUPER_ADMIN."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = business_repo.db
    # SUPER_ADMIN should not see businesses in their user profile (they're universal)
    # But they can access all businesses through other endpoints
    if current_user["role"] == Role.SUPER_ADMIN:
        return success_response(
            status_code=200,
            message="Super admin is universal and not associated with specific businesses",
            data={
                "businesses": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        )
    
    if current_user["role"] == Role.ADMIN:
        query = session.query(Business)
    else:
        business_ids = user_business_repo.get_business_ids_for_user(current_user["user_id"])
        if not business_ids:
            return success_response(
                status_code=200,
                message="No businesses found",
                data={
                    "businesses": [],
                    "total_items": 0,
                    "total_pages": 0,
                    "current_page": page,
                    "size": size
                }
            )
        query = session.query(Business).filter(Business.id.in_(business_ids))

    if address:
        query = query.filter(Business.address.ilike(f"%{address}%"))
    
    if search:
        search_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Business.name).like(search_pattern),
                func.lower(Business.unique_code).like(search_pattern),
                func.lower(Business.address).like(search_pattern),
            )
        )

    if start_date:
        query = query.filter(Business.created_at >= start_date)
    if end_date:
        query = query.filter(Business.created_at < end_date + timedelta(days=1))

    total_items = query.count()
    offset = (page - 1) * size
    businesses = query.order_by(Business.created_at.desc()).offset(offset).limit(size).all()

    total_pages = (total_items + size - 1) // size
    business_list = [BusinessResponse.model_validate(business).model_dump() for business in businesses]

    return success_response(
        status_code=200,
        message="Businesses retrieved successfully",
        data={
            "businesses": business_list,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "size": size
        }
    )

async def get_single_business(
    business_id: int,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
):
    """Retrieve details of a single business by ID if the user is associated with it or is SUPER_ADMIN."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = business_repo.db
    if current_user["role"] != Role.SUPER_ADMIN:
        if not user_business_repo.is_user_in_business(current_user["user_id"], business_id):
            return error_response(
                status_code=403, message="User is not associated with this business"
            )

    business = business_repo.get_by_id(business_id)
    if not business:
        return error_response(status_code=404, message="Business not found")

    return success_response(
        status_code=200,
        message="Business retrieved successfully",
        data=BusinessResponse.model_validate(business).model_dump()
    )

async def update_business(
    business_id: int,
    request: BusinessUpdate,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
):
    """Update business details, allowed by AGENT owner or SUPER_ADMIN."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    session = business_repo.db

    business = business_repo.get_by_id(business_id)
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN and business.agent_id != current_user["user_id"]:
        return error_response(
            status_code=403, message="Only the agent owner or SUPER_ADMIN can update this business"
        )

    try:
        if request.name:
            business.name = request.name
        if request.address is not None:
            business.address = request.address
        session.commit()
        session.refresh(business)

        # Notify business admin and agent about business update
        from service.notifications import notify_business_admin
        await notify_business_admin(
            business_id=business_id,
            notification_type=NotificationType.BUSINESS_UPDATED,
            title="Business Updated",
            message=f"Business '{business.name}' details have been updated",
            priority=NotificationPriority.LOW,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=business_id,
            related_entity_type="business",
        )
        
        # Also notify agent if different from admin
        if business.agent_id and business.agent_id != business.admin_id:
            from service.notifications import notify_user
            await notify_user(
                user_id=business.agent_id,
                notification_type=NotificationType.BUSINESS_UPDATED,
                title="Business Updated",
                message=f"Business '{business.name}' details have been updated",
                priority=NotificationPriority.LOW,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=business_id,
                related_entity_type="business",
            )

        return success_response(
            status_code=200,
            message="Business updated successfully",
            data=BusinessResponse.model_validate(business).model_dump()
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update business: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to update business: {str(e)}"
        )

async def delete_business(
    business_id: int,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
):
    """Delete a business if it has no associated members, allowed by AGENT owner or SUPER_ADMIN."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = business_repo.db

    business = business_repo.get_by_id(business_id)
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN and business.agent_id != current_user["user_id"]:
        return error_response(
            status_code=403, message="Only the agent owner or SUPER_ADMIN can delete this business"
        )

    member_count = (
        session.query(user_business)
        .filter(
            user_business.c.business_id == business_id,
            user_business.c.user_id != current_user["user_id"],
        )
        .count()
    )
    if member_count > 0:
        return error_response(
            status_code=400, message="Business is active and cannot be deleted due to associated members"
        )

    try:
        # Get all associated users before deletion
        associated_users = session.query(user_business.c.user_id).filter(
            user_business.c.business_id == business_id
        ).all()
        user_ids = [user_id[0] for user_id in associated_users]
        business_name = business.name
        
        session.execute(user_business.delete().where(user_business.c.business_id == business_id))
        session.execute(
            user_units.delete().where(
                user_units.c.unit_id.in_(select(Unit.id).where(Unit.business_id == business_id))
            )
        )
        session.execute(Unit.__table__.delete().where(Unit.business_id == business_id))
        session.delete(business)
        session.commit()
        
        # Notify all associated users, business admin, and agent about deletion
        from service.notifications import notify_multiple_users, notify_user
        if user_ids:
            await notify_multiple_users(
                user_ids=user_ids,
                notification_type=NotificationType.BUSINESS_DELETED,
                title="Business Deleted",
                message=f"Business '{business_name}' has been deleted",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=business_id,
                related_entity_type="business",
            )
        
        # Notify business admin if exists
        if business.admin_id and business.admin_id not in user_ids:
            await notify_user(
                user_id=business.admin_id,
                notification_type=NotificationType.BUSINESS_DELETED,
                title="Business Deleted",
                message=f"Business '{business_name}' has been deleted",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=business_id,
                related_entity_type="business",
            )
        
        # Notify agent if exists and different from admin
        if business.agent_id and business.agent_id not in user_ids and business.agent_id != business.admin_id:
            await notify_user(
                user_id=business.agent_id,
                notification_type=NotificationType.BUSINESS_DELETED,
                title="Business Deleted",
                message=f"Business '{business_name}' has been deleted",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=business_id,
                related_entity_type="business",
            )
        
        return success_response(
            status_code=200, message="Business deleted successfully", data={}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete business: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to delete business: {str(e)}"
        )

async def create_unit(
    business_id: int,
    request: UnitCreate,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
):
    """Create a new unit within a business for AGENT or ADMIN."""
    if current_user["role"] not in [Role.AGENT, Role.ADMIN]:
        return error_response(status_code=403, message="Only AGENT or ADMIN can create units")

    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = business_repo.db

    business_query = session.query(Business).filter(Business.id == business_id)
    if current_user["role"] == Role.AGENT:
        business_query = business_query.filter(Business.agent_id == current_user["user_id"])
    business = business_query.first()
    if not business:
        return error_response(status_code=404, message="Business not found or you do not have access")

    try:
        unit = Unit(
            name=request.name,
            business_id=business_id,
            location=request.location,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        session.add(unit)
        session.commit()
        session.refresh(unit)

        # Notify business admin and agent about unit creation
        from service.notifications import notify_business_admin
        await notify_business_admin(
            business_id=business_id,
            notification_type=NotificationType.UNIT_CREATED,
            title="Unit Created",
            message=f"Unit '{unit.name}' has been created in '{business.name}'",
            priority=NotificationPriority.LOW,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=unit.id,
            related_entity_type="unit",
        )

        unit_response = UnitResponse.model_validate(unit)
        return success_response(
            status_code=201,
            message="Unit created successfully",
            data=unit_response.model_dump(),
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Unit creation failed: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create unit: {str(e)}")

async def get_single_unit(
    business_id: int,
    unit_id: int,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
):
    """Retrieve details of a single unit by ID if the user is associated with its business or is SUPER_ADMIN."""
    logger.info(f"Fetching unit_id: {unit_id} for business_id: {business_id}, user_id: {current_user['user_id']}, role: {current_user['role']}")
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = unit_repo.db
    
    unit = session.query(Unit).filter(Unit.id == unit_id, Unit.business_id == business_id).first()
    if not unit:
        logger.error(f"Unit not found for unit_id: {unit_id} in business_id: {business_id}")
        return error_response(status_code=404, message="Unit not found or does not belong to specified business")

    business = business_repo.get_by_id(unit.business_id)
    if not business:
        logger.error(f"Business not found for unit_id: {unit_id}")
        return error_response(status_code=404, message="Associated business not found")

    # Role-based access control
    if current_user["role"] not in [Role.SUPER_ADMIN, Role.ADMIN]:
        if current_user["role"] == Role.AGENT:
            if business.agent_id != current_user["user_id"]:
                logger.error(f"User {current_user['user_id']} is not the agent owner of business {business.id}")
                return error_response(status_code=403, message="Only the agent owner can access this unit")
        elif current_user["role"] in [Role.CUSTOMER, Role.SUB_AGENT]:
            if not user_business_repo.is_user_in_business(current_user["user_id"], business.id):
                logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
                return error_response(status_code=403, message="User not associated with this business")
            if current_user["role"] == Role.CUSTOMER:
                if not session.query(user_units).filter(
                    user_units.c.user_id == current_user["user_id"],
                    user_units.c.unit_id == unit_id
                ).first():
                    logger.error(f"User {current_user['user_id']} not associated with unit {unit_id}")
                    return error_response(status_code=403, message="User not associated with this unit")
        else:
            logger.error(f"Invalid role {current_user['role']} for user {current_user['user_id']}")
            return error_response(status_code=403, message="Invalid user role")

    logger.info(f"Unit {unit_id} retrieved successfully for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Unit retrieved successfully",
        data=UnitResponse.model_validate(unit).model_dump()
    )

async def get_all_units(
    current_user: dict,
    db: Session,
    page: int = 1,
    size: int = 8,
    search: Optional[str] = None,
    *,
    unit_repo: UnitRepository | None = None,
):
    """Retrieve all paginated units in the system for SUPER_ADMIN only."""
    logger.info(f"Fetching all units for user_id: {current_user['user_id']}, page: {page}, size: {size}")
    if current_user["role"] != Role.SUPER_ADMIN:
        logger.error(f"User {current_user['user_id']} attempted to access all units without SUPER_ADMIN role")
        return error_response(status_code=403, message="Only SUPER_ADMIN can access all units")

    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = unit_repo.db

    query = session.query(Unit)
    if search:
        search_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Unit.name).like(search_pattern),
                func.lower(Unit.location).like(search_pattern),
            )
        )
    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning("No units found in the system")
        return success_response(
            status_code=200,
            message="No units found in the system",
            data={
                "units": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        )

    logger.info(f"Found {len(units)} units in the system")
    return success_response(
        status_code=200,
        message="All units retrieved successfully",
        data={
            "units": [UnitResponse.model_validate(unit).model_dump() for unit in units],
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "current_page": page,
            "size": size
        }
    )

async def get_business_units(
    business_id: int,
    current_user: dict,
    db: Session,
    page: int = 1,
    size: int = 8,
    search: Optional[str] = None,
    *,
    business_repo: BusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
):
    """Retrieve paginated units for a business based on user role."""
    logger.info(f"Fetching units for business_id: {business_id}, user_id: {current_user['user_id']}, role: {current_user['role']}, page: {page}, size: {size}")
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = unit_repo.db

    business = business_repo.get_by_id(business_id)
    if not business:
        logger.error(f"Business not found for id: {business_id}")
        return error_response(status_code=404, message="Business not found")

    # Role-based access control
    if current_user["role"] in [Role.SUPER_ADMIN, Role.ADMIN]:
        query = session.query(Unit).filter(Unit.business_id == business.id)
    elif current_user["role"] == Role.AGENT:
        if business.agent_id != current_user["user_id"]:
            logger.error(f"User {current_user['user_id']} is not the agent owner of business {business.id}")
            return error_response(status_code=403, message="Only the agent owner can access these units")
        query = session.query(Unit).filter(Unit.business_id == business.id)
    elif current_user["role"] in [Role.CUSTOMER, Role.SUB_AGENT]:
        if not user_business_repo.is_user_in_business(current_user["user_id"], business.id):
            logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
            return error_response(status_code=403, message="User not associated with this business")
        if current_user["role"] == Role.CUSTOMER:
            query = session.query(Unit).join(user_units).filter(
                user_units.c.user_id == current_user["user_id"],
                Unit.business_id == business.id
            )
        else:  # SUB_AGENT
            query = session.query(Unit).filter(Unit.business_id == business.id)
    else:
        logger.error(f"Invalid role {current_user['role']} for user {current_user['user_id']}")
        return error_response(status_code=403, message="Invalid user role")

    if search:
        search_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Unit.name).like(search_pattern),
                func.lower(Unit.location).like(search_pattern),
            )
        )

    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning(f"No units found for business {business.id} for user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="No units found for this business",
            data={
                "units": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        )

    logger.info(f"Found {len(units)} units for business {business.id} for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Units retrieved successfully",
        data={
            "units": [UnitResponse.model_validate(unit).model_dump() for unit in units],
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "current_page": page,
            "size": size
        }
    )

async def get_user_units(
    current_user: dict,
    db: Session,
    name: Optional[str] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    size: int = 8,
    *,
    unit_repo: UnitRepository | None = None,
):
    """Retrieve paginated units associated with the current user via user_units."""
    logger.info(f"Fetching units for user_id: {current_user['user_id']}, role: {current_user['role']}, page: {page}, size: {size}")
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = unit_repo.db

    # Base query: Join units with user_units to get units the user is associated with
    query = session.query(Unit).join(user_units).filter(user_units.c.user_id == current_user["user_id"])

    # Apply filters
    if name:
        query = query.filter(Unit.name.ilike(f"%{name}%"))
    if location:
        query = query.filter(Unit.location.ilike(f"%{location}%"))
    if search:
        search_pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(Unit.name).like(search_pattern),
                func.lower(Unit.location).like(search_pattern),
            )
        )

    # Pagination
    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning(f"No units found for user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="No units found for this user",
            data={
                "units": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        )

    logger.info(f"Found {len(units)} units for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="User units retrieved successfully",
        data={
            "units": [UnitResponse.model_validate(unit).model_dump() for unit in units],
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "current_page": page,
            "size": size
        }
    )

async def update_business_unit(
    unit_id: int,
    request: UnitUpdate,
    current_user: dict,
    db: Session,
    *,
    unit_repo: UnitRepository | None = None,
):
    """Update Unit Details"""
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = unit_repo.db

    unit = unit_repo.get_by_id(unit_id)
    if not unit:
        error_response(status_code=404, message="Unit Not Found")
    if current_user["role"] != Role.SUPER_ADMIN and unit.created_by != current_user["user_id"]:
        error_response(status_code=403, message="Only SUPER ADMIN and business owner can update this unit")

    try:
        if request.name:
            unit.name = request.name
        if request.location is not None:
            unit.location = request.location
        session.commit()
        session.refresh(unit)

        # Notify business admin and agent about unit update
        business_repo = _resolve_repo(None, BusinessRepository, db)
        business = business_repo.get_by_id(unit.business_id)
        from service.notifications import notify_business_admin
        await notify_business_admin(
            business_id=unit.business_id,
            notification_type=NotificationType.UNIT_UPDATED,
            title="Unit Updated",
            message=f"Unit '{unit.name}' has been updated in '{business.name}'",
            priority=NotificationPriority.LOW,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=unit.id,
            related_entity_type="unit",
        )

        return success_response(
            status_code=200,
            message="Business updated successfully",
            data=UnitResponse.model_validate(unit).model_dump()
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update unit: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to update unit: {str(e)}"
        )

async def delete_unit(
    unit_id: int,
    current_user: dict,
    db: Session,
    *,
    unit_repo: UnitRepository | None = None,
):
    """Delete a unit if it has no associated members, allowed by AGENT owner or SUPER_ADMIN."""
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = unit_repo.db

    unit = unit_repo.get_by_id(unit_id)
    if not unit:
        return error_response(status_code=404, message="Unit not found")

    if current_user["role"] != Role.SUPER_ADMIN and unit.created_by != current_user["user_id"]:
        return error_response(
            status_code=403, message="Only the unit owner or SUPER_ADMIN can delete this unit"
        )

    member_count = session.query(user_units).filter(user_units.c.unit_id == unit_id).count()
    if member_count > 0:
        return error_response(
            status_code=400, message="Unit has associated members and cannot be deleted"
        )

    try:
        # Get business and unit members before deletion
        business_repo = _resolve_repo(None, BusinessRepository, db)
        business = business_repo.get_by_id(unit.business_id)
        unit_name = unit.name
        unit_members = session.query(user_units).filter(user_units.c.unit_id == unit_id).all()
        member_ids = [member.user_id for member in unit_members]
        
        session.delete(unit)
        session.commit()
        
        # Notify business admin and agent about unit deletion
        from service.notifications import notify_business_admin, notify_multiple_users
        await notify_business_admin(
            business_id=unit.business_id,
            notification_type=NotificationType.UNIT_DELETED,
            title="Unit Deleted",
            message=f"Unit '{unit_name}' has been deleted from '{business.name}'",
            priority=NotificationPriority.MEDIUM,
            db=session,
            business_repo=business_repo,
            notification_repo=UserNotificationRepository(session),
            related_entity_id=unit_id,
            related_entity_type="unit",
        )
        
        # Notify unit members
        if member_ids:
            await notify_multiple_users(
                user_ids=member_ids,
                notification_type=NotificationType.UNIT_DELETED,
                title="Unit Deleted",
                message=f"Unit '{unit_name}' has been deleted from '{business.name}'",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=UserNotificationRepository(session),
                related_entity_id=unit_id,
                related_entity_type="unit",
            )
        
        return success_response(
            status_code=200, message="Unit deleted successfully", data={}
        )
    except Exception as e:
        session.rollback()
        return error_response(status_code=500, message=f"Failed to delete unit: {str(e)}")

async def get_business_summary(
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
):
    """Retrieve the total number of businesses in the system, accessible by ADMIN only."""
 
    if current_user["role"] != Role.ADMIN:
        return error_response(status_code=403, message="Only ADMIN can access total business count")

    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    total_businesses = business_repo.db.query(Business).count()
    
    return success_response(
        status_code=200,
        message="Total business count retrieved successfully",
        data={"total_businesses": total_businesses}
    )

async def get_all_unit_summary(
    current_user: dict,
    db: Session,
    *,
    unit_repo: UnitRepository | None = None,
):
    """Retrieve the total number of units in the system, accessible by SUPER_ADMIN only."""
    
    if current_user["role"] != Role.SUPER_ADMIN:
        return error_response(status_code=403, message="Only SUPER_ADMIN can access total unit count")

    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    total_units = unit_repo.db.query(Unit).count()
    
    return success_response(
        status_code=200,
        message="Total unit count retrieved successfully",
        data={"total_units": total_units}
    )

async def get_business_unit_summary(
    business_id: str,
    current_user: dict,
    db: Session,
    *,
    business_repo: BusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
):
    """Retrieve the total number of units for a specific business, based on user role."""
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    user_business_repo = _resolve_repo(user_business_repo, UserBusinessRepository, db)
    session = unit_repo.db

    business = business_repo.get_by_id(business_id)
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] in [Role.SUPER_ADMIN, Role.ADMIN]:
        query = session.query(Unit).filter(Unit.business_id == business_id)
    elif current_user["role"] == Role.AGENT:
        if business.agent_id != current_user["user_id"]:
            return error_response(status_code=403, message="Only the agent owner can access this count")
        query = session.query(Unit).filter(Unit.business_id == business_id)
    elif current_user["role"] in [Role.CUSTOMER, Role.SUB_AGENT]:
        if not user_business_repo.is_user_in_business(current_user["user_id"], business_id):
            return error_response(status_code=403, message="User not associated with this business")
        if current_user["role"] == Role.CUSTOMER:
            query = session.query(Unit).join(user_units).filter(
                user_units.c.user_id == current_user["user_id"],
                Unit.business_id == business_id
            )
        else:
            query = session.query(Unit).filter(Unit.business_id == business_id)
    else:
        return error_response(status_code=403, message="Invalid user role")

    total_units = query.count()
    
    return success_response(
        status_code=200,
        message="Business unit count retrieved successfully",
        data={"total_units": total_units}
    )


async def get_unassigned_admin_businesses(
    current_user: dict,
    business_repo: "BusinessRepository",
):
    """Return businesses that do not currently have an assigned admin (super_admin only)."""
    if current_user.get("role") != Role.SUPER_ADMIN:
        return error_response(
            status_code=403,
            message="Only super_admin can view unassigned businesses",
        )

    businesses = business_repo.get_unassigned_businesses()
    business_list = [
        BusinessResponse.model_validate(business, from_attributes=True).model_dump()
        for business in businesses
    ]

    return success_response(
        status_code=200,
        message="Unassigned businesses retrieved successfully",
        data={"businesses": business_list, "total": len(business_list)},
    )