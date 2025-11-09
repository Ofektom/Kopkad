from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from sqlalchemy import select
from models.business import Business, PendingBusinessRequest, Unit, user_units, AdminCredentials, BusinessPermission
from models.user_business import user_business
from models.user import User, Role, Permission
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions

async def create_business(request: BusinessCreate, current_user: dict, db: Session):
    """Create a thrift business."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")
    if current_user["role"] != Role.AGENT:
        return error_response(status_code=403, message="Only AGENT can create businesses")
    if not has_permission(current_user_obj, Permission.CREATE_BUSINESS, db):
        return error_response(status_code=403, message="No permission to create business")

    if db.query(Business).filter(Business.agent_id == current_user["user_id"]).first():
        return error_response(status_code=403, message="User can only own one business")

    characters = string.digits + string.ascii_letters
    max_attempts = 100
    for _ in range(max_attempts):
        unique_code = "".join(random.choice(characters) for _ in range(6))
        if not db.query(Business).filter(Business.unique_code == unique_code).first():
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
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(business)
        db.flush()  # Get business.id before creating admin
        
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
        db.add(admin_user)
        db.flush()  # Get admin_user.id
        
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
        db.add(admin_credentials_record)
        
        # 5. Grant business-scoped permissions to admin
        grant_admin_permissions(admin_user.id, business.id, current_user["user_id"], db)
        
        # 6. Create default unit (existing logic)
        if request.address:
            unit = Unit(
                name=f"{request.name} Default Unit",
                business_id=business.id,
                location=request.address,
                created_by=current_user["user_id"],
                created_at=datetime.now(timezone.utc),
            )
            db.add(unit)
        
        # 7. Link agent to business (existing logic)
        db.execute(
            insert(user_business).values(user_id=current_user["user_id"], business_id=business.id)
        )
        
        db.commit()
        db.refresh(business)

        user = db.query(User).filter(User.id == current_user["user_id"]).first()
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
        db.rollback()
        logger.error(f"Failed to create business: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create business: {str(e)}")

async def add_customer_to_business(
    request: CustomerInvite, current_user: dict, db: Session
):
    """Add an existing customer to a business for AGENT, SUB_AGENT, or SUPER_ADMIN."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")
    if current_user["role"] not in [Role.AGENT, Role.SUB_AGENT, Role.SUPER_ADMIN]:
        return error_response(
            status_code=403, message="Only AGENT, SUB_AGENT, or SUPER_ADMIN can add customers to a business"
        )
    if current_user["role"] != Role.SUPER_ADMIN and not has_permission(current_user_obj, Permission.ASSIGN_BUSINESS, db):
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

    customer = db.query(User).filter(
        User.phone_number == phone_number, User.role == Role.CUSTOMER
    ).first()
    if not customer:
        return error_response(status_code=404, message="Customer not found or not a CUSTOMER role")

    business = db.query(Business).filter(Business.unique_code == request.business_unique_code).first()
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] == Role.AGENT and business.agent_id != current_user["user_id"]:
        return error_response(
            status_code=403, message="Agent must be the owner of the business to add customers"
        )
    if current_user["role"] == Role.SUB_AGENT:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business.id
        ).first():
            return error_response(
                status_code=403, message="Sub-agent not found in this business"
            )

    if db.query(user_business).filter(
        user_business.c.user_id == customer.id,
        user_business.c.business_id == business.id
    ).first():
        return error_response(
            status_code=409, message="Customer already associated with this business"
        )

    if request.unit_id:
        unit = db.query(Unit).filter(
            Unit.id == request.unit_id, Unit.business_id == business.id
        ).first()
        if not unit:
            return error_response(status_code=404, message="Unit not found in this business")

    try:
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        pending_request = PendingBusinessRequest(
            customer_id=customer.id,
            business_id=business.id,
            unit_id=request.unit_id,
            token=token,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc)
        )
        db.add(pending_request)
        db.commit()

        accept_url = f"{settings.APP_BASE_URL}/business/accept-invitation?token={token}"
        reject_url = f"{settings.APP_BASE_URL}/business/reject-invitation?token={token}"
        notification_method = customer.settings.notification_method if customer.settings else "both"
        delivery_method = []

        if notification_method in ["email", "both"] and customer.email:
            await send_business_invitation_email(
                customer.email, customer.full_name, business.name, accept_url, reject_url
            )
            delivery_method.append("email")

        if not delivery_method:
            return error_response(
                status_code=500, message="No valid notification method available"
            )

        return success_response(
            status_code=200,
            message=f"Invitation sent to customer {customer.full_name} via {', '.join(delivery_method)}, it expires in 24 hours",
            data={"status": "pending", "expires_at": expires_at.isoformat()}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initiate customer invitation: {str(e)}")
        return error_response(status_code=500, message=f"Failed to process invitation: {str(e)}")

async def accept_business_invitation(token: str, db: Session):
    """Accept a business invitation via token."""
    pending_request = db.query(PendingBusinessRequest).filter(
        PendingBusinessRequest.token == token
    ).first()
    if not pending_request:
        return error_response(status_code=404, message="Invalid or missing invitation token")

    if pending_request.expires_at < datetime.now(timezone.utc):
        db.delete(pending_request)
        db.commit()
        return error_response(status_code=410, message="Invitation has expired")

    try:
        db.execute(
            insert(user_business).values(
                user_id=pending_request.customer_id,
                business_id=pending_request.business_id
            )
        )
        if pending_request.unit_id:
            db.execute(
                insert(user_units).values(
                    user_id=pending_request.customer_id,
                    unit_id=pending_request.unit_id
                )
            )
        db.delete(pending_request)
        db.commit()

        business = db.query(Business).filter(
            Business.id == pending_request.business_id
        ).first()
        return success_response(
            status_code=200,
            message=f"Successfully joined {business.name}",
            data={"business_unique_code": business.unique_code}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to accept invitation: {str(e)}")
        return error_response(status_code=500, message=f"Failed to accept invitation: {str(e)}")

async def reject_business_invitation(token: str, db: Session):
    """Reject a business invitation via token."""
    pending_request = db.query(PendingBusinessRequest).filter(
        PendingBusinessRequest.token == token
    ).first()
    if not pending_request:
        return error_response(status_code=404, message="Invalid or missing invitation token")

    if pending_request.expires_at < datetime.now(timezone.utc):
        db.delete(pending_request)
        db.commit()
        return error_response(status_code=410, message="Invitation has expired")

    try:
        db.delete(pending_request)
        db.commit()
        return success_response(status_code=200, message="Invitation rejected", data={})
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reject invitation: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to reject invitation: {str(e)}"
        )

async def get_user_businesses(
    current_user: dict,
    db: Session,
    address: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    size: int = 8
):
    """Retrieve paginated and filtered list of businesses associated with the user or all businesses for ADMIN/SUPER_ADMIN."""
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
        query = db.query(Business)
    else:
        business_ids = [
            row[0] for row in db.query(user_business.c.business_id)
            .filter(user_business.c.user_id == current_user["user_id"]).all()
        ]
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
        query = db.query(Business).filter(Business.id.in_(business_ids))

    if address:
        query = query.filter(Business.address.ilike(f"%{address}%"))

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

async def get_single_business(business_id: int, current_user: dict, db: Session):
    """Retrieve details of a single business by ID if the user is associated with it or is SUPER_ADMIN."""
    if current_user["role"] != Role.SUPER_ADMIN:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business_id
        ).first():
            return error_response(
                status_code=403, message="User is not associated with this business"
            )

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return error_response(status_code=404, message="Business not found")

    return success_response(
        status_code=200,
        message="Business retrieved successfully",
        data=BusinessResponse.model_validate(business).model_dump()
    )

async def update_business(business_id: int, request: BusinessUpdate, current_user: dict, db: Session):
    """Update business details, allowed by AGENT owner or SUPER_ADMIN."""
    business = db.query(Business).filter(Business.id == business_id).first()
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
        db.commit()
        db.refresh(business)

        return success_response(
            status_code=200,
            message="Business updated successfully",
            data=BusinessResponse.model_validate(business).model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update business: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to update business: {str(e)}"
        )

async def delete_business(business_id: int, current_user: dict, db: Session):
    """Delete a business if it has no associated members, allowed by AGENT owner or SUPER_ADMIN."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN and business.agent_id != current_user["user_id"]:
        return error_response(
            status_code=403, message="Only the agent owner or SUPER_ADMIN can delete this business"
        )

    member_count = db.query(user_business).filter(
        user_business.c.business_id == business_id,
        user_business.c.user_id != current_user["user_id"]
    ).count()
    if member_count > 0:
        return error_response(
            status_code=400, message="Business is active and cannot be deleted due to associated members"
        )

    try:
        db.execute(user_business.delete().where(user_business.c.business_id == business_id))
        db.execute(user_units.delete().where(user_units.c.unit_id.in_(
            select(Unit.id).where(Unit.business_id == business_id)
        )))
        db.execute(Unit.__table__.delete().where(Unit.business_id == business_id))
        db.delete(business)
        db.commit()
        return success_response(
            status_code=200, message="Business deleted successfully", data={}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete business: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to delete business: {str(e)}"
        )

async def create_unit(business_id: int, request: UnitCreate, current_user: dict, db: Session):
    """Create a new unit within a business for AGENT or ADMIN."""
    if current_user["role"] not in [Role.AGENT, Role.ADMIN]:
        return error_response(status_code=403, message="Only AGENT or ADMIN can create units")

    business = db.query(Business).filter(
        Business.id == business_id,
        Business.agent_id == current_user["user_id"] if current_user["role"] == Role.AGENT else True
    ).first()
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
        db.add(unit)
        db.commit()
        db.refresh(unit)

        unit_response = UnitResponse.model_validate(unit)
        return success_response(
            status_code=201,
            message="Unit created successfully",
            data=unit_response.model_dump(),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Unit creation failed: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create unit: {str(e)}")

async def get_single_unit(business_id: int, unit_id: int, current_user: dict, db: Session):
    """Retrieve details of a single unit by ID if the user is associated with its business or is SUPER_ADMIN."""
    logger.info(f"Fetching unit_id: {unit_id} for business_id: {business_id}, user_id: {current_user['user_id']}, role: {current_user['role']}")
    
    unit = db.query(Unit).filter(Unit.id == unit_id, Unit.business_id == business_id).first()
    if not unit:
        logger.error(f"Unit not found for unit_id: {unit_id} in business_id: {business_id}")
        return error_response(status_code=404, message="Unit not found or does not belong to specified business")

    business = db.query(Business).filter(Business.id == unit.business_id).first()
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
            if not db.query(user_business).filter(
                user_business.c.user_id == current_user["user_id"],
                user_business.c.business_id == business.id
            ).first():
                logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
                return error_response(status_code=403, message="User not associated with this business")
            if current_user["role"] == Role.CUSTOMER:
                if not db.query(user_units).filter(
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

async def get_all_units(current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve all paginated units in the system for SUPER_ADMIN only."""
    logger.info(f"Fetching all units for user_id: {current_user['user_id']}, page: {page}, size: {size}")
    if current_user["role"] != Role.SUPER_ADMIN:
        logger.error(f"User {current_user['user_id']} attempted to access all units without SUPER_ADMIN role")
        return error_response(status_code=403, message="Only SUPER_ADMIN can access all units")

    query = db.query(Unit)
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

async def get_business_units(business_id: int, current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve paginated units for a business based on user role."""
    logger.info(f"Fetching units for business_id: {business_id}, user_id: {current_user['user_id']}, role: {current_user['role']}, page: {page}, size: {size}")
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        logger.error(f"Business not found for id: {business_id}")
        return error_response(status_code=404, message="Business not found")

    # Role-based access control
    if current_user["role"] in [Role.SUPER_ADMIN, Role.ADMIN]:
        query = db.query(Unit).filter(Unit.business_id == business.id)
    elif current_user["role"] == Role.AGENT:
        if business.agent_id != current_user["user_id"]:
            logger.error(f"User {current_user['user_id']} is not the agent owner of business {business.id}")
            return error_response(status_code=403, message="Only the agent owner can access these units")
        query = db.query(Unit).filter(Unit.business_id == business.id)
    elif current_user["role"] in [Role.CUSTOMER, Role.SUB_AGENT]:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business.id
        ).first():
            logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
            return error_response(status_code=403, message="User not associated with this business")
        if current_user["role"] == Role.CUSTOMER:
            query = db.query(Unit).join(user_units).filter(
                user_units.c.user_id == current_user["user_id"],
                Unit.business_id == business.id
            )
        else:  # SUB_AGENT
            query = db.query(Unit).filter(Unit.business_id == business.id)
    else:
        logger.error(f"Invalid role {current_user['role']} for user {current_user['user_id']}")
        return error_response(status_code=403, message="Invalid user role")

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
    page: int = 1,
    size: int = 8
):
    """Retrieve paginated units associated with the current user via user_units."""
    logger.info(f"Fetching units for user_id: {current_user['user_id']}, role: {current_user['role']}, page: {page}, size: {size}")
    
    # Base query: Join units with user_units to get units the user is associated with
    query = db.query(Unit).join(user_units).filter(user_units.c.user_id == current_user["user_id"])

    # Apply filters
    if name:
        query = query.filter(Unit.name.ilike(f"%{name}%"))
    if location:
        query = query.filter(Unit.location.ilike(f"%{location}%"))

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

async def update_business_unit(unit_id: int, request: UnitUpdate, current_user: dict, db: Session):
    """Update Unit Details"""
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if not unit:
        error_response(status_code=404, message="Unit Not Found")
    if current_user["role"] != Role.SUPER_ADMIN and unit.created_by != current_user["user_id"]:
        error_response(status_code=403, message="Only SUPER ADMIN and business owner can update this unit")

    try:
        if request.name:
            unit.name = request.name
        if request.location is not None:
            unit.location = request.location
        db.commit()
        db.refresh(unit)

        return success_response(
            status_code=200,
            message="Business updated successfully",
            data=UnitResponse.model_validate(unit).model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update unit: {str(e)}")
        return error_response(
            status_code=500, message=f"Failed to update unit: {str(e)}"
        )

async def delete_unit(unit_id: int, current_user: dict, db: Session):
    """Delete a unit if it has no associated members, allowed by AGENT owner or SUPER_ADMIN."""
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if not unit:
        return error_response(status_code=404, message="Unit not found")

    if current_user["role"] != Role.SUPER_ADMIN and unit.created_by != current_user["user_id"]:
        return error_response(
            status_code=403, message="Only the unit owner or SUPER_ADMIN can delete this unit"
        )

    member_count = db.query(user_units).filter(user_units.c.unit_id == unit_id).count()
    if member_count > 0:
        return error_response(
            status_code=400, message="Unit has associated members and cannot be deleted"
        )

    try:
        db.delete(unit)
        db.commit()
        return success_response(
            status_code=200, message="Unit deleted successfully", data={}
        )
    except Exception as e:
        db.rollback()
        return error_response(status_code=500, message=f"Failed to delete unit: {str(e)}")

async def get_business_summary(current_user: dict, db: Session):
    """Retrieve the total number of businesses in the system, accessible by ADMIN only."""
 
    if current_user["role"] != Role.ADMIN:
        return error_response(status_code=403, message="Only ADMIN can access total business count")

    total_businesses = db.query(Business).count()
    
    return success_response(
        status_code=200,
        message="Total business count retrieved successfully",
        data={"total_businesses": total_businesses}
    )

async def get_all_unit_summary(current_user: dict, db: Session):
    """Retrieve the total number of units in the system, accessible by SUPER_ADMIN only."""
    
    if current_user["role"] != Role.SUPER_ADMIN:
        return error_response(status_code=403, message="Only SUPER_ADMIN can access total unit count")

    total_units = db.query(Unit).count()
    
    return success_response(
        status_code=200,
        message="Total unit count retrieved successfully",
        data={"total_units": total_units}
    )

async def get_business_unit_summary(business_id: str, current_user: dict, db: Session):
    """Retrieve the total number of units for a specific business, based on user role."""
  
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] in [Role.SUPER_ADMIN, Role.ADMIN]:
        query = db.query(Unit).filter(Unit.business_id == business_id)
    elif current_user["role"] == Role.AGENT:
        if business.agent_id != current_user["user_id"]:
            return error_response(status_code=403, message="Only the agent owner can access this count")
        query = db.query(Unit).filter(Unit.business_id == business_id)
    elif current_user["role"] in [Role.CUSTOMER, Role.SUB_AGENT]:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business_id
        ).first():
            return error_response(status_code=403, message="User not associated with this business")
        if current_user["role"] == Role.CUSTOMER:
            query = db.query(Unit).join(user_units).filter(
                user_units.c.user_id == current_user["user_id"],
                Unit.business_id == business_id
            )
        else:
            query = db.query(Unit).filter(Unit.business_id == business_id)
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