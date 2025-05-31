from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from sqlalchemy import select
from models.business import Business, PendingBusinessRequest, Unit, user_units
from models.user_business import user_business
from models.user import User, Role, Permission
from utils.response import success_response, error_response
from schemas.business import BusinessCreate, BusinessResponse, BusinessUpdate, UnitCreate, UnitResponse, CustomerInvite
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
    if current_user["role"] not in [Role.AGENT, Role.SUPER_ADMIN]:
        return error_response(status_code=403, message="Only AGENT or SUPER_ADMIN can create businesses")
    if current_user["role"] != Role.SUPER_ADMIN and not has_permission(current_user_obj, Permission.CREATE_BUSINESS, db):
        return error_response(status_code=403, message="No permission to create business")

    if current_user["role"] != Role.SUPER_ADMIN and db.query(Business).filter(Business.agent_id == current_user["user_id"]).first():
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
        db.commit()
        db.refresh(business)

        if request.address:
            unit = Unit(
                name=f"{request.name} Default Unit",
                business_id=business.id,
                location=request.address,
                created_by=None,
                created_at=datetime.now(timezone.utc),
            )
            db.add(unit)
            db.commit()

        db.execute(
            insert(user_business).values(user_id=current_user["user_id"], business_id=business.id)
        )
        db.commit()

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
        return success_response(
            status_code=201,
            message=f"Business created. Unique code: {unique_code}",
            data=business_response.model_dump(),
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

        accept_url = f"{settings.APP_BASE_URL}/api/v1/business/accept-invitation?token={token}"
        reject_url = f"{settings.APP_BASE_URL}/api/v1/business/reject-invitation?token={token}"
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
    """Retrieve paginated and filtered list of businesses associated with the user or all businesses for SUPER_ADMIN."""
    if current_user["role"] == Role.SUPER_ADMIN:
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

async def create_unit(business_id: int, request: UnitCreate, db: Session, current_user: dict):
    """Create a new unit within a business for AGENT or SUPER_ADMIN."""
    if current_user["role"] not in [Role.AGENT, Role.SUPER_ADMIN]:
        return error_response(status_code=403, message="Only AGENT or SUPER_ADMIN can create units")

    business = db.query(Business).filter(
        Business.id == business_id,
        Business.agent_id == current_user["user_id"] if current_user["role"] != Role.SUPER_ADMIN else True
    ).first()
    if not business:
        return error_response(status_code=404, message="Business not found or you do not have access")

    try:
        unit = Unit(
            name=request.name,
            business_id=business_id,
            location=request.location,
            created_by=None,
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

async def get_business_units(business_unique_code: str, current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve paginated units for a business for associated users or SUPER_ADMIN."""
    logger.info(f"Fetching units for business_unique_code: {business_unique_code}, user_id: {current_user['user_id']}, page: {page}, size: {size}")
    business = db.query(Business).filter(Business.unique_code.ilike(business_unique_code)).first()
    if not business:
        logger.error(f"Business not found for unique_code: {business_unique_code}")
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business.id
        ).first():
            logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
            return error_response(status_code=403, message="User not associated with this business")

    query = db.query(Unit).filter(Unit.business_id == business.id)
    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning(f"No units found for business {business.id}")
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

    logger.info(f"Found {len(units)} units for business {business.id}")
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

async def get_all_units(current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve all paginated units in the system for SUPER_ADMIN only."""
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

async def get_agent_business_units(business_unique_code: str, current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve all paginated units for a business for the AGENT owner or SUPER_ADMIN."""
    if current_user["role"] not in [Role.AGENT, Role.SUPER_ADMIN]:
        logger.error(f"User {current_user['user_id']} attempted to access agent units without AGENT or SUPER_ADMIN role")
        return error_response(status_code=403, message="Only AGENT or SUPER_ADMIN can access business units")

    business = db.query(Business).filter(Business.unique_code.ilike(business_unique_code)).first()
    if not business:
        logger.error(f"Business not found for unique_code: {business_unique_code}")
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN and business.agent_id != current_user["user_id"]:
        logger.error(f"User {current_user['user_id']} is not the agent owner of business {business.id}")
        return error_response(status_code=403, message="Only the agent owner or SUPER_ADMIN can access these units")

    query = db.query(Unit).filter(Unit.business_id == business.id)
    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning(f"No units found for business {business.id}")
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

    logger.info(f"Found {len(units)} units for business {business.id}")
    return success_response(
        status_code=200,
        message="Agent units retrieved successfully",
        data={
            "units": [UnitResponse.model_validate(unit).model_dump() for unit in units],
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "current_page": page,
            "size": size
        }
    )

async def get_customer_business_units(business_unique_code: str, current_user: dict, db: Session, page: int = 1, size: int = 8):
    """Retrieve paginated units associated with a CUSTOMER or SUPER_ADMIN in a business."""
    if current_user["role"] not in [Role.CUSTOMER, Role.SUPER_ADMIN]:
        logger.error(f"User {current_user['user_id']} attempted to access customer units without CUSTOMER or SUPER_ADMIN role")
        return error_response(status_code=403, message="Only CUSTOMER or SUPER_ADMIN can access their associated units")

    business = db.query(Business).filter(Business.unique_code.ilike(business_unique_code)).first()
    if not business:
        logger.error(f"Business not found for unique_code: {business_unique_code}")
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] != Role.SUPER_ADMIN:
        if not db.query(user_business).filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business.id
        ).first():
            logger.error(f"User {current_user['user_id']} not associated with business {business.id}")
            return error_response(status_code=403, message="User not associated with this business")

    if current_user["role"] == Role.SUPER_ADMIN:
        query = db.query(Unit).filter(Unit.business_id == business.id)
    else:
        query = db.query(Unit).join(user_units).filter(
            user_units.c.user_id == current_user["user_id"],
            Unit.business_id == business.id
        )

    total_items = query.count()
    offset = (page - 1) * size
    units = query.order_by(Unit.created_at.desc()).offset(offset).limit(size).all()

    if not units:
        logger.warning(f"No units found for user {current_user['user_id']} in business {business.id}")
        return success_response(
            status_code=200,
            message="No units found for this customer in the business",
            data={
                "units": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        )

    logger.info(f"Found {len(units)} units for user {current_user['user_id']} in business {business.id}")
    return success_response(
        status_code=200,
        message="Customer units retrieved successfully",
        data={
            "units": [UnitResponse.model_validate(unit).model_dump() for unit in units],
            "total_items": total_items,
            "total_pages": (total_items + size - 1) // size,
            "current_page": page,
            "size": size
        }
    )