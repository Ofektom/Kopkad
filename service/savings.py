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
    SavingsReinitiateDaily,
    SavingsReinitiateTarget,
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

paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))

logging.basicConfig(
    filename="savings.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

        # Check if payment_provider_customer_id exists; if not, create Paystack customer
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

        # Check if in test mode (based on PAYSTACK_SECRET_KEY or environment variable)
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
            # Check for existing dedicated account
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
                # Check if NUBAN is unavailable
                if dedicated_data.get("code") == "feature_unavailable":
                    logger.error(f"Dedicated NUBAN not available: {dedicated_data}")
                    return error_response(
                        status_code=400,
                        message="Virtual account payments are currently unavailable. Please contact support@paystack.com to enable this feature.",
                    )
                # Attempt to create new dedicated account
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

        # Initialize transaction for payment tracking
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

    total_amount = sum(m.amount for m in markings)
    response = Transaction.verify(reference=reference)
    logger.info(f"Paystack verify response for bank transfer: {response}")

    completion_message = None
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
                logger.warning(f"Marking for date {marking.marked_date} is not PENDING (status: {marking.status})")
                continue
            marking.status = SavingsStatus.PAID
            marking.marked_by_id = current_user["user_id"]  # Ensure marked_by_id is set
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
                completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}!"
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
    else:
        logger.error(f"Bank transfer verification failed: {response.get('message', 'No message')}")
        virtual_account = markings[0].virtual_account_details or {"bank": "Unknown", "account_number": "Unknown", "account_name": "Unknown"}
        return success_response(
            status_code=200,
            message="Bank transfer not yet verified, please confirm after payment",
            data={
                "reference": reference,
                "status": SavingsStatus.PENDING,
                "amount": str(total_amount),
                "tracking_numbers": list({m.savings_account.tracking_number for m in markings}),
                "marked_dates": [m.marked_date.isoformat() for m in markings],
                "virtual_account": virtual_account,
            }
        )

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
        for day in range(existing_days, total_days):
            new_marking = SavingsMarking(
                savings_account_id=savings.id,
                unit_id=savings.unit_id,
                amount=savings.daily_amount,
                marked_date=savings.start_date + timedelta(days=day),
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
        target_amount=total_amount,
        created_by=current_user["user_id"],
        marking_status=MarkingStatus.NOT_STARTED,
    )
    db.add(savings)
    db.flush()

    logger.info(f"Set target_amount={total_amount} for daily savings {tracking_number} with {total_days} days")
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
        created_by=current_user["user_id"],
        marking_status=MarkingStatus.NOT_STARTED,
    )
    db.add(savings)
    db.flush()

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

    if savings.marking_status != MarkingStatus.COMPLETED:
        return error_response(
            status_code=400,
            message=f"Savings {savings.tracking_number} not fully completed (status: {savings.marking_status})",
        )

    if request.daily_amount <= 0 or request.duration_months <= 0:
        return error_response(status_code=400, message="Daily amount and duration must be positive")

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

    total_days = _calculate_total_days(request.start_date, request.duration_months)
    total_amount = request.daily_amount * Decimal(total_days)
    end_date = request.start_date + relativedelta(months=request.duration_months) - timedelta(days=1)
    savings.daily_amount = request.daily_amount
    savings.duration_months = request.duration_months
    savings.start_date = request.start_date
    savings.end_date = end_date
    savings.commission_days = request.commission_days
    savings.target_amount = total_amount
    savings.savings_type = SavingsType.DAILY
    savings.business_id = request.business_id
    savings.unit_id = request.unit_id
    savings.updated_by = current_user["user_id"]
    savings.marking_status = MarkingStatus.NOT_STARTED
    db.flush()

    db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).delete()
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

    logger.info(f"Reinitiated daily savings {savings.tracking_number} with target_amount={total_amount} for customer {current_user['user_id']}")
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

    if savings.marking_status != MarkingStatus.COMPLETED:
        return error_response(
            status_code=400,
            message=f"Savings {savings.tracking_number} not fully completed (status: {savings.marking_status})",
        )

    if request.target_amount <= 0:
        return error_response(status_code=400, message="Target amount must be positive")
    total_days = (request.end_date - request.start_date).days + 1
    if total_days <= 0:
        return error_response(status_code=400, message="End date must be after start date")

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

    duration_months = (request.end_date.year - request.start_date.year) * 12 + request.end_date.month - request.start_date.month + 1
    daily_amount = request.target_amount / Decimal(total_days)

    savings.daily_amount = daily_amount.quantize(Decimal("0.01"))
    savings.duration_months = duration_months
    savings.start_date = request.start_date
    savings.end_date = request.end_date
    savings.target_amount = request.target_amount
    savings.commission_days = request.commission_days
    savings.savings_type = SavingsType.TARGET
    savings.business_id = request.business_id
    savings.unit_id = request.unit_id
    savings.updated_by = current_user["user_id"]
    savings.marking_status = MarkingStatus.NOT_STARTED
    db.flush()

    db.query(SavingsMarking).filter(SavingsMarking.savings_account_id == savings.id).delete()
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

    logger.info(f"Reinitiated target savings {savings.tracking_number} for customer {current_user['user_id']}")
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
        if request.commission_days < 0:
            return error_response(status_code=400, message="Commission days cannot be negative")
        savings.commission_days = request.commission_days

    savings.updated_by = current_user["user_id"]
    db.commit()
    logger.info(f"Updated savings {savings.tracking_number} for customer {current_user['user_id']}")
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
        if savings_type not in [SavingsType.DAILY, SavingsType.TARGET]:
            return error_response(status_code=400, message="Invalid savings type. Use DAILY or TARGET")
        query = query.filter(SavingsAccount.savings_type == savings_type)
    
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
        return error_response(status_code=404, message=f"Savings {tracking_number} not found")

    if savings.marking_status == MarkingStatus.COMPLETED:
        return error_response(status_code=400, message=f"Cannot mark savings in {savings.marking_status} status")

    if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message=f"Not your savings {tracking_number}")
    elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
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
            return error_response(status_code=400, message=f"Customer {savings.customer_id} is not associated with unit {request.unit_id} in business {savings.business_id}")

    marking = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings.id,
        SavingsMarking.marked_date == request.marked_date,
        SavingsMarking.status == SavingsStatus.PENDING
    ).first()
    if not marking or marking.marked_by_id:
        return error_response(status_code=400, message=f"Invalid or already marked date {request.marked_date}")

    customer = db.query(User).filter(User.id == savings.customer_id).first()
    if not customer.email:
        return error_response(status_code=400, message="Customer email required")

    try:
        payment_method = PaymentMethod(request.payment_method)
        if payment_method not in [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]:
            return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")
    except ValueError:
        return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")

    marking.payment_method = payment_method
    marking.unit_id = request.unit_id or savings.unit_id
    marking.marked_by_id = current_user["user_id"]  # Set marked_by_id
    marking.updated_by = current_user["user_id"]
    total_amount = marking.amount

    if savings.marking_status == MarkingStatus.NOT_STARTED:
        savings.marking_status = MarkingStatus.IN_PROGRESS
        db.commit()

    # Generate shorter payment reference
    short_uuid = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
    reference = f"sv_{tracking_number}_{short_uuid}"  # e.g., sv_0620476978_09fa0f81
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
        return virtual_account
    return error_response(status_code=400, message=f"Invalid payment method: {payment_method}")

async def mark_savings_bulk(request: BulkMarkSavingsRequest, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()

    if not request.markings:
        return error_response(status_code=400, message="No savings accounts provided")

    all_markings = []
    total_amount = Decimal("0")
    marked_dates_by_tracking = {}
    savings_accounts = {}

    try:
        payment_method = PaymentMethod(request.payment_method)
        if payment_method not in [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]:
            return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")
    except ValueError:
        return error_response(status_code=400, message=f"Invalid payment method: {request.payment_method}")

    for mark_request in request.markings:
        savings = db.query(SavingsAccount).filter(SavingsAccount.tracking_number == mark_request.tracking_number).first()
        if not savings:
            return error_response(status_code=404, message=f"Savings {mark_request.tracking_number} not found")

        if savings.marking_status == MarkingStatus.COMPLETED:
            return error_response(status_code=400, message=f"Cannot mark savings in {savings.marking_status} status")

        if current_user["role"] == "customer" and savings.customer_id != current_user["user_id"]:
            return error_response(status_code=403, message=f"Not your savings {mark_request.tracking_number}")
        elif current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin", "customer"]:
            return error_response(status_code=401, message="Unauthorized role")

        if mark_request.unit_id:
            unit_exists = db.query(exists().where(
                user_units.c.user_id == savings.customer_id
            ).where(
                user_units.c.unit_id == mark_request.unit_id
            ).where(
                Unit.id == mark_request.unit_id
            ).where(
                Unit.business_id == savings.business_id
            )).scalar()
            if not unit_exists:
                return error_response(status_code=400, message=f"Customer {savings.customer_id} is not associated with unit {mark_request.unit_id} in business {savings.business_id}")

        marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.marked_date == mark_request.marked_date,
            SavingsMarking.status == SavingsStatus.PENDING
        ).first()
        if not marking or marking.marked_by_id:
            return error_response(status_code=400, message=f"Invalid or already marked date {mark_request.marked_date} for {mark_request.tracking_number}")

        marking.payment_method = payment_method
        marking.unit_id = mark_request.unit_id or savings.unit_id
        marking.marked_by_id = current_user["user_id"]  # Set marked_by_id
        marking.updated_by = current_user["user_id"]
        total_amount += marking.amount
        all_markings.append(marking)
        savings_accounts[savings.id] = savings

        if mark_request.tracking_number not in marked_dates_by_tracking:
            marked_dates_by_tracking[mark_request.tracking_number] = []
        marked_dates_by_tracking[mark_request.tracking_number].append(marking.marked_date.isoformat())

    customer = db.query(User).filter(User.id == savings_accounts[list(savings_accounts.keys())[0]].customer_id).first()
    if not customer.email:
        return error_response(status_code=400, message="Customer email required")

    # Generate shorter payment reference using the first tracking number
    first_tracking_number = list(marked_dates_by_tracking.keys())[0]
    short_uuid = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
    reference = f"sv_{first_tracking_number}_{short_uuid}"  # e.g., sv_0620476978_09fa0f81
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
        return virtual_account
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

    db.commit()
    logger.info(f"Abruptly ended markings for savings {tracking_number} for customer {savings.customer_id}")
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

    response_data = SavingsMetricsResponse(
        tracking_number=tracking_number,
        total_amount=total_amount,
        amount_marked=amount_marked,
        days_remaining=days_remaining
    ).model_dump()

    logger.info(f"Retrieved metrics for savings {tracking_number}: total={total_amount}, marked={amount_marked}, days_remaining={days_remaining}")
    return success_response(status_code=200, message="Savings metrics retrieved successfully", data=response_data)

async def verify_savings_payment(reference: str, db: Session):
    markings = db.query(SavingsMarking).filter(SavingsMarking.payment_reference == reference).all()
    if not markings:
        return error_response(status_code=404, message="Payment reference not found")

    payment_method = markings[0].payment_method
    total_amount = sum(m.amount for m in markings)
    tracking_numbers = list({m.savings_account.tracking_number for m in markings})
    marked_dates = [m.marked_date.isoformat() for m in markings]

    logger.info(f"Verifying payment for reference {reference} with method {payment_method}")

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
                marking.marked_by_id = marking.updated_by  # Use updated_by to set marked_by_id
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
                    completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}!"
            db.commit()
            response_data["status"] = SavingsStatus.PAID
            logger.info(f"Card payment verified and marked as PAID for reference {reference}")
        else:
            logger.error(f"Card payment verification failed: {response.get('message', 'No message')}")
            return error_response(status_code=400, message="Payment verification failed")
    elif payment_method == PaymentMethod.BANK_TRANSFER:
        virtual_account = markings[0].virtual_account_details
        if not virtual_account:
            logger.error(f"No virtual account details stored for reference {reference}")
            return error_response(status_code=400, message="Virtual account details not found")

        response_data["virtual_account"] = virtual_account
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
                marking.marked_by_id = marking.updated_by  # Use updated_by to set marked_by_id
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
                    completion_message = f"Congratulations! You have successfully completed your savings plan {savings.tracking_number}!"
            db.commit()
            response_data["status"] = SavingsStatus.PAID
            logger.info(f"Bank transfer payment verified and marked as PAID for reference {reference}")
        else:
            logger.info(f"Bank transfer not yet verified for reference {reference}, returning virtual account details")
            return success_response(
                status_code=200,
                message="Bank transfer not yet verified, please confirm after payment",
                data=response_data
            )
    else:
        return error_response(status_code=400, message=f"Unsupported payment method: {payment_method}")

    if completion_message:
        response_data["completion_message"] = completion_message
    return success_response(
        status_code=200,
        message="Payment details retrieved",
        data=response_data
    )