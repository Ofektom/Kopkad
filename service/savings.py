from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from models.savings import SavingsAccount, SavingsMarking, SavingsType, SavingsStatus, PaymentMethod, MarkingStatus, PaymentInitiationStatus, PaymentInitiation
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
from models.expenses import ExpenseCard, Expense
from datetime import datetime
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

from store.repositories import (
    BusinessRepository,
    SavingsRepository,
    UnitRepository,
    UserBusinessRepository,
    UserRepository,
    UserNotificationRepository,
)
from models.financial_advisor import NotificationType, NotificationPriority
from service.notifications import notify_user, notify_business_admin

paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

logging.basicConfig(
    filename="savings.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def calculate_total_commission(savings: SavingsAccount) -> Decimal:
    if not savings.commission_days or savings.commission_days <= 0:
        return Decimal("0.00")
        
    total_days = _calculate_total_days(savings.start_date, savings.duration_months)
    commission_periods = math.ceil(total_days / savings.commission_days)
    total_commission = savings.commission_amount * Decimal(commission_periods)
    return total_commission.quantize(Decimal("0.01"))


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


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

async def create_savings_daily(
    request: SavingsCreateDaily,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    savings_repo: SavingsRepository | None = None,
    unit_repo: UnitRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
    business_repo: BusinessRepository | None = None,
):
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    unit_repo = _resolve_repo(unit_repo, UnitRepository, db)
    session = user_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not has_permission(current_user_obj, Permission.CREATE_SAVINGS, session):
        return error_response(status_code=403, message="No permission to create savings")

    customer_id = (
        current_user["user_id"] if current_user["role"] == "customer" else
        request.customer_id if current_user["role"] in ["agent", "sub_agent", "admin", "super_admin"] else
        None
    )
    if not customer_id:
        return error_response(status_code=400, message="Invalid customer_id or role")

    customer = session.query(User).filter(User.id == customer_id, User.role == "customer").first()
    if not customer:
        return error_response(status_code=400, message=f"User {customer_id} is not a customer")

    if request.daily_amount <= 0 or request.duration_months <= 0:
        return error_response(status_code=400, message="Daily amount and duration must be positive")

    if request.commission_days <= 0:
        return error_response(status_code=400, message="Commission days must be positive")

    unit_exists = savings_repo.get_customer_unit_association(
        user_id=customer_id,
        unit_id=request.unit_id,
        business_id=request.business_id,
    )
    if not unit_exists:
        return error_response(status_code=400, message=f"Customer {customer_id} is not associated with unit {request.unit_id} in business {request.business_id}")

    total_days = _calculate_total_days(request.start_date, request.duration_months)
    total_amount = request.daily_amount * Decimal(total_days)
    commission_amount = request.commission_amount if request.commission_amount is not None else request.daily_amount

    if commission_amount < 0:
        return error_response(status_code=400, message="Commission amount cannot be negative")

    tracking_number = _generate_unique_tracking_number(session, SavingsAccount)
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
    session.add(savings)
    session.flush()

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
    session.add_all(markings)
    session.commit()

    logger.info(f"Created daily savings {tracking_number} with {len(markings)} markings for customer {customer_id}")
    
    # Notify customer about savings account creation
    await notify_user(
        user_id=customer_id,
        notification_type=NotificationType.SAVINGS_ACCOUNT_CREATED,
        title="Savings Account Created",
        message=f"Your daily savings account {tracking_number} has been created successfully. Daily amount: {request.daily_amount:.2f}",
        priority=NotificationPriority.LOW,
        db=session,
        notification_repo=notification_repo,
        related_entity_id=savings.id,
        related_entity_type="savings_account",
    )
    
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

async def create_savings_target(
    request: SavingsCreateTarget,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    savings_repo: SavingsRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    session = user_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not has_permission(current_user_obj, Permission.CREATE_SAVINGS, session):
        return error_response(status_code=403, message="No permission to create savings")

    customer_id = (
        current_user["user_id"] if current_user["role"] == "customer" else
        request.customer_id if current_user["role"] in ["agent", "sub_agent", "admin", "super_admin"] else
        None
    )
    if not customer_id:
        return error_response(status_code=400, message="Invalid customer_id or role")

    customer = session.query(User).filter(User.id == customer_id, User.role == "customer").first()
    if not customer:
        return error_response(status_code=400, message=f"User {customer_id} is not a customer")

    if request.target_amount <= 0:
        return error_response(status_code=400, message="Target amount must be positive")
    total_days = (request.end_date - request.start_date).days + 1
    if total_days <= 0:
        return error_response(status_code=400, message="End date must be after start date")

    if request.commission_days <= 0:
        return error_response(status_code=400, message="Commission days must be positive")

    unit_exists = savings_repo.get_customer_unit_association(
        user_id=customer_id,
        unit_id=request.unit_id,
        business_id=request.business_id,
    )
    if not unit_exists:
        return error_response(status_code=400, message=f"Customer {customer_id} is not associated with unit {request.unit_id} in business {request.business_id}")

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    tracking_number = _generate_unique_tracking_number(session, SavingsAccount)
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
    session.add(savings)
    session.flush()

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
    session.add_all(markings)
    session.commit()

    # Notify customer about savings account creation
    await notify_user(
        user_id=customer_id,
        notification_type=NotificationType.SAVINGS_ACCOUNT_CREATED,
        title="Savings Account Created",
        message=f"Your target savings account {tracking_number} has been created successfully. Target amount: {request.target_amount:.2f}",
        priority=NotificationPriority.LOW,
        db=session,
        notification_repo=notification_repo,
        related_entity_id=savings.id,
        related_entity_type="savings_account",
    )

    return _savings_response(savings)

async def extend_savings(
    request: SavingsExtend,
    current_user: dict,
    db: Session,
    *,
    notification_repo: UserNotificationRepository | None = None,
):
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
    
    # Notify customer about extension
    await notify_user(
        user_id=savings.customer_id,
        notification_type=NotificationType.SAVINGS_ACCOUNT_EXTENDED,
        title="Savings Account Extended",
        message=f"Your savings account {savings.tracking_number} has been extended by {request.additional_months} months. New end date: {savings.end_date}",
        priority=NotificationPriority.LOW,
        db=db,
        notification_repo=notification_repo,
        related_entity_id=savings.id,
        related_entity_type="savings_account",
    )
    
    return _savings_response(savings)

async def update_savings(
    savings_id: int,
    request: SavingsUpdate,
    current_user: dict,
    db: Session,
    *,
    notification_repo: UserNotificationRepository | None = None,
):
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
    
    # Notify customer about update
    await notify_user(
        user_id=savings.customer_id,
        notification_type=NotificationType.SAVINGS_ACCOUNT_UPDATED,
        title="Savings Account Updated",
        message=f"Your savings account {savings.tracking_number} has been updated successfully.",
        priority=NotificationPriority.LOW,
        db=db,
        notification_repo=notification_repo,
        related_entity_id=savings.id,
        related_entity_type="savings_account",
    )
    
    return _savings_response(savings)

async def delete_savings(
    savings_id: int,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    savings_repo: SavingsRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
    business_repo: BusinessRepository | None = None,
):
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    session = savings_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, session):
        return error_response(status_code=403, message="No permission to delete savings")

    savings = session.query(SavingsAccount).filter(SavingsAccount.id == savings_id).first()
    if not savings:
        return error_response(status_code=404, message="Savings account not found")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "customer"]:
        return error_response(status_code=401, message="Unauthorized role")

    has_paid_markings = session.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings_id,
        SavingsMarking.status == SavingsStatus.PAID
    ).first()
    if has_paid_markings:
        return error_response(status_code=400, message="Cannot delete savings account with paid markings")

    tracking_number = savings.tracking_number
    customer_id = savings.customer_id
    business_id = savings.business_id
    session.delete(savings)
    session.commit()

    logger.info(f"Deleted savings account {tracking_number} (ID: {savings_id}) for customer {customer_id}")
    
    # Notify customer about deletion
    await notify_user(
        user_id=customer_id,
        notification_type=NotificationType.SAVINGS_ACCOUNT_DELETED,
        title="Savings Account Deleted",
        message=f"Your savings account {tracking_number} has been deleted.",
        priority=NotificationPriority.MEDIUM,
        db=session,
        notification_repo=notification_repo,
        related_entity_id=savings_id,
        related_entity_type="savings_account",
    )
    
    # Notify business admin about deletion
    if business_id:
        await notify_business_admin(
            business_id=business_id,
            notification_type=NotificationType.SAVINGS_ACCOUNT_DELETED,
            title="Savings Account Deleted",
            message=f"Savings account {tracking_number} has been deleted.",
            priority=NotificationPriority.MEDIUM,
            db=session,
            business_repo=business_repo,
            notification_repo=notification_repo,
            related_entity_id=savings_id,
            related_entity_type="savings_account",
        )
    
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
    search: str | None,
    limit: int,
    offset: int,
    current_user: dict,
    db: Session,
    *,
    savings_repo: SavingsRepository | None = None,
    user_repo: UserRepository | None = None,
    business_repo: BusinessRepository | None = None,
    user_business_repo: UserBusinessRepository | None = None,
    unit_repo: UnitRepository | None = None,
):
    target_business_id: int | None = None
    effective_customer_id: int | None = None

    role = current_user["role"]

    if role == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own savings")
        effective_customer_id = current_user["user_id"]
        if business_id:
            user_business_ids = [b.id for b in current_user_obj.businesses]
            if business_id not in user_business_ids:
                return error_response(status_code=403, message="You don't have access to this business")
            target_business_id = business_id
        elif current_user.get("active_business_id"):
            target_business_id = current_user["active_business_id"]

    elif role in {"agent", "sub_agent"}:
        business_ids = [b.id for b in business_repo.get_user_businesses_with_units(current_user["user_id"]) or []]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")

        if business_id:
            if business_id not in business_ids:
                return error_response(status_code=403, message="You don't have access to this business")
            target_business_id = business_id
        elif current_user.get("active_business_id") and current_user["active_business_id"] in business_ids:
            target_business_id = current_user["active_business_id"]
        else:
            return error_response(status_code=400, message="Please specify a business_id or set an active business")

    elif role == "admin":
        target_business_id = business_id or current_user.get("active_business_id")
        if not target_business_id:
            return error_response(status_code=400, message="Please specify a business_id parameter")

    elif role == "super_admin":
        target_business_id = business_id or current_user.get("active_business_id")

    else:
        return error_response(status_code=401, message="Unauthorized role")

    if customer_id and role != "customer":
        customer = user_repo.find_one_by(id=customer_id, role="customer")
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        effective_customer_id = customer_id

    if limit < 1 or offset < 0:
        return error_response(status_code=400, message="Limit must be positive and offset non-negative")

    savings, total_count = savings_repo.get_savings_with_filters(
        customer_id=effective_customer_id,
        business_id=target_business_id,
        unit_id=unit_id,
        savings_type=savings_type,
        search=search,
        limit=limit,
        offset=offset,
    )

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
        },
    )

async def get_savings_markings_by_tracking_number(
    tracking_number: str,
    db: Session,
    *,
    savings_repo: SavingsRepository | None = None,
):
    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    session = savings_repo.db

    savings_account = session.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    
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

async def mark_savings_payment(
    tracking_number: str,
    request: SavingsMarkingRequest,
    current_user: dict,
    db: Session,
):
    """
    Initiate payment for a single savings marking.
    - Idempotent via idempotency_key
    - Defers actual marking to verify step
    """
    savings = db.query(SavingsAccount).filter(
        SavingsAccount.tracking_number == tracking_number
    ).first()
    if not savings:
        raise HTTPException(404, f"Savings {tracking_number} not found")

    if savings.marking_status == MarkingStatus.COMPLETED:
        raise HTTPException(400, f"Cannot mark completed savings {tracking_number}")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        raise HTTPException(403, "Not your savings account")

    marking = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings.id,
        SavingsMarking.marked_date == request.marked_date,
        SavingsMarking.status == SavingsStatus.PENDING
    ).first()
    if not marking:
        raise HTTPException(400, f"Date {request.marked_date} invalid or already marked")

    total_amount = marking.amount
    if total_amount <= 0:
        raise HTTPException(400, "Contribution amount must be positive")

    customer = db.query(User).filter(User.id == savings.customer_id).first()
    if not customer or not customer.email:
        raise HTTPException(400, "Customer email required for payment")

    # ── Idempotency check ──
    reference = None
    existing = None

    if request.idempotency_key:
        existing = db.query(PaymentInitiation).filter(
            PaymentInitiation.idempotency_key == request.idempotency_key,
            PaymentInitiation.status == PaymentInitiationStatus.PENDING.value,
            PaymentInitiation.user_id == current_user["user_id"]
        ).first()
        if existing:
            logger.info(f"Single marking idempotency hit - reusing ref {existing.reference}")
            reference = existing.reference

    # ── New initiation if needed ──
    if not reference:
        ref_suffix = str(uuid.uuid4())[:8]
        reference = f"sv_{tracking_number}_{ref_suffix}"

        total_kobo = int(total_amount * 100)
        resp = Transaction.initialize(
            reference=reference,
            amount=total_kobo,
            email=customer.email,
            metadata={
                "source": "single_marking",
                "tracking_number": tracking_number,
                "marked_date": str(request.marked_date),
                "idempotency_key": request.idempotency_key,
            }
        )

        if not resp["status"]:
            raise HTTPException(500, f"Paystack init failed: {resp.get('message')}")

        reference = resp["data"]["reference"]

        initiation = PaymentInitiation(
            idempotency_key=request.idempotency_key,
            reference=reference,
            status=PaymentInitiationStatus.PENDING,
            user_id=current_user["user_id"],
            savings_account_id=savings.id,
            savings_marking_id=marking.id,
            payment_method=request.payment_method.value if request.payment_method else "card",
            payment_metadata={
                "type": "single",
                "marking_id": marking.id,
                "tracking_number": tracking_number,
                "marked_date": str(request.marked_date),
                "amount": float(total_amount),
            }
        )
        db.add(initiation)
        db.commit()

    return success_response(
        status_code=200,
        message="Proceed to payment",
        data={
            "payment_reference": reference,
            "total_amount": float(total_amount),
            "tracking_number": tracking_number,
            "marked_date": str(request.marked_date),
        }
    )


async def mark_savings_bulk(
    request: BulkMarkSavingsRequest,
    current_user: dict,
    db: Session,
):
    """
    Initiate bulk payment for multiple savings markings.
    - Idempotent
    - Defers marking to verify
    """
    if not request.markings:
        raise HTTPException(400, "No markings provided")

    # Validate all markings belong to same user & are pending
    savings_ids = set()
    marking_ids = []
    total_amount = Decimal("0")
    tracking_numbers = set()

    for m in request.markings:
        marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == m.savings_account_id,
            SavingsMarking.marked_date == m.marked_date,
            SavingsMarking.status == SavingsStatus.PENDING
        ).first()
        if not marking:
            raise HTTPException(400, f"Invalid or already marked: {m.marked_date}")

        savings = db.query(SavingsAccount).get(m.savings_account_id)
        if not savings:
            raise HTTPException(404, f"Savings account {m.savings_account_id} not found")

        if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
            raise HTTPException(403, "Not your savings account")

        total_amount += marking.amount
        marking_ids.append(marking.id)
        savings_ids.add(savings.id)
        tracking_numbers.add(savings.tracking_number)

    if total_amount <= 0:
        raise HTTPException(400, "Total amount must be positive")

    # ── Idempotency check ──
    reference = None
    existing = None

    if request.idempotency_key:
        existing = db.query(PaymentInitiation).filter(
            PaymentInitiation.idempotency_key == request.idempotency_key,
            PaymentInitiation.status == PaymentInitiationStatus.PENDING.value,
            PaymentInitiation.user_id == current_user["user_id"]
        ).first()
        if existing:
            logger.info(f"Bulk idempotency hit - reusing ref {existing.reference}")
            reference = existing.reference

    # ── New initiation if needed ──
    if not reference:
        ref_suffix = str(uuid.uuid4())[:8]
        reference = f"sv_bulk_{ref_suffix}"

        customer = db.query(User).filter(
            User.id == current_user["user_id"]
        ).first()
        if not customer or not customer.email:
            raise HTTPException(400, "Customer email required")

        total_kobo = int(total_amount * 100)
        resp = Transaction.initialize(
            reference=reference,
            amount=total_kobo,
            email=customer.email,
            metadata={
                "source": "bulk_marking",
                "marking_ids": marking_ids,
                "idempotency_key": request.idempotency_key,
            }
        )

        if not resp["status"]:
            raise HTTPException(500, f"Paystack init failed: {resp.get('message')}")

        reference = resp["data"]["reference"]

        initiation = PaymentInitiation(
            idempotency_key=request.idempotency_key,
            reference=reference,
            status=PaymentInitiationStatus.PENDING,
            user_id=current_user["user_id"],
            savings_account_id=None,  # bulk
            savings_marking_id=None,
            payment_method=request.payment_method.value,
            payment_metadata={
                "type": "bulk",
                "marking_ids": marking_ids,
                "total_amount": float(total_amount),
                "tracking_numbers": list(tracking_numbers),
            }
        )
        db.add(initiation)
        db.commit()

    return success_response(
        status_code=200,
        message="Proceed to bulk payment",
        data={
            "payment_reference": reference,
            "total_amount": float(total_amount),
        }
    )


async def verify_savings_payment(reference: str, db: Session):
    """
    Verify Paystack payment for savings markings (single or bulk).
    - Idempotent: safe to call multiple times
    - Updates markings to PAID if successful
    - Marks initiation as COMPLETED
    - Checks if any savings plans are now fully completed
    """
    logger.info(f"[SAVINGS-VERIFY] Starting verification for reference: {reference}")

    initiation = db.query(PaymentInitiation).filter(
        PaymentInitiation.reference == reference
    ).first()

    if not initiation:
        logger.error(f"[SAVINGS-VERIFY] Initiation not found for reference {reference}")
        raise HTTPException(404, "Payment initiation not found")

    # Idempotent: already completed → early return
    if initiation.status == PaymentInitiationStatus.COMPLETED.value:
        logger.info(f"[SAVINGS-VERIFY] Already completed - idempotent success")
        return success_response(200, "Payment already verified")

    # Safety check: wrong state
    if initiation.status != PaymentInitiationStatus.PENDING.value:
        logger.warning(f"[SAVINGS-VERIFY] Invalid state for {reference}: {initiation.status}")
        raise HTTPException(400, "Initiation not in pending state")

    # Verify with Paystack
    resp = Transaction.verify(reference=reference)
    if not resp["status"] or resp["data"]["status"] != "success":
        logger.error(f"[SAVINGS-VERIFY] Paystack verification failed: {resp.get('message')}")
        initiation.status = PaymentInitiationStatus.FAILED.value
        db.commit()
        raise HTTPException(400, "Payment verification failed")

    paid_amount = Decimal(resp["data"]["amount"]) / 100
    logger.info(f"[SAVINGS-VERIFY] Paid amount: {paid_amount}")

    # Extract from metadata (supports both single and bulk)
    metadata = initiation.payment_metadata or {}
    marking_ids = metadata.get("marking_ids", []) or [metadata.get("marking_id")]
    if not marking_ids:
        logger.error("[SAVINGS-VERIFY] No marking_ids in metadata")
        initiation.status = PaymentInitiationStatus.FAILED.value
        db.commit()
        raise HTTPException(400, "No markings associated with this initiation")

    markings = db.query(SavingsMarking).filter(
        SavingsMarking.id.in_(marking_ids),
        SavingsMarking.status == SavingsStatus.PENDING
    ).all()

    expected = sum(m.amount for m in markings)
    if paid_amount < expected:
        logger.error(f"[SAVINGS-VERIFY] Underpayment: {paid_amount} < {expected}")
        initiation.status = PaymentInitiationStatus.FAILED.value
        db.commit()
        raise HTTPException(400, f"Underpayment: {paid_amount} < {expected}")

    # Update markings to PAID
    for marking in markings:
        marking.status = SavingsStatus.PAID
        marking.payment_reference = reference
        marking.updated_at = datetime.utcnow()
        # marked_by_id already set during initiation if needed

    db.commit()
    logger.info(f"[SAVINGS-VERIFY] Updated {len(markings)} markings to PAID")

    # Check for completed savings plans
    savings_ids = {m.savings_account_id for m in markings}
    completion_messages = []

    for savings_id in savings_ids:
        savings = db.query(SavingsAccount).get(savings_id)
        if not savings:
            continue

        pending_count = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings_id,
            SavingsMarking.status == SavingsStatus.PENDING
        ).count()

        if pending_count == 0 and savings.marking_status != MarkingStatus.COMPLETED:
            savings.marking_status = MarkingStatus.COMPLETED
            total_commission = calculate_total_commission(savings)
            completion_messages.append(
                f"Congratulations! You have successfully completed savings plan {savings.tracking_number}! "
                f"Total commission: {total_commission}"
            )

    db.commit()

    # Mark initiation completed
    initiation.status = PaymentInitiationStatus.COMPLETED.value
    db.commit()
    logger.info(f"[SAVINGS-VERIFY] Initiation marked COMPLETED")

    # Build response
    response_data = {
        "reference": reference,
        "status": "PAID",
        "paid_amount": float(paid_amount),
        "markings_updated": len(markings),
        "tracking_numbers": list({m.savings_account.tracking_number for m in markings if m.savings_account}),
        "marked_dates": [m.marked_date.isoformat() for m in markings],
    }

    if completion_messages:
        response_data["completion_message"] = " ".join(completion_messages)

    return success_response(
        status_code=200,
        message="Payment verified successfully",
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
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "customer"]:
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

async def end_savings_markings(tracking_number: str, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not has_permission(current_user_obj, Permission.UPDATE_SAVINGS, db):
        return error_response(status_code=403, message="No permission to end savings markings")

    savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == tracking_number).first()
    if not savings:
        return error_response(status_code=404, message=f"Savings {tracking_number} not found")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message=f"Not your savings {tracking_number}")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "customer"]:
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

async def get_savings_metrics(
    user_id: str,
    db: Session,
    tracking_number: str = None,
    business_id: int = None,
    *,
    savings_repo: SavingsRepository | None = None,
    user_repo: UserRepository | None = None,
):
    logger.info(f"Fetching savings metrics for user_id: {user_id}, tracking_number: {tracking_number}, business_id: {business_id}")

    savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    session = savings_repo.db

    if tracking_number:
        # Metrics for a specific savings account (for SavingsMarkings.jsx)
        savings_account = session.query(SavingsAccount).filter(
            SavingsAccount.tracking_number == tracking_number,
            SavingsAccount.customer_id == user_id
        ).first()

        if not savings_account:
            logger.error(f"Savings account {tracking_number} not found for user {user_id}")
            return error_response(status_code=404, message="Savings account not found")

        markings = session.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings_account.id).all()

        if not markings:
            logger.error(f"No markings found for savings {tracking_number}")
            return error_response(status_code=404, message="No savings schedule found for this account")

        total_amount = savings_account.target_amount or sum(marking.amount for marking in markings)
        amount_marked = sum(marking.amount for marking in markings if marking.status == SavingsStatus.PAID)
        days_remaining = sum(1 for marking in markings if marking.status == SavingsStatus.PENDING)
        can_extend = savings_account.marking_status != MarkingStatus.COMPLETED and date.today() <= savings_account.end_date
        total_commission = calculate_total_commission(savings_account)

        # Check for existing payment request
        from models.payments import PaymentRequest, PaymentRequestStatus

        payment_request = session.query(PaymentRequest).filter(
            PaymentRequest.savings_account_id == savings_account.id,
            PaymentRequest.status.in_(
                [PaymentRequestStatus.PENDING, PaymentRequestStatus.APPROVED]
            ),
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
            payment_request_status=payment_request_status,
        ).model_dump()

        logger.info(
            "Retrieved metrics for savings %s: savings_account_id=%s, total=%s, marked=%s, days_remaining=%s, "
            "can_extend=%s, total_commission=%s, marking_status=%s, payment_request_status=%s",
            tracking_number,
            savings_account.id,
            total_amount,
            amount_marked,
            days_remaining,
            can_extend,
            total_commission,
            savings_account.marking_status,
            payment_request_status,
        )
        return success_response(status_code=200, message="Savings metrics retrieved successfully", data=response_data)

    # Aggregated metrics for all accounts (for Savings.jsx and Dashboard)
    user = user_repo.get_by_id(user_id)
    target_business_id = business_id or (user.active_business_id if user else None)

    today = datetime.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = month_start + relativedelta(months=1)
    logger.info(
        "Month range: %s to %s, business_id: %s",
        month_start.date(),
        month_end.date(),
        target_business_id,
    )

    total_savings_query = (
        session.query(func.coalesce(func.sum(SavingsMarking.amount), 0))
        .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
        .filter(
            SavingsAccount.customer_id == user_id,
            SavingsMarking.status == SavingsStatus.PAID,
        )
    )
    if target_business_id:
        total_savings_query = total_savings_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    total_savings_all_time = total_savings_query.scalar()

    this_month_query = (
        session.query(func.coalesce(func.sum(SavingsMarking.amount), 0))
        .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
        .filter(
            SavingsAccount.customer_id == user_id,
            SavingsMarking.status == SavingsStatus.PAID,
            SavingsMarking.marked_date >= month_start,
            SavingsMarking.marked_date < month_end,
        )
    )
    if target_business_id:
        this_month_query = this_month_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    this_month_savings = this_month_query.scalar()

    total_cards_query = session.query(SavingsAccount).filter(SavingsAccount.customer_id == user_id)
    if target_business_id:
        total_cards_query = total_cards_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    total_savings_cards = total_cards_query.count()

    total_markings_query = (
        session.query(func.count(SavingsMarking.id))
        .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
        .filter(SavingsAccount.customer_id == user_id)
    )
    if target_business_id:
        total_markings_query = total_markings_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    total_markings_all_time = total_markings_query.scalar()

    pending_markings_query = (
        session.query(func.count(SavingsMarking.id))
        .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
        .filter(
            SavingsAccount.customer_id == user_id,
            SavingsMarking.status == SavingsStatus.PENDING,
        )
    )
    if target_business_id:
        pending_markings_query = pending_markings_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    total_pending_markings = pending_markings_query.scalar()

    paid_markings_query = (
        session.query(func.count(SavingsMarking.id))
        .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
        .filter(
            SavingsAccount.customer_id == user_id,
            SavingsMarking.status == SavingsStatus.PAID,
        )
    )
    if target_business_id:
        paid_markings_query = paid_markings_query.filter(
            SavingsAccount.business_id == target_business_id
        )
    total_paid_markings = paid_markings_query.scalar()

    logger.info(
        "Aggregated metrics for user %s: cards=%s, total_markings=%s, pending_markings=%s, paid_markings=%s",
        user_id,
        total_savings_cards,
        total_markings_all_time,
        total_pending_markings,
        total_paid_markings,
    )

    response_data = {
        "overview": {
            "total_savings_all_time": float(total_savings_all_time or 0),
            "total_savings_this_month": float(this_month_savings or 0),
            "total_savings_cards": total_savings_cards,
        },
        "markings": {
            "total_markings": int(total_markings_all_time or 0),
            "pending_markings": int(total_pending_markings or 0),
            "completed_markings": int(total_paid_markings or 0),
        },
    }

    logger.info("Aggregated metrics payload for user %s: %s", user_id, response_data)
    return success_response(
        status_code=200,
        message="Savings metrics retrieved successfully",
        data=response_data,
    )

async def get_monthly_summary(current_user: dict, db: Session, business_id: int | None = None):
    """Get monthly summary of savings and expenses for the current month, plus all-time totals"""
    
    # Get current month start and end dates
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
    else:
        month_end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)
    
    user_id = current_user["user_id"]
    
    # Calculate total savings for current month (amount marked in current month)
    total_savings_current_month = db.query(
        func.coalesce(func.sum(SavingsMarking.amount), 0)
    ).join(
        SavingsAccount, SavingsMarking.savings_account_id == SavingsAccount.id
    ).filter(
        SavingsAccount.customer_id == user_id,
        SavingsMarking.status == SavingsStatus.PAID,
        SavingsMarking.marked_date >= month_start.date(),
        SavingsMarking.marked_date <= month_end.date()
    ).scalar() or Decimal('0')
    
    if business_id:
        total_savings_current_month = db.query(
            func.coalesce(func.sum(SavingsMarking.amount), 0)
        ).join(
            SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id
        ).filter(
            SavingsAccount.customer_id == user_id,
            SavingsAccount.business_id == business_id,
            SavingsMarking.status == SavingsStatus.PAID,
            SavingsMarking.marked_date >= month_start.date(),
            SavingsMarking.marked_date <= month_end.date(),
        ).scalar() or Decimal("0")
    
    # Calculate total expenses for current month
    total_expenses_current_month = db.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).join(
        ExpenseCard, Expense.expense_card_id == ExpenseCard.id
    ).filter(
        ExpenseCard.customer_id == user_id,
        Expense.created_at >= month_start,
        Expense.created_at <= month_end
    ).scalar() or Decimal('0')
    
    # Calculate ALL-TIME total savings (all paid markings ever)
    total_savings_all_time_query = db.query(
        func.coalesce(func.sum(SavingsMarking.amount), 0)
    ).join(
        SavingsAccount, SavingsMarking.savings_account_id == SavingsAccount.id
    ).filter(
        SavingsAccount.customer_id == user_id,
        SavingsMarking.status == SavingsStatus.PAID
    )
    if business_id:
        total_savings_all_time_query = total_savings_all_time_query.filter(SavingsAccount.business_id == business_id)
    total_savings_all_time = total_savings_all_time_query.scalar() or Decimal("0")
    
    # Calculate ALL-TIME total expenses (all expenses ever)
    total_expenses_all_time = db.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).join(
        ExpenseCard, Expense.expense_card_id == ExpenseCard.id
    ).filter(
        ExpenseCard.customer_id == user_id
    ).scalar() or Decimal('0')
    
    return success_response(
        status_code=200,
        message="Monthly summary retrieved successfully",
        data={
            "month": now.strftime("%B %Y"),
            # Current month totals
            "total_savings": float(total_savings_current_month),
            "total_expenses": float(total_expenses_current_month),
            "net_balance": float(total_savings_current_month - total_expenses_current_month),
            # All-time totals
            "total_savings_all_time": float(total_savings_all_time),
            "total_expenses_all_time": float(total_expenses_all_time),
            "net_balance_all_time": float(total_savings_all_time - total_expenses_all_time)
        }
    )