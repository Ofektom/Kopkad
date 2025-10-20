from fastapi import status
from sqlalchemy.orm import Session
from models.savings import SavingsAccount, SavingsMarking, SavingsType, SavingsStatus, PaymentMethod, MarkingStatus
from schemas.savings import (
    SavingsCreateDaily,
    SavingsCreateTarget,
    SavingsResponse,
    SavingsMarkingRequest,
    SavingsMarkingResponse,
    SavingsUpdate,
    SavingsExtend,
    BulkMarkSavingsRequest,
    SavingsTargetCalculationResponse,
    SavingsMetricsResponse,
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
from models.business import Unit, user_units
from sqlalchemy.sql import exists
import requests
import uuid
import math

paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

logging.basicConfig(
    filename="savings.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def calculate_total_commission(savings: SavingsAccount) -> Decimal:
    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    commission_periods = math.ceil(total_days / savings.commission_days)
    total_commission = savings.commission_amount * Decimal(commission_periods)
    return total_commission.quantize(Decimal("0.01"))

async def initiate_virtual_account_payment(amount: Decimal, email: str, customer_id: int, reference: str, db: Session):
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json",
        }
        user = db.query(User).filter(User.id == customer_id).first()
        if not user:
            logger.error(f"User {customer_id} not found in database")
            return error_response(status_code=404, message="User not found")

        payment_provider_customer_id = getattr(user, 'payment_provider_customer_id', None)
        if not payment_provider_customer_id:
            customer_payload = {
                "email": email,
                "first_name": "Customer",
                "last_name": f"ID_{customer_id}",
            }
            customer_response = requests.post(
                "https://api.paystack.co/customer",
                headers=headers,
                json=customer_payload,
            )
            customer_data = customer_response.json()
            logger.info(f"Paystack customer creation response: {customer_data}")
            if customer_response.status_code != 200 or not customer_data.get("status"):
                logger.error(f"Failed to create Paystack customer: {customer_data}")
                return error_response(
                    status_code=customer_response.status_code,
                    message=f"Failed to create customer: {customer_data.get('message', 'Unknown error')}",
                )
            payment_provider_customer_id = customer_data["data"]["customer_code"]
            try:
                user.payment_provider_customer_id = payment_provider_customer_id
                db.commit()
            except AttributeError:
                logger.warning(f"User model lacks payment_provider_customer_id field; proceeding without storing")

        is_test_mode = "test" in os.getenv("PAYSTACK_SECRET_KEY", "").lower() or os.getenv("PAYSTACK_ENV", "production") == "test"
        if is_test_mode:
            logger.info(f"Running in test mode; generating mock virtual account for customer {payment_provider_customer_id}")
            virtual_account = {
                "bank": "Test Bank",
                "account_number": f"TEST{str(customer_id).zfill(10)}",
                "account_name": f"Test Account - ID_{customer_id}",
            }
            logger.info(f"Generated mock virtual account: {virtual_account}")
        else:
            dedicated_response = requests.get(
                f"https://api.paystack.co/dedicated_account?customer={payment_provider_customer_id}",
                headers=headers,
            )
            dedicated_data = dedicated_response.json()
            logger.info(f"Paystack dedicated account check response: {dedicated_data}")

            if dedicated_response.status_code == 200 and dedicated_data.get("status") and dedicated_data["data"]:
                account_data = dedicated_data["data"][0]
                virtual_account = {
                    "bank": account_data["bank"]["name"],
                    "account_number": account_data["account_number"],
                    "account_name": account_data["account_name"],
                }
                logger.info(f"Using existing dedicated account for customer {payment_provider_customer_id}: {virtual_account}")
            else:
                if dedicated_data.get("code") == "feature_unavailable":
                    logger.error(f"Dedicated NUBAN not available: {dedicated_data}")
                    return error_response(
                        status_code=400,
                        message="Virtual account payments are currently unavailable. Please contact support@paystack.com to enable this feature.",
                    )
                payload = {
                    "customer": payment_provider_customer_id,
                    "preferred_bank": "wema-bank",
                }
                response = requests.post(
                    "https://api.paystack.co/dedicated_account",
                    headers=headers,
                    json=payload,
                )
                response_data = response.json()
                logger.info(f"Paystack dedicated account creation response: {response_data}")
                if response.status_code == 200 and response_data.get("status"):
                    virtual_account = {
                        "bank": response_data["data"]["bank"]["name"],
                        "account_number": response_data["data"]["account_number"],
                        "account_name": response_data["data"]["account_name"],
                    }
                else:
                    if response_data.get("code") == "feature_unavailable":
                        logger.error(f"Dedicated NUBAN not available: {response_data}")
                        return error_response(
                            status_code=400,
                            message="Virtual account payments are currently unavailable. Please contact support@paystack.com to enable this feature.",
                        )
                    logger.error(f"Failed to create dedicated account: {response_data}")
                    return error_response(
                        status_code=response.status_code,
                        message=f"Failed to initiate virtual account: {response_data.get('message', 'Dedicated NUBAN creation failed')}",
                    )

        transaction = Transaction.initialize(
            reference=reference,
            amount=int(amount * 100),
            email=email,
            callback_url="https://kopkad-frontend.vercel.app/payment-confirmation",
        )
        logger.info(f"Paystack transaction initialize response: {transaction}")
        if not transaction["status"]:
            logger.error(f"Failed to initialize transaction: {transaction}")
            return error_response(
                status_code=500,
                message=f"Failed to initialize transaction: {transaction.get('message', 'Unknown error')}",
            )

        return virtual_account
    except Exception as e:
        logger.error(f"Error initiating virtual account: {str(e)}", exc_info=True)
        return error_response(status_code=500, message=f"Error initiating virtual account: {str(e)}")

def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions

def _calculate_total_days(start_date: date, duration_months: int) -> int:
    end_date = start_date + relativedelta(months=duration_months) - timedelta(days=1)
    total_days = (end_date - start_date).days + 1
    logger.info(f"Calculated {total_days} days from {start_date} to {end_date} for {duration_months} months")
    return total_days

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
        last_marking_date = max([m.marked_date for m in markings]) if markings else savings.start_date - timedelta(days=1)
        for day in range(existing_days, total_days):
            new_marking_date = savings.start_date + timedelta(days=day)
            if new_marking_date <= last_marking_date:
                continue
            new_marking = SavingsMarking(
                savings_account_id=savings.id,
                unit_id=savings.unit_id,
                amount=savings.daily_amount,
                marked_date=new_marking_date,
                status=SavingsStatus.PENDING,
            )
            db.add(new_marking)

    elif existing_days > total_days:
        excess_count = existing_days - total_days
        extra_markings = (
            db.query(SavingsMarking)
            .filter(SavingsMarking.savings_account_id == savings.id)
            .order_by(SavingsMarking.marked_date.desc())
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
            unit_id=savings.unit_id,
            tracking_number=savings.tracking_number,
            savings_type=savings.savings_type,
            daily_amount=savings.daily_amount,
            duration_months=savings.duration_months,
            start_date=savings.start_date,
            target_amount=savings.target_amount,
            end_date=savings.end_date,
            commission_days=savings.commission_days,
            commission_amount=savings.commission_amount,
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

    if request.commission_days <= 0:
        return error_response(status_code=400, message="Commission days must be positive")

    unit_exists = db.query(exists().where(
        user_units.c.user_id == customer_id
    ).where(
        user_units.c.unit_id == request.unit_id
    ).where(
        Unit.id == request.unit_id
    ).where(
        Unit.business_id == request.business_id
    )).scalar()
    if not unit_exists:
        return error_response(status_code=400, message=f"Customer {customer_id} is not associated with unit {request.unit_id} in business {request.business_id}")

    total_days = _calculate_total_days(request.start_date, request.duration_months)
    total_amount = request.daily_amount * Decimal(total_days)
    commission_amount = request.commission_amount if request.commission_amount is not None else request.daily_amount

    if commission_amount < 0:
        return error_response(status_code=400, message="Commission amount cannot be negative")

    tracking_number = _generate_unique_tracking_number(db, SavingsAccount)
    end_date = request.start_date + relativedelta(months=request.duration_months) - timedelta(days=1)

    savings = SavingsAccount(
        customer_id=customer_id,
        business_id=request.business_id,
        unit_id=request.unit_id,
        tracking_number=tracking_number,
        savings_type=SavingsType.DAILY,
        daily_amount=request.daily_amount,
        duration_months=request.duration_months,
        start_date=request.start_date,
        end_date=end_date,
        commission_days=request.commission_days,
        commission_amount=commission_amount,
        target_amount=total_amount,
        created_by=current_user["user_id"],
        marking_status=MarkingStatus.NOT_STARTED,
    )
    db.add(savings)
    db.flush()

    total_commission = calculate_total_commission(savings)
    logger.info(f"Set target_amount={total_amount} for daily savings {tracking_number} with {total_days} days")
    logger.info(f"Set commission_amount={commission_amount}, commission_days={request.commission_days}, total_commission={total_commission} for daily savings {tracking_number}")
    logger.info(f"Creating {total_days} markings for daily savings {tracking_number} from {request.start_date} to {end_date}")

    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            unit_id=savings.unit_id,
            marked_date=request.start_date + timedelta(days=i),
            amount=request.daily_amount,
            marked_by_id=None,
            status=SavingsStatus.PENDING,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    logger.info(f"Created daily savings {tracking_number} with {len(markings)} markings for customer {customer_id}")
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

    if request.commission_days <= 0:
        return error_response(status_code=400, message="Commission days must be positive")

    unit_exists = db.query(exists().where(
        user_units.c.user_id == customer_id
    ).where(
        user_units.c.unit_id == request.unit_id
    ).where(
        Unit.id == request.unit_id
    ).where(
        Unit.business_id == request.business_id
    )).scalar()
    if not unit_exists:
        return error_response(status_code=400, message=f"Customer {customer_id} is not associated with unit {request.unit_id} in business {request.business_id}")

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    tracking_number = _generate_unique_tracking_number(db, SavingsAccount)
    daily_amount = request.target_amount / Decimal(total_days)
    commission_amount = request.commission_amount if request.commission_amount is not None else daily_amount.quantize(Decimal("0.01"))

    if commission_amount < 0:
        return error_response(status_code=400, message="Commission amount cannot be negative")

    savings = SavingsAccount(
        customer_id=customer_id,
        business_id=request.business_id,
        unit_id=request.unit_id,
        tracking_number=tracking_number,
        savings_type=SavingsType.TARGET,
        daily_amount=daily_amount.quantize(Decimal("0.01")),
        duration_months=duration_months,
        start_date=request.start_date,
        target_amount=request.target_amount,
        end_date=request.end_date,
        commission_days=request.commission_days,
        commission_amount=commission_amount,
        created_by=current_user["user_id"],
        marking_status=MarkingStatus.NOT_STARTED,
    )
    db.add(savings)
    db.flush()

    total_commission = calculate_total_commission(savings)
    logger.info(f"Created target savings {tracking_number} with commission_amount={commission_amount}, commission_days={request.commission_days}, total_commission={total_commission} for customer {customer_id}")

    markings = [
        SavingsMarking(
            savings_account_id=savings.id,
            unit_id=savings.unit_id,
            marked_date=request.start_date + timedelta(days=i),
            amount=daily_amount.quantize(Decimal("0.01")),
            marked_by_id=None,
            status=SavingsStatus.PENDING,
        )
        for i in range(total_days)
    ]
    db.add_all(markings)
    db.commit()

    return _savings_response(savings)

async def extend_savings(request: SavingsExtend, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to extend savings")

    savings = db.query(SavingsAccount).filter(
        SavingsAccount.tracking_number == request.tracking_number,
        SavingsAccount.customer_id == current_user["user_id"],
    ).first()
    if not savings:
        return error_response(status_code=404, message=f"Savings {request.tracking_number} not found or not owned")

    if savings.marking_status == MarkingStatus.COMPLETED:
        return error_response(
            status_code=400,
            message=f"Savings {savings.tracking_number} is completed and cannot be extended",
        )

    if request.additional_months <= 0:
        return error_response(status_code=400, message="Additional months must be positive")

    current_end_date = savings.end_date
    today = date.today()
    if today > current_end_date:
        return error_response(status_code=400, message=f"Savings {savings.tracking_number} has ended and cannot be extended")

    savings.duration_months += request.additional_months
    savings.end_date = current_end_date + relativedelta(months=request.additional_months)
    savings.updated_by = current_user["user_id"]

    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    savings.target_amount = savings.daily_amount * Decimal(total_days) if savings.savings_type == SavingsType.DAILY else savings.target_amount

    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).all()
    _adjust_savings_markings(savings, markings, db)

    total_commission = calculate_total_commission(savings)
    logger.info(f"Extended savings {savings.tracking_number} by {request.additional_months} months, new total_commission={total_commission} for customer {current_user['user_id']}")

    db.commit()
    return _savings_response(savings)

async def update_savings(savings_id: int, request: SavingsUpdate, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to update savings")

    savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
    if not savings:
        return error_response(status_code=404, message="Savings account not found")

    if request.business_id and request.unit_id:
        unit_exists = db.query(exists().where(
            user_units.c.user_id == savings.customer_id
        ).where(
            user_units.c.unit_id == request.unit_id
        ).where(
            Unit.id == request.unit_id
        ).where(
            Unit.business_id == request.business_id
        )).scalar()
        if not unit_exists:
            return error_response(status_code=400, message=f"Customer {savings.customer_id} is not associated with unit {request.unit_id} in business {request.business_id}")
        savings.business_id = request.business_id
        savings.unit_id = request.unit_id

    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).all()
    has_markings = len(markings) > 0

    if request.start_date:
        if has_markings:
            return error_response(status_code=400, message="Cannot update start date after marking has begun")
        savings.start_date = request.start_date

    if request.daily_amount is not None:
        if request.daily_amount <= 0:
            return error_response(status_code=400, message="Daily amount must be positive")
        savings.daily_amount = request.daily_amount
        if request.commission_amount is None and savings.commission_amount == savings.daily_amount:
            savings.commission_amount = request.daily_amount

        for marking in markings:
            marking.amount = request.daily_amount
            marking.unit_id = savings.unit_id
        db.commit()

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
            savings.end_date = savings.start_date + relativedelta(months=savings.duration_months) - timedelta(days=1)
        elif request.end_date:
            savings.duration_months = (request.end_date - savings.start_date).days // 30
            savings.end_date = request.end_date

        if savings.savings_type == SavingsType.DAILY:
            total_days = _calculate_total_days(savings.start_date, savings.duration_months)
            savings.target_amount = savings.daily_amount * Decimal(total_days)

        _adjust_savings_markings(savings, markings, db)

    if request.target_amount is not None:
        if request.target_amount <= 0:
            return error_response(status_code=400, message="Target amount must be positive")
        savings.target_amount = request.target_amount

    if request.commission_days is not None:
        if request.commission_days <= 0:
            return error_response(status_code=400, message="Commission days must be positive")
        savings.commission_days = request.commission_days

    if request.commission_amount is not None:
        if request.commission_amount < 0:
            return error_response(status_code=400, message="Commission amount cannot be negative")
        savings.commission_amount = request.commission_amount

    savings.updated_by = current_user["user_id"]
    db.commit()
    total_commission = calculate_total_commission(savings)
    logger.info(f"Updated savings {savings.tracking_number} with commission_amount={savings.commission_amount}, commission_days={savings.commission_days}, total_commission={total_commission} for customer {current_user['user_id']}")
    return _savings_response(savings)

async def delete_savings(savings_id: int, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to delete savings")

    savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
    if not savings:
        return error_response(status_code=404, message="Savings account not found")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
        return error_response(status_code=401, message="Unauthorized role")

    has_paid_markings = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings_id,
        SavingsMarking.status == SavingsStatus.PAID
    ).first()
    if has_paid_markings:
        return error_response(status_code=400, message="Cannot delete savings account with paid markings")

    tracking_number = savings.tracking_number
    db.delete(savings)
    db.commit()

    logger.info(f"Deleted savings account {tracking_number} (ID: {savings_id}) for customer {savings.customer_id}")
    return success_response(
        status_code=200,
        message="Savings account deleted successfully",
        data={"tracking_number": tracking_number, "savings_id": savings_id}
    )

async def get_all_savings(
    customer_id: int | None,
    business_id: int | None,
    unit_id: int | None,
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

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own savings")
        query = query.filter(SavingsAccount.customer_id == current_user["user_id"])
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        if business_id and business_id not in business_ids:
            return error_response(status_code=403, message="Access restricted to your business")
        query = query.filter(SavingsAccount.business_id.in_(business_ids))
        if unit_id:
            unit_exists = db.query(exists().where(Unit.id == unit_id).where(Unit.business_id.in_(business_ids))).scalar()
            if not unit_exists:
                return error_response(status_code=400, message=f"Unit {unit_id} not found in your businesses")
            query = query.filter(SavingsAccount.unit_id == unit_id)
    elif current_user["role"] == "admin":
        if not business_id:
            return error_response(status_code=400, message="Business ID is required for admin role")
        unit_exists = db.query(exists().where(Unit.business_id == business_id)).scalar()
        if not unit_exists:
            return error_response(status_code=400, message=f"Business {business_id} not found")
        query = query.filter(SavingsAccount.business_id == business_id)
        if unit_id:
            unit_exists = db.query(exists().where(Unit.id == unit_id).where(Unit.business_id == business_id)).scalar()
            if not unit_exists:
                return error_response(status_code=400, message=f"Unit {unit_id} not found in business {business_id}")
            query = query.filter(SavingsAccount.unit_id == unit_id)
    elif current_user["role"] != "super_admin":
        return error_response(status_code=401, message="Unauthorized role")

    if business_id:
        query = query.filter(SavingsAccount.business_id == business_id)

    if customer_id and current_user["role"] != "customer":
        customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        query = query.filter(SavingsAccount.customer_id == customer_id)

    if savings_type:
        # Map legacy savings types to enum values
        savings_type_map = {
            "single": SavingsType.DAILY,
            "target": SavingsType.TARGET,
            "daily": SavingsType.DAILY
        }
        if savings_type.lower() not in savings_type_map and savings_type not in [SavingsType.DAILY, SavingsType.TARGET]:
            return error_response(status_code=400, message="Invalid savings type. Use DAILY, TARGET, single, or target")
        query = query.filter(SavingsAccount.savings_type == savings_type_map.get(savings_type.lower(), savings_type))
    
    if limit < 1 or offset < 0:
        return error_response(status_code=400, message="Limit must be positive and offset non-negative")

    total_count = query.count()

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
            unit_id=s.unit_id,
            tracking_number=s.tracking_number,
            savings_type=s.savings_type,
            daily_amount=s.daily_amount,
            duration_months=s.duration_months,
            start_date=s.start_date,
            target_amount=s.target_amount,
            end_date=s.end_date,
            commission_days=s.commission_days,
            commission_amount=s.commission_amount,
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

async def get_savings_markings_by_tracking_number(tracking_number: str, db: Session):
    savings_account = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    
    if not savings_account:
        return error_response(status_code=404, message="Savings account not found")

    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings_account.id).all()

    if not markings:
        return error_response(status_code=404, message="No savings schedule found for this account")
    
    savings_schedule = {
        marking.marked_date.isoformat(): marking.status for marking in markings
    }

    response_data = SavingsMarkingResponse(
        tracking_number=tracking_number,
        unit_id=savings_account.unit_id,
        savings_schedule=savings_schedule,
        total_amount=savings_account.target_amount or sum(marking.amount for marking in markings),
        authorization_url=None,
        payment_reference=None,
        virtual_account=None
    )

    logger.info(f"Retrieved {len(savings_schedule)} markings for savings {tracking_number}")
    return success_response(status_code=200, message="Savings schedule retrieved successfully", data=response_data.model_dump())

async def mark_savings_payment(tracking_number: str, request: SavingsMarkingRequest, current_user: dict, db: Session):
    savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    if not savings:
        logger.error(f"Savings account with tracking_number {tracking_number} not found")
        return error_response(status_code=404, message=f"Savings {tracking_number} not found")

    if savings.marking_status == MarkingStatus.COMPLETED:
        logger.warning(f"Attempt to mark savings {tracking_number} in COMPLETED status")
        return error_response(status_code=400, message=f"Cannot mark savings in {savings.marking_status} status")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        logger.warning(f"User {current_user['user_id']} attempted to mark savings {tracking_number} not owned")
        return error_response(status_code=403, message=f"Not your savings {tracking_number}")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
        logger.warning(f"Unauthorized role {current_user['role']} attempted to mark savings {tracking_number}")
        return error_response(status_code=401, message="Unauthorized role")

    if request.unit_id:
        unit_exists = db.query(exists().where(
            user_units.c.user_id == savings.customer_id
        ).where(
            user_units.c.unit_id == request.unit_id
        ).where(
            Unit.id == request.unit_id
        ).where(
            Unit.business_id == savings.business_id
        )).scalar()
        if not unit_exists:
            logger.error(f"Customer {savings.customer_id} not associated with unit {request.unit_id} in business {savings.business_id}")
            return error_response(status_code=400, message=f"Customer {savings.customer_id} is not associated with unit {request.unit_id} in business {savings.business_id}")

    logger.info(f"Attempting to mark date {request.marked_date} for savings {tracking_number}")

    marking = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings.id,
        SavingsMarking.marked_date == request.marked_date,
        SavingsMarking.status == SavingsStatus.PENDING
    ).first()

    if not marking:
        existing_marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.marked_date == request.marked_date
        ).first()
        if not existing_marking:
            logger.error(f"Date {request.marked_date} not found in savings schedule for {tracking_number}")
            return error_response(status_code=400, message=f"Date {request.marked_date} is not in the savings schedule")
        logger.error(f"Date {request.marked_date} for {tracking_number} is already marked, status: {existing_marking.status}")
        return error_response(status_code=400, message=f"Date {request.marked_date} is already marked (status: {existing_marking.status})")
    
    customer = db.query(User).filter(User.id == savings.customer_id).first()
    if not customer.email:
        logger.error(f"Customer {savings.customer_id} has no email for savings {tracking_number}")
        return error_response(status_code=400, message="Customer email required")

    try:
        payment_method = PaymentMethod(request.payment_method)
        if payment_method not in [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]:
            logger.error(f"Invalid payment method {request.payment_method} for savings {tracking_number}")
            return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")
    except ValueError:
        logger.error(f"Invalid payment method value {request.payment_method} for savings {tracking_number}")
        return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")

    marking.payment_method = payment_method
    marking.unit_id = request.unit_id or savings.unit_id
    marking.marked_by_id = current_user["user_id"]
    marking.updated_by = current_user["user_id"]

    days_since_start = (request.marked_date - savings.start_date).days + 1
    commission_periods = math.floor(days_since_start / savings.commission_days) + 1
    commission_due = savings.commission_amount if days_since_start % savings.commission_days == 0 or commission_periods == 1 else Decimal("0")
    total_amount = marking.amount + commission_due

    if savings.marking_status == MarkingStatus.NOT_STARTED:
        savings.marking_status = MarkingStatus.IN_PROGRESS
        db.commit()

    short_uuid = str(uuid.uuid4())[:8]
    reference = f"sv_{tracking_number}_{short_uuid}"
    if len(reference) > 100:
        logger.warning(f"Generated reference too long: {reference}; truncating")
        reference = reference[:100]

    if payment_method == PaymentMethod.CARD:
        total_amount_kobo = int(total_amount * 100)
        response = Transaction.initialize(
            reference=reference,
            amount=total_amount_kobo,
            email=customer.email,
            callback_url="https://kopkad-frontend.vercel.app/payment-confirmation"
        )
        logger.info(f"Paystack initialize response: {response}")
        if response["status"]:
            marking.payment_reference = response["data"]["reference"]
            marking.status = SavingsStatus.PENDING
            db.commit()
            logger.info(f"Card payment initiated for {tracking_number}, date {request.marked_date}, reference {reference}, includes commission_due={commission_due}")
            return success_response(
                status_code=200,
                message="Proceed to payment",
                data=SavingsMarkingResponse(
                    tracking_number=savings.tracking_number,
                    unit_id=savings.unit_id,
                    savings_schedule={marking.marked_date.isoformat(): marking.status},
                    total_amount=total_amount,
                    authorization_url=response["data"]["authorization_url"],
                    payment_reference=response["data"]["reference"],
                    virtual_account=None
                ).model_dump()
            )
        logger.error(f"Paystack initialization failed: {response}")
        return error_response(status_code=500, message=f"Failed to initiate card payment: {response.get('message', 'Unknown error')}")
    elif payment_method == PaymentMethod.BANK_TRANSFER:
        virtual_account = await initiate_virtual_account_payment(total_amount, customer.email, savings.customer_id, reference, db)
        if isinstance(virtual_account, dict):
            marking.payment_reference = reference
            marking.status = SavingsStatus.PENDING
            marking.virtual_account_details = virtual_account
            db.commit()
            logger.info(f"Bank transfer initiated for {tracking_number}, date {request.marked_date}, reference {reference}, includes commission_due={commission_due}")
            return success_response(
                status_code=200,
                message="Pay to the virtual account",
                data=SavingsMarkingResponse(
                    tracking_number=savings.tracking_number,
                    unit_id=savings.unit_id,
                    savings_schedule={marking.marked_date.isoformat(): marking.status},
                    total_amount=total_amount,
                    authorization_url=None,
                    payment_reference=reference,
                    virtual_account=virtual_account
                ).model_dump()
            )
        logger.error(f"Failed to initiate virtual account payment: {virtual_account}")
        return virtual_account
    logger.error(f"Invalid payment method {payment_method} for savings {tracking_number}")
    return error_response(status_code=400, message=f"Invalid payment method: {payment_method}")

async def mark_savings_bulk(request: BulkMarkSavingsRequest, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()

    if not request.markings:
        logger.error("No markings provided in bulk marking request")
        return error_response(status_code=400, message="No savings accounts provided")

    try:
        payment_method = PaymentMethod(request.payment_method)
        if payment_method not in [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]:
            logger.error(f"Invalid payment method {request.payment_method}")
            return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")
    except ValueError:
        logger.error(f"Invalid payment method value {request.payment_method}")
        return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")

    all_markings = []
    total_amount = Decimal("0")
    marked_dates_by_tracking = {}
    savings_accounts = {}
    commission_due_by_savings = {}

    markings_by_tracking = {}
    for mark_request in request.markings:
        tracking_number = mark_request.tracking_number
        if tracking_number not in markings_by_tracking:
            markings_by_tracking[tracking_number] = []
        markings_by_tracking[tracking_number].append(mark_request)

    for tracking_number, mark_requests in markings_by_tracking.items():
        savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
        if not savings:
            logger.error(f"Savings account {tracking_number} not found")
            return error_response(status_code=404, message=f"Savings {tracking_number} not found")

        if savings.marking_status == MarkingStatus.COMPLETED:
            logger.warning(f"Attempt to mark savings {tracking_number} in COMPLETED status")
            return error_response(status_code=400, message=f"Cannot mark savings in {savings.marking_status} status")

        if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
            logger.warning(f"User {current_user['user_id']} attempted to mark savings {tracking_number} not owned")
            return error_response(status_code=403, message=f"Not your savings {tracking_number}")
        elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
            logger.warning(f"Unauthorized role {current_user['role']} attempted to mark savings {tracking_number}")
            return error_response(status_code=401, message="Unauthorized role")

        unit_id = mark_requests[0].unit_id
        if unit_id:
            unit_exists = db.query(exists().where(
                user_units.c.user_id == savings.customer_id
            ).where(
                user_units.c.unit_id == unit_id
            ).where(
                Unit.id == unit_id
            ).where(
                Unit.business_id == savings.business_id
            )).scalar()
            if not unit_exists:
                logger.error(f"Customer {savings.customer_id} not associated with unit {unit_id} in business {savings.business_id}")
                return error_response(status_code=400, message=f"Customer {savings.customer_id} is not associated with unit {unit_id} in business {savings.business_id}")

        all_account_markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id
        ).order_by(SavingsMarking.marked_date.asc()).all()

        if not all_account_markings:
            logger.error(f"No markings found for savings {tracking_number}")
            return error_response(status_code=400, message=f"No markings found for savings {tracking_number}")

        earliest_pending = None
        for marking in all_account_markings:
            if marking.status == SavingsStatus.PENDING:
                earliest_pending = marking.marked_date
                break

        if not earliest_pending:
            logger.error(f"No pending markings found for savings {tracking_number}")
            return error_response(status_code=400, message=f"No pending markings available for savings {tracking_number}")

        requested_dates = sorted([mark_request.marked_date for mark_request in mark_requests])
        if not requested_dates:
            logger.error(f"No valid dates provided for savings {tracking_number}")
            return error_response(status_code=400, message="No valid dates provided")

        if requested_dates[0] != earliest_pending:
            logger.error(f"Requested dates for {tracking_number} do not start with earliest pending date {earliest_pending}")
            return error_response(
                status_code=400,
                message=f"Dates must start with the earliest unmarked date {earliest_pending} for savings {tracking_number}"
            )

        current_date = earliest_pending
        expected_date = current_date
        for requested_date in requested_dates:
            marking = next((m for m in all_account_markings if m.marked_date == requested_date), None)
            if not marking or marking.status != SavingsStatus.PENDING or marking.marked_by_id:
                logger.error(f"Invalid or already marked date {requested_date} for {tracking_number}, status: {marking.status if marking else 'not found'}")
                return error_response(
                    status_code=400,
                    message=f"Invalid or already marked date {requested_date} for {tracking_number}"
                )

            while expected_date < requested_date:
                intermediate_marking = next((m for m in all_account_markings if m.marked_date == expected_date), None)
                if intermediate_marking and intermediate_marking.status == SavingsStatus.PENDING:
                    logger.error(f"Non-sequential date {requested_date} for {tracking_number}; earlier date {expected_date} is still PENDING")
                    return error_response(
                        status_code=400,
                        message=f"Non-sequential date {requested_date}; earlier date {expected_date} must be marked first for {tracking_number}"
                    )
                expected_date += timedelta(days=1)

            if requested_date != expected_date:
                logger.error(f"Non-sequential date {requested_date} for {tracking_number}; expected {expected_date}")
                return error_response(
                    status_code=400,
                    message=f"Non-sequential date {requested_date}; expected {expected_date} for {tracking_number}"
                )
            expected_date += timedelta(days=1)

        commission_due = Decimal("0")
        start_date = savings.start_date
        for mark_request in mark_requests:
            marking = db.query(SavingsMarking).filter(
                SavingsMarking.savings_account_id == savings.id,
                SavingsMarking.marked_date == mark_request.marked_date,
                SavingsMarking.status == SavingsStatus.PENDING
            ).first()
            marking.payment_method = payment_method
            marking.unit_id = mark_request.unit_id or savings.unit_id
            marking.marked_by_id = current_user["user_id"]
            marking.updated_by = current_user["user_id"]
            total_amount += marking.amount
            days_since_start = (mark_request.marked_date - start_date).days + 1
            commission_periods = math.floor(days_since_start / savings.commission_days) + 1
            if days_since_start % savings.commission_days == 0 or (commission_periods == 1 and days_since_start <= savings.commission_days):
                commission_due += savings.commission_amount
            all_markings.append(marking)
            savings_accounts[savings.id] = savings
            if tracking_number not in marked_dates_by_tracking:
                marked_dates_by_tracking[tracking_number] = []
            marked_dates_by_tracking[tracking_number].append(marking.marked_date.isoformat())
        commission_due_by_savings[savings.id] = commission_due

    total_amount += sum(commission_due_by_savings.values())
    customer = db.query(User).filter(User.id == savings_accounts[list(savings_accounts.keys())[0]].customer_id).first()
    if not customer.email:
        logger.error(f"Customer {savings.customer_id} has no email")
        return error_response(status_code=400, message="Customer email required")

    first_tracking_number = list(marked_dates_by_tracking.keys())[0]
    short_uuid = str(uuid.uuid4())[:8]
    reference = f"sv_{first_tracking_number}_{short_uuid}"
    if len(reference) > 100:
        logger.warning(f"Generated reference too long: {reference}; truncating")
        reference = reference[:100]

    for savings_id, savings in savings_accounts.items():
        if savings.marking_status == MarkingStatus.NOT_STARTED:
            savings.marking_status = MarkingStatus.IN_PROGRESS
    db.commit()

    if payment_method == PaymentMethod.CARD:
        total_amount_kobo = int(total_amount * 100)
        response = Transaction.initialize(
            reference=reference,
            amount=total_amount_kobo,
            email=customer.email,
            callback_url="https://kopkad-frontend.vercel.app/payment-confirmation"
        )
        logger.info(f"Paystack initialize response: {response}")
        if response["status"]:
            for marking in all_markings:
                marking.payment_reference = reference
                marking.status = SavingsStatus.PENDING
            db.commit()
            logger.info(f"Card payment initiated for bulk marking, reference {reference}, dates: {marked_dates_by_tracking}, total_amount={total_amount}, includes commission_due={sum(commission_due_by_savings.values())}")
            return success_response(
                status_code=200,
                message="Proceed to payment for bulk marking",
                data={
                    "authorization_url": response["data"]["authorization_url"],
                    "reference": response["data"]["reference"],
                    "total_amount": total_amount,
                    "savings_accounts": [
                        {
                            "tracking_number": tn,
                            "unit_id": db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tn).first().unit_id,
                            "marked_dates": dates
                        }
                        for tn, dates in marked_dates_by_tracking.items()
                    ]
                }
            )
        logger.error(f"Paystack initialization failed: {response}")
        return error_response(status_code=500, message=f"Failed to initiate bulk card payment: {response.get('message', 'Unknown error')}")
    elif payment_method == PaymentMethod.BANK_TRANSFER:
        virtual_account = await initiate_virtual_account_payment(total_amount, customer.email, savings_accounts[list(savings_accounts.keys())[0]].customer_id, reference, db)
        if isinstance(virtual_account, dict):
            for marking in all_markings:
                marking.payment_reference = reference
                marking.status = SavingsStatus.PENDING
                marking.virtual_account_details = virtual_account
            db.commit()
            logger.info(f"Bank transfer initiated for bulk marking, reference {reference}, dates: {marked_dates_by_tracking}, total_amount={total_amount}, includes commission_due={sum(commission_due_by_savings.values())}")
            return success_response(
                status_code=200,
                message="Pay to the virtual account for bulk marking",
                data={
                    "virtual_account": virtual_account,
                    "reference": reference,
                    "total_amount": total_amount,
                    "savings_accounts": [
                        {
                            "tracking_number": tn,
                            "unit_id": db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tn).first().unit_id,
                            "marked_dates": dates
                        }
                        for tn, dates in marked_dates_by_tracking.items()
                    ]
                }
            )
        logger.error(f"Failed to initiate virtual account payment: {virtual_account}")
        return virtual_account
    logger.error(f"Invalid payment method {payment_method}")
    return error_response(status_code=400, message=f"Invalid payment method: {payment_method}")

async def end_savings_markings(tracking_number: str, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to end savings markings")

    savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    if not savings:
        return error_response(status_code=404, message=f"Savings {tracking_number} not found")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message=f"Not your savings {tracking_number}")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
        return error_response(status_code=401, message="Unauthorized role")

    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).all()
    if not markings:
        return error_response(status_code=404, message="No markings found for this savings account")

    savings.marking_status = MarkingStatus.COMPLETED
    for marking in markings:
        marking.updated_by = current_user["user_id"]
        marking.updated_at = datetime.now()

    total_commission = calculate_total_commission(savings)
    logger.info(f"Abruptly ended markings for savings {tracking_number} with total_commission={total_commission} for customer {savings.customer_id}")
    db.commit()
    return success_response(
        status_code=200,
        message="Savings markings ended successfully",
        data={
            "tracking_number": tracking_number,
            "completion_message": f"Congratulations! You have successfully completed your savings plan {tracking_number}!"
        }
    )

async def get_savings_metrics(tracking_number: str, db: Session):
    savings_account = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    
    if not savings_account:
        return error_response(status_code=404, message="Savings account not found")

    markings = db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings_account.id).all()

    if not markings:
        return error_response(status_code=404, message="No savings schedule found for this account")

    total_amount = savings_account.target_amount or sum(marking.amount for marking in markings)
    amount_marked = sum(marking.amount for marking in markings if marking.status == SavingsStatus.PAID)
    days_remaining = sum(1 for marking in markings if marking.status == SavingsStatus.PENDING)
    can_extend = savings_account.marking_status != MarkingStatus.COMPLETED and date.today() <= savings_account.end_date
    total_commission = calculate_total_commission(savings_account)

    # Check for existing payment request
    from models.payments import PaymentRequest, PaymentRequestStatus
    payment_request = db.query(PaymentRequest).filter(
        PaymentRequest.savings_account_id == savings_account.id,
        PaymentRequest.status.in_([
            PaymentRequestStatus.PENDING,
            PaymentRequestStatus.APPROVED
        ])
    ).first()
    
    payment_request_status = payment_request.status.value if payment_request else None

    response_data = SavingsMetricsResponse(
        tracking_number=tracking_number,
        savings_account_id=savings_account.id,
        total_amount=total_amount,
        amount_marked=amount_marked,
        days_remaining=days_remaining,
        can_extend=can_extend,
        total_commission=total_commission,
        marking_status=savings_account.marking_status,
        payment_request_status=payment_request_status
    ).model_dump()

    logger.info(f"Retrieved metrics for savings {tracking_number}: savings_account_id={savings_account.id}, total={total_amount}, marked={amount_marked}, days_remaining={days_remaining}, can_extend={can_extend}, total_commission={total_commission}, marking_status={savings_account.marking_status}, payment_request_status={payment_request_status}")
    return success_response(status_code=200, message="Savings metrics retrieved successfully", data=response_data)


async def verify_savings_payment(reference: str, db: Session):
    markings = db.query(SavingsMarking).filter(SavingsMarking.payment_reference == reference).all()
    if not markings:
        return error_response(status_code=404, message="Payment reference not found")

    payment_method = markings[0].payment_method
    savings_accounts = {m.savings_account_id: m.savings_account for m in markings}
    commission_due_by_savings = {}
    for savings_id, savings in savings_accounts.items():
        commission_due = Decimal("0")
        for marking in markings:
            if marking.savings_account_id == savings_id:
                days_since_start = (marking.marked_date - savings.start_date).days + 1
                commission_periods = math.floor(days_since_start / savings.commission_days) + 1
                if days_since_start % savings.commission_days == 0 or (commission_periods == 1 and days_since_start <= savings.commission_days):
                    commission_due += savings.commission_amount
        commission_due_by_savings[savings_id] = commission_due

    total_amount = sum(m.amount for m in markings) + sum(commission_due_by_savings.values())
    tracking_numbers = list({m.savings_account.tracking_number for m in markings})
    marked_dates = [m.marked_date.isoformat() for m in markings]

    logger.info(f"Verifying payment for reference {reference} with method {payment_method}, total_amount={total_amount}, includes commission_due={sum(commission_due_by_savings.values())}")

    response_data = {
        "reference": reference,
        "status": SavingsStatus.PENDING,
        "amount": str(total_amount),
        "tracking_numbers": tracking_numbers,
        "marked_dates": marked_dates,
    }

    completion_message = None
    if payment_method == PaymentMethod.CARD:
        response = Transaction.verify(reference=reference)
        logger.info(f"Paystack verify response: {response}")
        if response["status"] and response["data"]["status"] == "success":
            total_paid = Decimal(response["data"]["amount"]) / 100
            if total_paid < total_amount:
                logger.error(f"Underpayment for {reference}: expected {total_amount}, paid {total_paid}")
                return error_response(
                    status_code=400,
                    message=f"Paid amount {total_paid} less than expected {total_amount}"
                )
            for marking in markings:
                if marking.status != SavingsStatus.PENDING:
                    logger.error(f"Marking for date {marking.marked_date} is not PENDING (status: {marking.status})")
                    continue
                marking.status = SavingsStatus.PAID
                marking.marked_by_id = marking.updated_by
                marking.updated_at = datetime.now()
            db.commit()
            for savings_id in {m.savings_account_id for m in markings}:
                savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
                latest_marked_date = max(m.marked_date for m in markings if m.savings_account_id == savings_id)
                remaining_pending = db.query(SavingsMarking).filter(
                    SavingsMarking.savings_account_id == savings_id,
                    SavingsMarking.status == SavingsStatus.PENDING,
                    SavingsMarking.marked_date > latest_marked_date
                ).count()
                if remaining_pending == 0:
                    savings.marking_status = MarkingStatus.COMPLETED
                    total_commission = calculate_total_commission(savings)
                    completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}! Total commission: {total_commission}"
            db.commit()
            response_data["status"] = SavingsStatus.PAID
            logger.info(f"Card payment verified and marked as PAID for reference {reference}")
        else:
            logger.error(f"Card payment verification failed: {response.get('message', 'No message')}")
            return error_response(status_code=400, message="Payment verification failed")
    elif payment_method == PaymentMethod.BANK_TRANSFER:
        is_test_mode = "test" in os.getenv("PAYSTACK_SECRET_KEY", "").lower() or os.getenv("PAYSTACK_ENV", "production") == "test"
        if not is_test_mode:
            response = Transaction.verify(reference=reference)
            logger.info(f"Paystack verify response for bank transfer: {response}")
            if response["status"] and response["data"]["status"] == "success":
                total_paid = Decimal(response["data"]["amount"]) / 100
                if total_paid < total_amount:
                    logger.error(f"Underpayment for {reference}: expected {total_amount}, paid {total_paid}")
                    return error_response(
                        status_code=400,
                        message=f"Paid amount {total_paid} less than expected {total_amount}"
                    )
                for marking in markings:
                    if marking.status != SavingsStatus.PENDING:
                        logger.error(f"Marking for date {marking.marked_date} is not PENDING (status: {marking.status})")
                        continue
                    marking.status = SavingsStatus.PAID
                    marking.marked_by_id = marking.updated_by
                    marking.updated_at = datetime.now()
                db.commit()
                for savings_id in {m.savings_account_id for m in markings}:
                    savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
                    latest_marked_date = max(m.marked_date for m in markings if m.savings_account_id == savings_id)
                    remaining_pending = db.query(SavingsMarking).filter(
                        SavingsMarking.savings_account_id == savings_id,
                        SavingsMarking.status == SavingsStatus.PENDING,
                        SavingsMarking.marked_date > latest_marked_date
                    ).count()
                    if remaining_pending == 0:
                        savings.marking_status = MarkingStatus.COMPLETED
                        total_commission = calculate_total_commission(savings)
                        completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}! Total commission: {total_commission}"
                db.commit()
                response_data["status"] = SavingsStatus.PAID
                logger.info(f"Bank transfer payment verified and marked as PAID for reference {reference}")
            else:
                logger.error(f"Bank transfer verification failed: {response.get('message', 'No message')}")
                return error_response(status_code=400, message="Payment verification failed")
        else:
            logger.info(f"Test mode: Using confirm_bank_transfer for reference {reference}")
            current_user = {"user_id": markings[0].updated_by, "role": "customer"}
            return await confirm_bank_transfer(reference, current_user, db)
    else:
        return error_response(status_code=400, message=f"Unsupported payment method: {payment_method}")

    if completion_message:
        response_data["completion_message"] = completion_message
    return success_response(
        status_code=200,
        message="Payment details retrieved",
        data=response_data
    )

async def confirm_bank_transfer(reference: str, current_user: dict, db: Session):
    markings = db.query(SavingsMarking).filter(SavingsMarking.payment_reference == reference).all()
    if not markings:
        return error_response(status_code=404, message="Payment reference not found")

    if markings[0].payment_method != PaymentMethod.BANK_TRANSFER:
        return error_response(status_code=400, message="Reference is not for a bank transfer")

    savings = db.query(SavingsAccount).filter(SavingsAccount.id == markings[0].savings_account_id).first()
    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
        return error_response(status_code=401, message="Unauthorized role")

    savings_accounts = {m.savings_account_id: m.savings_account for m in markings}
    commission_due_by_savings = {}
    for savings_id, savings in savings_accounts.items():
        commission_due = Decimal("0")
        for marking in markings:
            if marking.savings_account_id == savings_id:
                days_since_start = (marking.marked_date - savings.start_date).days + 1
                commission_periods = math.floor(days_since_start / savings.commission_days) + 1
                if days_since_start % savings.commission_days == 0 or (commission_periods == 1 and days_since_start <= savings.commission_days):
                    commission_due += savings.commission_amount
        commission_due_by_savings[savings_id] = commission_due

    total_amount = sum(m.amount for m in markings) + sum(commission_due_by_savings.values())
    response = {
        "status": True,
        "data": {
            "status": "success",
            "amount": int(total_amount * 100)
        }
    }
    logger.info(f"Mock Paystack verify response for bank transfer: {response}")

    completion_message = None
    total_paid = Decimal(response["data"]["amount"]) / 100
    if total_paid < total_amount:
        logger.error(f"Underpayment for {reference}: expected {total_amount}, paid {total_paid}")
        return error_response(
            status_code=400,
            message=f"Paid amount {total_paid} less than expected {total_amount}"
        )
    for marking in markings:
        if marking.status != SavingsStatus.PENDING:
            logger.warning(f"Marking for date {marking.marked_date} is not PENDING (status: {marking.status})")
            continue
        marking.status = SavingsStatus.PAID
        marking.marked_by_id = current_user["user_id"]
        marking.updated_at = datetime.now()
        marking.updated_by = current_user["user_id"]
    for savings_id in {m.savings_account_id for m in markings}:
        savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
        latest_marked_date = max(m.marked_date for m in markings if m.savings_account_id == savings_id)
        remaining_pending = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings_id,
            SavingsMarking.status == SavingsStatus.PENDING,
            SavingsMarking.marked_date > latest_marked_date
        ).count()
        if remaining_pending == 0:
            savings.marking_status = MarkingStatus.COMPLETED
            total_commission = calculate_total_commission(savings)
            completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}! Total commission: {total_commission}"
    db.commit()
    logger.info(f"Bank transfer confirmed for reference {reference}, marked as PAID")
    response_data = {
        "reference": reference,
        "status": SavingsStatus.PAID,
        "amount": str(total_amount),
        "tracking_numbers": list({m.savings_account.tracking_number for m in markings}),
        "marked_dates": [m.marked_date.isoformat() for m in markings],
    }
    if completion_message:
        response_data["completion_message"] = completion_message
    return success_response(
        status_code=200,
        message="Bank transfer confirmed successfully",
        data=response_data
    )