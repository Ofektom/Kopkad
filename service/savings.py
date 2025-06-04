from fastapi import status
from sqlalchemy.orm import Session
from models.savings import SavingsAccount, SavingsMarking, SavingsType, SavingsStatus, PaymentMethod
from schemas.savings import (
    SavingsCreateDaily,
    SavingsCreateTarget,
    SavingsResponse,
    SavingsMarkingRequest,
    SavingsMarkingResponse,
    SavingsUpdate,
    SavingsReinitiateDaily,
    SavingsReinitiateTarget,
    BulkMarkSavingsRequest,
    SavingsTargetCalculationResponse,
)
from utils.response import success_response, error_response
from models.user import User, Permission
from datetime import timedelta, datetime, date
from decimal import Decimal
import logging
import os
from paystackapi.transaction import Transaction
from paystackapi.paystack import Paystack
from dateutil.relativedelta import relativedelta
from service.payments import initiate_virtual_account_payment
from models.business import Unit, user_units
from sqlalchemy.sql import exists


paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

logging.basicConfig(
    filename="savings.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ENV = os.getenv("ENV", "prod")


def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions


def _calculate_total_days(start_date: date, duration_months: int) -> int:
    end_date = start_date
    for _ in range(duration_months):
        next_month = end_date.replace(day=1) + timedelta(days=32)
        end_date = next_month.replace(day=1) - timedelta(days=1)
    return (end_date - start_date).days + 1


def _generate_unique_tracking_number(db: Session, model) -> str:
    import random
    while True:
        number = ''.join([str(random.randint(0, 9)) for _ in range(10)])
        if not db.query(model).filter(model.tracking_number == number).first():
            return number


def _adjust_savings_markings(savings: SavingsAccount, markings: list[SavingsMarking], db: Session):
    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    existing_days = len(markings)

    if existing_days < total_days:
        # Add missing markings
        for day in range(existing_days, total_days):
            new_marking = SavingsMarking(
                savings_account_id=savings.id,
                amount=savings.daily_amount,
                marked_date=savings.start_date + timedelta(days=day)  # Correct field name
            )
            db.add(new_marking)

    elif existing_days > total_days:
        # Remove extra markings while keeping the earliest ones
        excess_count = existing_days - total_days
        extra_markings = (
            db.query(SavingsMarking)
            .filter(SavingsMarking.savings_account_id == savings.id)
            .order_by(SavingsMarking.marked_date.desc())  # Remove latest entries first
            .limit(excess_count)
            .all()
        )
        for marking in extra_markings:
            db.delete(marking)

    db.commit()


def _savings_response(savings: SavingsAccount) -> dict:
    return success_response(
        status_code=status.HTTP_201_CREATED if savings.created_at == savings.updated_at else 200,
        message=f"{savings.savings_type} savings {'created' if savings.created_at == savings.updated_at else 'updated'} successfully",
        data=SavingsResponse(
            id=savings.id,
            customer_id=savings.customer_id,
            business_id=savings.business_id,
            tracking_number=savings.tracking_number,
            savings_type=savings.savings_type,
            daily_amount=savings.daily_amount,
            duration_months=savings.duration_months,
            start_date=savings.start_date,
            target_amount=savings.target_amount,
            end_date=savings.end_date,
            commission_days=savings.commission_days,
            created_at=savings.created_at,
            updated_at=savings.updated_at,
        ).model_dump(),
    )


async def create_savings_daily(request: SavingsCreateDaily, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.CREATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to create savings")

    customer_id = (
        current_user["user_id"] if current_user["role"] == "customer" else
        request.customer_id if current_user["role"] in ["agent", "sub_agent", "admin", "super_admin"] else
        None
    )
    if not customer_id:
        return error_response(status_code=400, message="Invalid customer_id or role")

    customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
    if not customer:
        return error_response(status_code=400, message=f"User {customer_id} is not a customer")

    if request.daily_amount <= 0 or request.duration_months <= 0:
        return error_response(status_code=400, message="Daily amount and duration must be positive")

    # NEW: Validate that the customer is associated with a unit under the specified business
    unit_exists = db.query(exists().where(
        user_units.c.user_id == customer_id
    ).where(
        user_units.c.unit_id == Unit.id
    ).where(
        Unit.business_id == request.business_id
    )).scalar()
    if not unit_exists:
        return error_response(status_code=400, message=f"Customer {customer_id} is not associated with any unit in business {request.business_id}")

    total_days = _calculate_total_days(request.start_date, request.duration_months)
    tracking_number = _generate_unique_tracking_number(db, SavingsAccount)
    
    savings = SavingsAccount(
        customer_id=customer_id,
        business_id=request.business_id,
        tracking_number=tracking_number,
        savings_type=SavingsType.DAILY.value,
        daily_amount=request.daily_amount,
        duration_months=request.duration_months,
        start_date=request.start_date,
        commission_days=request.commission_days,
        created_by=current_user["user_id"],
    )
    db.add(savings)
    db.flush()

    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            marked_date=request.start_date + timedelta(days=i),
            amount=request.daily_amount,
            marked_by_id=None,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    logger.info(f"Created daily savings {tracking_number} for customer {customer_id}")
    return _savings_response(savings)

async def calculate_target_savings(request: SavingsCreateTarget):
    if request.target_amount <= 0:
        return error_response(status_code=400, message="Target amount must be positive")

    total_days = (request.end_date - request.start_date).days + 1
    if total_days <= 0:
        return error_response(status_code=400, message="End date must be after start date")

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    daily_amount = request.target_amount / Decimal(total_days)

    return success_response(
        status_code=200,
        message="Savings calculated successfully",
        data=SavingsTargetCalculationResponse(
            daily_amount=daily_amount.quantize(Decimal("0.01")),
            duration_months=duration_months,
        ).model_dump(),
    )

async def create_savings_target(request: SavingsCreateTarget, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.CREATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to create savings")

    customer_id = (
        current_user["user_id"] if current_user["role"] == "customer" else
        request.customer_id if current_user["role"] in ["agent", "sub_agent", "admin", "super_admin"] else
        None
    )
    if not customer_id:
        return error_response(status_code=400, message="Invalid customer_id or role")

    customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
    if not customer:
        return error_response(status_code=400, message=f"User {customer_id} is not a customer")

    if request.target_amount <= 0:
        return error_response(status_code=400, message="Target amount must be positive")
    total_days = (request.end_date - request.start_date).days + 1
    if total_days <= 0:
        return error_response(status_code=400, message="End date must be after start date")

    # NEW: Validate business_id if provided
    if request.business_id:
        unit_exists = db.query(exists().where(
            user_units.c.user_id == customer_id
        ).where(
            user_units.c.unit_id == Unit.id
        ).where(
            Unit.business_id == request.business_id
        )).scalar()
        if not unit_exists:
            return error_response(status_code=400, message=f"Customer {customer_id} is not associated with any unit in business {request.business_id}")

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    tracking_number = _generate_unique_tracking_number(db, SavingsAccount)
    daily_amount = request.target_amount / Decimal(total_days)

    savings = SavingsAccount(
        customer_id=customer_id,
        business_id=request.business_id,
        tracking_number=tracking_number,
        savings_type=SavingsType.TARGET.value,
        daily_amount=daily_amount.quantize(Decimal("0.01")),
        duration_months=duration_months,
        start_date=request.start_date,
        target_amount=request.target_amount,
        end_date=request.end_date,
        commission_days=request.commission_days,
        created_by=current_user["user_id"],
    )
    db.add(savings)
    db.flush()

    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            marked_date=request.start_date + timedelta(days=i),
            amount=daily_amount.quantize(Decimal("0.01")),
            marked_by_id=None,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    logger.info(f"Created target savings {tracking_number} for customer {customer_id}")
    return _savings_response(savings)


async def reinitiate_savings_daily(request: SavingsReinitiateDaily, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.REINITIATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to reinitiate savings")

    savings = db.query(SavingsAccount).filter(
        SavingsAccount.tracking_number == request.tracking_number,
        SavingsAccount.customer_id == current_user["user_id"],
    ).first()
    if not savings:
        return error_response(status_code=404, message=f"Savings {request.tracking_number} not found or not owned")

    markings_count = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).count()
    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    if markings_count < total_days:
        return error_response(
            status_code=400,
            message=f"Savings {savings.tracking_number} not fully completed ({markings_count}/{total_days} days marked)",
        )

    if request.daily_amount <= 0 or request.duration_months <= 0:
        return error_response(status_code=400, message="Daily amount and duration must be positive")

    total_days = _calculate_total_days(request.start_date, request.duration_months)
    savings.daily_amount = request.daily_amount
    savings.duration_months = request.duration_months
    savings.start_date = request.start_date
    savings.commission_days = request.commission_days
    savings.target_amount = None
    savings.end_date = None
    savings.savings_type = SavingsType.DAILY.value
    savings.updated_by = current_user["user_id"]
    db.flush()

    # Clear old markings and create new ones
    db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).delete()
    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            marked_date=request.start_date + timedelta(days=i),
            amount=request.daily_amount,
            marked_by_id=None,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    logger.info(f"Reinitiated daily savings {savings.tracking_number} for customer {current_user['user_id']}")
    return _savings_response(savings)


async def reinitiate_savings_target(request: SavingsReinitiateTarget, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.REINITIATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to reinitiate savings")

    savings = db.query(SavingsAccount).filter(
        SavingsAccount.tracking_number == request.tracking_number,
        SavingsAccount.customer_id == current_user["user_id"],
    ).first()
    if not savings:
        return error_response(status_code=404, message=f"Savings {request.tracking_number} not found or not owned")

    markings_count = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).count()
    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    if markings_count < total_days:
        return error_response(
            status_code=400,
            message=f"Savings {savings.tracking_number} not fully completed ({markings_count}/{total_days} days marked)",
        )

    if request.target_amount <= 0:
        return error_response(status_code=400, message="Target amount must be positive")
    total_days = (request.end_date - request.start_date).days + 1
    if total_days <= 0:
        return error_response(status_code=400, message="End date must be after start date")

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    daily_amount = request.target_amount / Decimal(total_days)

    savings.daily_amount = daily_amount.quantize(Decimal("0.01"))
    savings.duration_months = duration_months
    savings.start_date = request.start_date
    savings.end_date = request.end_date
    savings.target_amount = request.target_amount
    savings.commission_days = request.commission_days
    savings.savings_type = SavingsType.TARGET.value
    savings.updated_by = current_user["user_id"]
    db.flush()

    # Clear old markings and create new ones
    db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).delete()
    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            marked_date=request.start_date + timedelta(days=i),
            amount=daily_amount.quantize(Decimal("0.01")),
            marked_by_id=None,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    logger.info(f"Reinitiated target savings {savings.tracking_number} for customer {current_user['user_id']}")
    return _savings_response(savings)


async def update_savings(savings_id: int, request: SavingsUpdate, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to update savings")

    savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
    if not savings:
        return error_response(status_code=404, message="Savings account not found")

    # Check if any markings exist for this savings account
    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).all()
    has_markings = len(markings) > 0

    # Prevent updating start_date if marking has already begun
    if request.start_date:
        if has_markings:
            return error_response(status_code=400, message="Cannot update start date after marking has begun")
        savings.start_date = request.start_date

    if request.daily_amount is not None:
        if request.daily_amount <= 0:
            return error_response(status_code=400, message="Daily amount must be positive")
        savings.daily_amount = request.daily_amount

        # Update existing markings with the new daily amount
        for marking in markings:
            marking.amount = request.daily_amount
        db.commit()

    # Handle updates that affect the duration (start_date, duration_months, or end_date)
    if request.duration_months is not None or request.start_date or request.end_date:
        if request.duration_months is not None:
            if request.duration_months <= 0:
                return error_response(status_code=400, message="Duration must be positive")
            savings.duration_months = request.duration_months

        if request.start_date and request.end_date:
            if request.end_date <= request.start_date:
                return error_response(status_code=400, message="End date must be after start date")
            savings.end_date = request.end_date
        elif request.start_date:
            savings.end_date = savings.start_date + relativedelta(months=savings.duration_months)
        elif request.end_date:
            savings.duration_months = (request.end_date - savings.start_date).days // 30
            savings.end_date = request.end_date

        # Adjust SavingsMarking records (increase or decrease)
        _adjust_savings_markings(savings, markings, db)

    if request.target_amount is not None:
        if request.target_amount <= 0:
            return error_response(status_code=400, message="Target amount must be positive")
        savings.target_amount = request.target_amount

    if request.commission_days is not None:
        if request.commission_days < 0:
            return error_response(status_code=400, message="Commission days cannot be negative")
        savings.commission_days = request.commission_days

    savings.updated_by = current_user["user_id"]
    db.commit()
    logger.info(f"Updated savings {savings.tracking_number} for customer {current_user['user_id']}")

    return _savings_response(savings)



async def get_savings_markings_by_tracking_number(tracking_number: str, db: Session):
    """
    Retrieve savings markings based on tracking number.
    """
    # Retrieve savings account by tracking number
    savings_account = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    
    if not savings_account:
        return error_response(status_code=404, message="Savings account not found")

    # Get all savings markings linked to the savings_account_id
    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings_account.id).all()

    if not markings:
        return error_response(status_code=404, message="No savings schedule found for this account")

    # Create savings_schedule dictionary with date as key and status (SavingsStatus Enum) as value
    savings_schedule = {
        marking.marked_date: marking.status for marking in markings  # Using enum values
    }

    # Convert to response format
    response_data = SavingsMarkingResponse(
        tracking_number=tracking_number,
        savings_schedule=savings_schedule,
        total_amount=sum(marking.amount for marking in markings),
        authorization_url=None,  # Modify if necessary
        payment_reference=None,  # Modify if necessary
    )

    return success_response(status_code=200, message="Savings schedule retrieved successfully", data=response_data)


async def mark_savings_payment(tracking_number: str, request: SavingsMarkingRequest, current_user: dict, db: Session):
    savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    if not savings:
        return error_response(status_code=404, message="Savings account not found")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
        return error_response(status_code=403, message="Unauthorized role")

    marking = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings.id,
        SavingsMarking.marked_date == request.marked_date
    ).first()
    if not marking or marking.marked_by_id:
        return error_response(status_code=400, message="Invalid date or already marked")

    total_amount = marking.amount
    total_amount_kobo = int(total_amount * 100)
    customer = db.query(User).filter(User.id == savings.customer_id).first()
    if not customer.email:
        return error_response(status_code=400, message="Customer email required")

    reference = f"savings_{savings.tracking_number}_{datetime.now().timestamp()}"
    marking.payment_method = request.payment_method

    if request.payment_method == "card":
        response = Transaction.initialize(
            reference=reference,
            amount=total_amount_kobo,
            email=customer.email,
            callback_url="http://localhost:8001/payments/webhook/paystack"
        )
        logger.info(f"Paystack initialize response: {response}")  # Add this line
        if response["status"]:
            marking.payment_reference = response["data"]["reference"]
            marking.status = SavingsStatus.PENDING.value
            db.commit()
            return SavingsMarkingResponse(
                tracking_number=savings.tracking_number,
                savings_schedule={marking.marked_date: marking.status},
                total_amount=total_amount,
                authorization_url=response["data"]["authorization_url"],
                payment_reference=response["data"]["reference"]
            )
        logger.error(f"Paystack initialization failed: {response}")
        return error_response(status_code=500, message=f"Failed to initiate card payment: {response.get('message', 'Unknown error')}")
    elif request.payment_method == "bank_transfer":
        virtual_account = await initiate_virtual_account_payment(total_amount, customer.email, savings.customer_id, reference)
        if isinstance(virtual_account, dict):
            marking.payment_reference = reference
            marking.status = SavingsStatus.PENDING.value
            db.commit()
            return SavingsMarkingResponse(
                tracking_number=savings.tracking_number,
                savings_schedule={marking.marked_date: marking.status},
                total_amount=total_amount,
                payment_reference=reference,
                virtual_account=virtual_account
            )
        return virtual_account
    return error_response(status_code=400, message="Invalid payment method")

async def mark_savings_bulk(request: BulkMarkSavingsRequest, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.MARK_SAVINGS_BULK, db):
        return error_response(status_code=403, message="No permission to bulk mark savings")

    if not request.markings:
        return error_response(status_code=400, message="No savings accounts provided")

    all_markings = []
    total_amount = Decimal(0)
    payment_method = request.markings[0].payment_method
    
    for mark_request in request.markings:
        if mark_request.payment_method != payment_method:
            return error_response(status_code=400, message="All markings must use the same payment method")
        savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == mark_request.tracking_number).first()
        if not savings:
            return error_response(status_code=404, message=f"Savings {mark_request.tracking_number} not found")

        if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
            return error_response(status_code=403, message=f"Not your savings {mark_request.tracking_number}")
        elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
            return error_response(status_code=403, message="Unauthorized role")

        markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.marked_date.in_([mark_request.marked_date])
        ).all()
        if len(markings) != 1 or markings[0].marked_by_id:
            return error_response(status_code=400, message=f"Invalid or already marked date for {mark_request.tracking_number}")

        markings[0].payment_method = mark_request.payment_method.value
        total_amount += markings[0].amount
        all_markings.extend(markings)

    customer = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not customer.email:
        return error_response(status_code=400, message="User email required")

    total_amount_kobo = int(total_amount * 100)
    reference = f"bulk_savings_{datetime.now().timestamp()}"
    if payment_method == "card":
        response = Transaction.initialize(
            reference=reference,
            amount=total_amount_kobo,
            email=customer.email,
            callback_url="http://localhost:8001/payments/webhook/paystack"
        )
        if response["status"]:
            for marking in all_markings:
                marking.payment_reference = response["data"]["reference"]
                marking.status = SavingsStatus.PENDING.value
            db.commit()
            savings_accounts = {m.savings_account.tracking_number: [m.marked_date.isoformat()] for m in all_markings}
            return success_response(
                status_code=200,
                message="Proceed to payment for bulk marking",
                data={
                    "authorization_url": response["data"]["authorization_url"],
                    "reference": response["data"]["reference"],
                    "total_amount": total_amount,
                    "savings_accounts": [{"tracking_number": tn, "marked_dates": dates} for tn, dates in savings_accounts.items()]
                }
            )
        return error_response(status_code=500, message="Failed to initiate bulk card payment")
    elif payment_method == "bank_transfer":
        virtual_account = await initiate_virtual_account_payment(total_amount, customer.email, current_user["user_id"], reference)
        if isinstance(virtual_account, dict):
            for marking in all_markings:
                marking.payment_reference = reference
                marking.status = SavingsStatus.PENDING.value
            db.commit()
            savings_accounts = {m.savings_account.tracking_number: [m.marked_date.isoformat()] for m in all_markings}
            return success_response(
                status_code=200,
                message="Pay to the virtual account for bulk marking",
                data={
                    "virtual_account": virtual_account,
                    "reference": reference,
                    "total_amount": total_amount,
                    "savings_accounts": [{"tracking_number": tn, "marked_dates": dates} for tn, dates in savings_accounts.items()]
                }
            )
        return virtual_account
    return error_response(status_code=400, message="Invalid payment method")


async def verify_savings_payment(reference: str, db: Session):
    if ENV != "dev":
        return error_response(status_code=403, message="This endpoint is only available in development mode")

    # Fetch markings by reference
    markings = db.query(SavingsMarking).filter(SavingsMarking.payment_reference == reference).all()
    if not markings:
        return error_response(status_code=404, message="Payment reference not found")

    # Determine payment method from the first marking
    payment_method = markings[0].payment_method
    logger.info(f"Verifying payment for reference {reference} with method {payment_method}")

    if payment_method == PaymentMethod.CARD or payment_method == "card":
        # Verify card payment with Paystack
        response = Transaction.verify(reference=reference)
        if response["status"] and response["data"]["status"] == "success":
            total_paid = Decimal(response["data"]["amount"]) / 100
            expected_amount = sum(m.amount for m in markings)
            if total_paid < expected_amount:
                logger.error(f"Underpayment for {reference}: expected {expected_amount}, paid {total_paid}")
                return error_response(
                    status_code=400,
                    message=f"Paid amount {total_paid} less than expected {expected_amount}"
                )
        else:
            logger.error(f"Card payment verification failed: {response.get('message', 'No message')}")
            return error_response(status_code=400, message="Payment verification failed")
    elif payment_method == PaymentMethod.BANK_TRANSFER or payment_method == "bank_transfer":
        # In dev mode with mock, simulate verification
        # For real bank transfers, this will need Paystack transfer verification (see below)
        expected_amount = sum(m.amount for m in markings)
        total_paid = expected_amount  # Mock assumes full payment for simplicity
        logger.info(f"Simulating bank transfer verification for {reference} (mock)")
    else:
        return error_response(status_code=400, message=f"Unsupported payment method: {payment_method}")

    # Update markings if payment is verified (card) or simulated (bank transfer)
    for marking in markings:
        if marking.status == SavingsStatus.PENDING.value:
            marking.marked_by_id = markings[0].savings_account.customer_id
            marking.updated_by = marking.marked_by_id
            marking.status = SavingsStatus.PAID.value
            marking.updated_at = datetime.now()
    db.commit()

    return success_response(
        status_code=200,
        message="Payment verified and dates marked (local test)",
        data={"reference": reference, "marked_dates": [m.marked_date.isoformat() for m in markings]}
    )

async def get_all_savings(
        customer_id: int | None,
        business_id: int | None,
        savings_type: str | None,
        limit: int, 
        offset: int, 
        current_user: dict, 
        db: Session
    ):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")
    
    query = db.query(SavingsAccount)

    # Role-based parameter validation and filtering
    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own savings")
        query = query.filter(SavingsAccount.customer_id == current_user["user_id"])
    elif current_user["role"] == "admin":
        if not business_id:
            return error_response(status_code=400, message="Business ID is required for admin role")
        unit_exists = db.query(exists().where(Unit.business_id == business_id)).scalar()
        if not unit_exists:
            return error_response(status_code=400, message=f"Business {business_id} not found")
        query = query.filter(SavingsAccount.business_id == business_id)
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        if business_id and business_id not in business_ids:
            return error_response(status_code=403, message="Access restricted to your business")
        query = query.filter(SavingsAccount.business_id.in_(business_ids))
    elif current_user["role"] != "super_admin":
        return error_response(status_code=403, message="Unauthorized role")

    # Optional customer_id filter (for super_admin, admin, agent, sub_agent)
    if customer_id and current_user["role"] != "customer":
        customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        query = query.filter(SavingsAccount.customer_id == customer_id)

    # Optional savings_type filter
    if savings_type:
        if savings_type not in [SavingsType.DAILY.value, SavingsType.TARGET.value]:
            return error_response(status_code=400, message="Invalid savings type. Use DAILY or TARGET")
        query = query.filter(SavingsAccount.savings_type == savings_type)
    
     # Pagination validation
    if limit < 1 or offset < 0:
        return error_response(status_code=400, message="Limit must be positive and offset non-negative")

    # Get total count
    total_count = query.count()

    # Fetch savings accounts
    savings = query.order_by(SavingsAccount.created_at.desc()).offset(offset).limit(limit).all()

    if not savings:
        return success_response(
            status_code=200,
            message="No savings accounts found",
            data={
                "savings": [], 
                "total_count": 0,
                "limit": limit,
                "offset": offset,
            }
        )

    response_data = [
        SavingsResponse(
            id=s.id,
            customer_id=s.customer_id,
            business_id=s.business_id,
            tracking_number=s.tracking_number,
            savings_type=s.savings_type,
            daily_amount=s.daily_amount,
            duration_months=s.duration_months,
            start_date=s.start_date,
            target_amount=s.target_amount,
            end_date=s.end_date,
            commission_days=s.commission_days,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ).model_dump()
        for s in savings
    ]

    logger.info(f"Retrieved {len(savings)} savings accounts for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Savings accounts retrieved successfully",
        data={
            "savings": response_data, 
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )