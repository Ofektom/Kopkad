from sqlalchemy.orm import Session
from sqlalchemy.sql import insert
from models.business import Business, PendingBusinessRequest
from models.user_business import user_business
from models.user import User, Role, Permission
from utils.response import success_response, error_response
from schemas.business import BusinessCreate, BusinessResponse
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

def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions

async def create_business(request: BusinessCreate, current_user: dict, db: Session):
    """Create a business, only allowed by AGENT."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.CREATE_BUSINESS, db):
        return error_response(status_code=403, message="No permission to create business")
    if current_user["role"] != Role.AGENT:
        return error_response(
            status_code=403, message="Only AGENT can create businesses"
        )

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
            status_code=500,
            message="Unable to generate unique code after multiple attempts",
        )

    try:
        business = Business(
            name=request.name,
            agent_id=current_user["user_id"],
            location=request.location,
            unique_code=unique_code,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(business)
        db.commit()
        db.refresh(business)

        db.execute(
            insert(user_business).values(
                user_id=current_user["user_id"], business_id=business.id
            )
        )
        db.commit()

        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        notification_method = (
            user.settings.notification_method if user.settings else "both"
        )
        delivery_status = "sent_to_"
        if user.phone_number and notification_method in ["whatsapp", "both"]:
            delivery_status += "whatsapp"
        if user.email and notification_method in ["email", "both"]:
            delivery_status += "_and_email"
            await send_business_created_email(
                user.email,
                user.full_name,
                business.name,
                business.unique_code,
                business.created_at.isoformat(),
            )
        if not user.phone_number and not user.email:
            delivery_status = "pending"

        return success_response(
            status_code=201,
            message=f"Business created. Unique code: {unique_code}",
            data=BusinessResponse(
                id=business.id,
                name=business.name,
                location=business.location,
                unique_code=unique_code,
                created_at=business.created_at,
                delivery_status=delivery_status,
            ).model_dump(),
        )
    except Exception as e:
        db.rollback()
        return error_response(
            status_code=500, message=f"Failed to create business: {str(e)}"
        )


async def add_customer_to_business(
    customer_phone: str, business_unique_code: str, current_user: dict, db: Session
):
    """Add an existing customer to a business for AGENT or SUB_AGENT."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.ASSIGN_BUSINESS, db):
        return error_response(status_code=403, message="No permission to assign customers to business")
    if current_user["role"] not in {Role.AGENT, Role.SUB_AGENT}:
        return error_response(
            status_code=403,
            message="Only AGENT and SUB_AGENT can add customers to a business",
        )

    input_phone = customer_phone.replace("+", "")
    if input_phone.startswith("234") and len(input_phone) == 13:
        phone_number = "0" + input_phone[3:]
    elif len(input_phone) == 11 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and input_phone.startswith("0"):
        phone_number = input_phone
    elif len(input_phone) == 10 and not input_phone.startswith("0"):
        phone_number = "0" + input_phone
    else:
        return error_response(
            status_code=400,
            message="Customer phone number must be 10 or 11 digits (with leading 0) or include country code 234 with 13 digits",
        )

    customer = (
        db.query(User)
        .filter(User.phone_number == phone_number, User.role == Role.CUSTOMER)
        .first()
    )
    if not customer:
        return error_response(
            status_code=404, message="Customer not found or not a CUSTOMER role"
        )

    business = (
        db.query(Business).filter(Business.unique_code == business_unique_code).first()
    )
    if not business:
        return error_response(status_code=404, message="Business not found")

    if current_user["role"] == Role.AGENT:
        if business.agent_id != current_user["user_id"]:
            return error_response(
                status_code=403,
                message="Agent must be the owner of the business to add customers",
            )
    else:  # SUB_AGENT
        if (
            not db.query(user_business)
            .filter(
                user_business.c.user_id == current_user["user_id"],
                user_business.c.business_id == business.id,
            )
            .first()
        ):
            return error_response(
                status_code=403, message="Sub-agent not associated with this business"
            )

    if (
        db.query(user_business)
        .filter(
            user_business.c.user_id == customer.id,
            user_business.c.business_id == business.id,
        )
        .first()
    ):
        return error_response(
            status_code=409, message="Customer already associated with this business"
        )

    try:
        token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        pending_request = PendingBusinessRequest(
            customer_id=customer.id,
            business_id=business.id,
            token=token,
            expires_at=expires_at,
        )
        db.add(pending_request)
        db.commit()

        accept_url = (
            f"{settings.APP_BASE_URL}/api/v1/business/accept-invitation?token={token}"
        )
        reject_url = (
            f"{settings.APP_BASE_URL}/api/v1/business/reject-invitation?token={token}"
        )
        notification_method = (
            customer.settings.notification_method if customer.settings else "both"
        )
        delivery_method = []

        if notification_method in ["email", "both"] and customer.email:
            await send_business_invitation_email(
                customer.email,
                customer.full_name,
                business.name,
                accept_url,
                reject_url,
            )
            delivery_method.append("email")

        if not delivery_method:
            return error_response(
                status_code=500, message="No valid notification method available"
            )

        return success_response(
            status_code=200,
            message=f"Invitation sent to customer {customer.full_name} via {', '.join(delivery_method)}, it expires in 24 hours",
            data={"status": "pending", "expires_at": expires_at.isoformat()},
        )
    except Exception as e:
        db.rollback()
        return error_response(
            status_code=500, message=f"Failed to initiate customer invitation: {str(e)}"
        )


async def accept_business_invitation(token: str, db: Session):
    """Accept a business invitation via token."""
    pending_request = (
        db.query(PendingBusinessRequest)
        .filter(PendingBusinessRequest.token == token)
        .first()
    )
    if not pending_request:
        return error_response(
            status_code=404, message="Invalid or missing invitation token"
        )

    if pending_request.expires_at < datetime.now(timezone.utc):
        db.delete(pending_request)
        db.commit()
        return error_response(status_code=410, message="Invitation has expired")

    try:
        db.execute(
            insert(user_business).values(
                user_id=pending_request.customer_id,
                business_id=pending_request.business_id,
            )
        )
        db.delete(pending_request)
        db.commit()

        business = (
            db.query(Business)
            .filter(Business.id == pending_request.business_id)
            .first()
        )
        return success_response(
            status_code=200,
            message=f"Successfully joined business {business.name}",
            data={"business_unique_code": business.unique_code},
        )
    except Exception as e:
        db.rollback()
        return error_response(
            status_code=500, message=f"Failed to accept invitation: {str(e)}"
        )


async def reject_business_invitation(token: str, db: Session):
    """Reject a business invitation via token."""
    pending_request = (
        db.query(PendingBusinessRequest)
        .filter(PendingBusinessRequest.token == token)
        .first()
    )
    if not pending_request:
        return error_response(
            status_code=404, message="Invalid or missing invitation token"
        )

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
        return error_response(
            status_code=500, message=f"Failed to reject invitation: {str(e)}"
        )


async def get_user_businesses(
    current_user: dict,
    db: Session,
    location: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    size: int = 8
):
    """Retrieve paginated and filtered list of businesses associated with the user."""
    # Get business IDs associated with the user
    business_ids = [
        row[0]
        for row in db.query(user_business.c.business_id)
        .filter(user_business.c.user_id == current_user["user_id"])
        .all()
    ]
    if not business_ids:
        return {
            "status_code": 200,
            "success": True,
            "message": "No businesses found",
            "data": {
                "businesses": [],
                "total_items": 0,
                "total_pages": 0,
                "current_page": page,
                "size": size
            }
        }

    # Build query with filters
    query = db.query(Business).filter(Business.id.in_(business_ids))

    if location:
        query = query.filter(Business.location.ilike(f"%{location}%"))

    if start_date:
        query = query.filter(Business.created_at >= start_date)
    if end_date:
        # Include full end date by adding one day
        query = query.filter(Business.created_at < end_date + timedelta(days=1))

    # Get total count for pagination
    total_items = query.count()

    # Apply pagination
    offset = (page - 1) * size
    businesses = query.order_by(Business.created_at.desc()).offset(offset).limit(size).all()

    total_pages = (total_items + size - 1) // size

    # Prepare response
    business_list = [
        BusinessResponse(
            id=business.id,
            name=business.name,
            location=business.location,
            unique_code=business.unique_code,
            created_at=business.created_at,
            delivery_status="n/a",
        ).model_dump()
        for business in businesses
    ]

    return {
        "status_code": 200,
        "success": True,
        "message": "Businesses retrieved successfully",
        "data": {
            "businesses": business_list,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "size": size
        }
    }


async def get_single_business(business_id: int, current_user: dict, db: Session):
    """Retrieve details of a single business by ID if the user is associated with it."""
    # Check if the user is associated with the business
    if (
        not db.query(user_business)
        .filter(
            user_business.c.user_id == current_user["user_id"],
            user_business.c.business_id == business_id,
        )
        .first()
    ):
        return error_response(
            status_code=403, message="User is not associated with this business"
        )

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return error_response(status_code=404, message="Business not found")

    return BusinessResponse(
        id=business.id,
        name=business.name,
        location=business.location,
        unique_code=business.unique_code,
        created_at=business.created_at,
        delivery_status="n/a",  # Not applicable here
    )