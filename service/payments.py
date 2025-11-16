from fastapi import HTTPException, status
from utils.response import error_response, success_response
from config.settings import settings
from decimal import Decimal
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from models.payments import (
    AccountDetails,
    PaymentAccount,
    Commission,
    PaymentRequest,
    PaymentRequestStatus,
)
from models.savings import SavingsAccount, SavingsMarking, MarkingStatus, SavingsStatus
from models.user import User
from models.business import Business
from service.savings import calculate_total_commission
from schemas.payments import (
    AccountDetailsCreate,
    AccountDetailsUpdate,
    AccountDetailsResponse,
    PaymentAccountCreate,
    PaymentAccountResponse,
    PaymentRequestCreate,
    PaymentRequestResponse,
    PaymentRequestReject,
    PaymentAccountUpdate,
    CommissionResponse,
    CustomerPaymentResponse,
)
from typing import Optional, Iterable, List

from store.repositories import (
    AccountDetailsRepository,
    BusinessRepository,
    CommissionRepository,
    PaymentAccountRepository,
    PaymentsRepository,
    UserRepository,
    UserNotificationRepository,
)
from models.financial_advisor import NotificationType, NotificationPriority
from service.notifications import notify_user, notify_business_admin

logging.basicConfig(
    filename="payments.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)

async def create_account_details(
    payment_account_id: int,
    request: AccountDetailsCreate,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
):
    """Add bank account details for a payment account."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    session = payment_account_repo.db

    if not user_repo.get_by_id(current_user["user_id"]):
        return error_response(status_code=404, message="User not found")

    payment_account = payment_account_repo.get_by_id(payment_account_id)
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    # Only customers and agents can perform this action
    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Unauthorized role. Only customers and agents can perform this action")

    try:
        account_details = account_details_repo.create(
            {
                "payment_account_id": payment_account_id,
                "account_name": request.account_name,
                "account_number": request.account_number,
                "bank_name": request.bank_name,
                "bank_code": request.bank_code,
                "account_type": request.account_type,
                "created_by": current_user["user_id"],
                "created_at": datetime.now(timezone.utc),
            }
        )
        session.commit()
        session.refresh(account_details)
        logger.info(f"Created account details {account_details.id} for payment account {payment_account_id} by user {current_user['user_id']}")
        return success_response(
            status_code=201,
            message="Account details added successfully",
            data={"account_details_id": account_details.id}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create account details: {str(e)}")

async def update_account_details(
    account_details_id: int,
    request: AccountDetailsUpdate,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
):
    """Update specific account details for a payment account."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    session = payment_account_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    account_details = account_details_repo.get_by_id(account_details_id)
    if not account_details:
        return error_response(status_code=404, message="Account details not found")

    payment_account = payment_account_repo.get_by_id(account_details.payment_account_id)
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    # Only customers and agents can perform this action
    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Unauthorized role. Only customers and agents can perform this action")

    try:
        # Update only provided fields
        if request.account_name is not None:
            account_details.account_name = request.account_name
        if request.account_number is not None:
            account_details.account_number = request.account_number
        if request.bank_name is not None:
            account_details.bank_name = request.bank_name
        if request.bank_code is not None:
            account_details.bank_code = request.bank_code
        if request.account_type is not None:
            account_details.account_type = request.account_type

        account_details.updated_by = current_user["user_id"]
        account_details.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(account_details)

        response_data = AccountDetailsResponse(
            id=account_details.id,
            payment_account_id=account_details.payment_account_id,
            account_name=account_details.account_name,
            account_number=account_details.account_number,
            bank_name=account_details.bank_name,
            bank_code=account_details.bank_code,
            account_type=account_details.account_type,
            created_at=account_details.created_at,
            updated_at=account_details.updated_at,
        )

        logger.info(f"Updated account details {account_details_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Account details updated successfully",
            data=response_data.model_dump()
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to update account details: {str(e)}")

async def delete_payment_account(
    payment_account_id: int,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
    payments_repo: PaymentsRepository | None = None,
):
    """Delete a payment account and its associated account details."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    session = payment_account_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_account = payment_account_repo.get_by_id(payment_account_id)
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    # Only customers and agents can delete payment accounts
    # Customers: their own payment accounts only
    # Agents: their own payment accounts only (for commission payments)
    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Unauthorized role. Only customers and agents can delete payment accounts")

    if payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="You can only delete your own payment account")

    # Check for active payment requests
    if payments_repo.db.query(PaymentRequest).filter(PaymentRequest.payment_account_id == payment_account_id).first():
        return error_response(status_code=400, message="Cannot delete payment account with active payment requests")

    try:
        # Delete all associated account details
        account_details = account_details_repo.get_for_account(payment_account_id)
        for detail in account_details:
            session.delete(detail)

        # Delete the payment account
        session.delete(payment_account)
        session.commit()

        logger.info(f"Deleted payment account {payment_account_id} and its account details by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Payment account deleted successfully",
            data={"payment_account_id": payment_account_id}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to delete payment account: {str(e)}")

async def create_payment_account(
    request: PaymentAccountCreate,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
):
    """Create a payment account for a customer to store payment details."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    session = payment_account_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    # Only customers and agents can create payment accounts
    # Agents create payment accounts for themselves (for commission payments)
    # Customers create payment accounts for themselves (for savings payouts)
    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Only customers and agents can create payment accounts")

    if current_user["role"] == "customer" and current_user["user_id"] != current_user_obj.id:
        return error_response(status_code=403, message="Customers can only create their own payment accounts")

    existing_payment_account = payment_account_repo.find_one_by(customer_id=current_user["user_id"])
    if existing_payment_account:
        return error_response(status_code=400, message="Payment account already exists for this customer")

    try:
        payment_account = payment_account_repo.create(
            {
                "customer_id": current_user["user_id"],
                "created_by": current_user["user_id"],
                "created_at": datetime.now(timezone.utc),
            }
        )

        account_details_list = []
        for detail in request.account_details:
            account_details = account_details_repo.create(
                {
                    "payment_account_id": payment_account.id,
                    "account_name": detail.account_name,
                    "account_number": detail.account_number,
                    "bank_name": detail.bank_name,
                    "bank_code": detail.bank_code,
                    "account_type": detail.account_type,
                    "created_by": current_user["user_id"],
                    "created_at": datetime.now(timezone.utc),
                }
            )
            account_details_list.append(account_details)

        session.commit()
        session.refresh(payment_account)
        for detail in account_details_list:
            session.refresh(detail)

        account_details_response = [
            AccountDetailsResponse(
                id=detail.id,
                payment_account_id=detail.payment_account_id,
                account_name=detail.account_name,
                account_number=detail.account_number,
                bank_name=detail.bank_name,
                bank_code=detail.bank_code,
                account_type=detail.account_type,
                created_at=detail.created_at,
                updated_at=detail.updated_at,
            ) for detail in account_details_list
        ]

        response_data = PaymentAccountResponse(
            id=payment_account.id,
            customer_id=payment_account.customer_id,
            customer_name=current_user_obj.full_name,
            account_details=account_details_response,
            created_at=payment_account.created_at,
            updated_at=payment_account.updated_at,
        )

        logger.info(f"Created payment account {payment_account.id} for customer {current_user['user_id']}")
        return success_response(
            status_code=201,
            message="Payment account created successfully",
            data=response_data.model_dump()
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create payment account: {str(e)}")

async def update_payment_account(
    payment_account_id: int,
    request: PaymentAccountUpdate,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
):
    """Update a payment account by adding or updating account details."""

    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    session = payment_account_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_account = payment_account_repo.get_by_id(payment_account_id)
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Unauthorized role. Only customers and agents can update payment accounts")

    if payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="You can only update your own payment account")

    try:
        if request.account_details:
            existing_details = account_details_repo.get_for_account(payment_account_id)
            existing_ids = {detail.id for detail in existing_details}

            for detail in request.account_details:
                if hasattr(detail, "id") and detail.id in existing_ids:
                    existing_detail = account_details_repo.get_by_id(detail.id)
                    if not existing_detail:
                        continue
                    existing_detail.account_name = detail.account_name
                    existing_detail.account_number = detail.account_number
                    existing_detail.bank_name = detail.bank_name
                    existing_detail.bank_code = detail.bank_code
                    existing_detail.account_type = detail.account_type
                    existing_detail.updated_by = current_user["user_id"]
                    existing_detail.updated_at = datetime.now(timezone.utc)
                else:
                    account_details_repo.create(
                        {
                            "payment_account_id": payment_account_id,
                            "account_name": detail.account_name,
                            "account_number": detail.account_number,
                            "bank_name": detail.bank_name,
                            "bank_code": detail.bank_code,
                            "account_type": detail.account_type,
                            "created_by": current_user["user_id"],
                            "created_at": datetime.now(timezone.utc),
                        }
                    )

        payment_account.updated_by = current_user["user_id"]
        payment_account.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(payment_account)

        account_details = account_details_repo.get_for_account(payment_account_id)
        account_details_response = [
            AccountDetailsResponse(
                id=detail.id,
                payment_account_id=detail.payment_account_id,
                account_name=detail.account_name,
                account_number=detail.account_number,
                bank_name=detail.bank_name,
                bank_code=detail.bank_code,
                account_type=detail.account_type,
                created_at=detail.created_at,
                updated_at=detail.updated_at,
            )
            for detail in account_details
        ]

        customer = user_repo.get_by_id(payment_account.customer_id)
        response_data = PaymentAccountResponse(
            id=payment_account.id,
            customer_id=payment_account.customer_id,
            customer_name=customer.full_name if customer else "Unknown",
            account_details=account_details_response,
            created_at=payment_account.created_at,
            updated_at=payment_account.updated_at,
        )

        logger.info(f"Updated payment account {payment_account_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Payment account updated successfully",
            data=response_data.model_dump(),
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to update payment account: {str(e)}")

async def delete_account_details(
    account_details_id: int,
    current_user: dict,
    db: Session,
    force_delete: bool = False,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
):
    """Delete specific account details for a payment account."""
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    session = payment_account_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    account_details = account_details_repo.get_by_id(account_details_id)
    if not account_details:
        return error_response(status_code=404, message="Account details not found")

    payment_account = payment_account_repo.get_by_id(account_details.payment_account_id)
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    # Only customers and agents can delete account details
    # Customers: their own account details only
    # Agents: their own account details only (for commission payments)
    if current_user["role"] not in ["customer", "agent"]:
        return error_response(status_code=403, message="Unauthorized role. Only customers and agents can delete account details")

    if payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="You can only delete your own account details")

    if payment_account_repo.db.query(PaymentRequest).filter(PaymentRequest.account_details_id == account_details_id).first():
        return error_response(status_code=400, message="Cannot delete account details used in a payment request")

    try:
        remaining_details = account_details_repo.count_other_details(account_details_id)

        if remaining_details == 0 and not force_delete:
            return {
                "status": "warning",
                "message": "This is the last account detail. Deleting it will also delete the payment account. Proceed?",
                "data": {"account_details_id": account_details_id}
            }

        session.delete(account_details)
        session.commit()
        logger.info(f"Deleted account details {account_details_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Account details deleted successfully",
            data={"account_details_id": account_details_id}
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to delete account details: {str(e)}")

async def create_payment_request(
    request: PaymentRequestCreate,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    account_details_repo: AccountDetailsRepository | None = None,
    payments_repo: PaymentsRepository | None = None,
    commission_repo: CommissionRepository | None = None,
    business_repo: BusinessRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Create a payment request for a completed savings account."""

    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    account_details_repo = _resolve_repo(account_details_repo, AccountDetailsRepository, db)
    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    commission_repo = _resolve_repo(commission_repo, CommissionRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    session = payments_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        logger.error(f"User not found: {current_user['user_id']}")
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["customer", "admin"]:
        logger.error(
            "Unauthorized role: %s for user %s",
            current_user["role"],
            current_user["user_id"],
        )
        return error_response(status_code=403, message="Unauthorized role")

    payment_account = payment_account_repo.get_by_customer_id(current_user["user_id"])
    if not payment_account:
        logger.error(f"No payment account found for customer {current_user['user_id']}")
        return error_response(
            status_code=404,
            message="No payment account found. Please add a payment account in Settings.",
        )

    account_details = account_details_repo.get_by_id(request.account_details_id)
    if not account_details or account_details.payment_account_id != payment_account.id:
        logger.error(
            "Account details %s not found or not associated with payment account %s",
            request.account_details_id,
            payment_account.id,
        )
        return error_response(
            status_code=404,
            message="Account details not found or not associated with your payment account",
        )

    savings_account = (
        session.query(SavingsAccount)
        .filter(
            SavingsAccount.id == request.savings_account_id,
            SavingsAccount.customer_id == current_user["user_id"],
            SavingsAccount.marking_status == MarkingStatus.COMPLETED,
        )
        .first()
    )
    if not savings_account:
        logger.error(
            "Savings account %s not found, not owned by user %s, or not completed",
            request.savings_account_id,
            current_user["user_id"],
        )
        return error_response(
            status_code=404,
            message="Savings account not found, not owned by you, or not completed",
        )

    existing_request = payments_repo.get_existing_for_savings(
        request.savings_account_id,
        [PaymentRequestStatus.PENDING, PaymentRequestStatus.APPROVED],
    )
    if existing_request:
        status_text = (
            "pending"
            if existing_request.status == PaymentRequestStatus.PENDING.value
            else "approved"
        )
        logger.warning(
            "Payment request already exists for savings account %s with status %s",
            request.savings_account_id,
            status_text,
        )
        return error_response(
            status_code=400,
            message=f"A {status_text} payment request already exists for this savings account. Please wait for it to be processed or cancel the pending request.",
        )

    total_marked_amount = (
        session.query(func.sum(SavingsMarking.amount))
        .filter(
            SavingsMarking.savings_account_id == request.savings_account_id,
            SavingsMarking.status == SavingsStatus.PAID,
        )
        .scalar()
        or Decimal("0.00")
    )

    total_commission = calculate_total_commission(savings_account)
    payout_amount = total_marked_amount - total_commission

    if payout_amount <= 0:
        logger.error(
            "Payout amount is zero or negative for savings account %s",
            request.savings_account_id,
        )
        return error_response(status_code=400, message="No positive payout amount available")

    try:
        payment_request = payments_repo.create(
            {
                "payment_account_id": payment_account.id,
                "account_details_id": request.account_details_id,
                "savings_account_id": request.savings_account_id,
                "amount": payout_amount,
                "request_date": datetime.now(timezone.utc),
                "created_by": current_user["user_id"],
                "created_at": datetime.now(timezone.utc),
                "reference": f"PR-{current_user['user_id']}-{int(datetime.now(timezone.utc).timestamp())}",
            }
        )
        session.commit()
        session.refresh(payment_request)

        business = business_repo.get_by_id(savings_account.business_id)
        agent_id = business.agent_id if business else None

        if total_commission > 0 and agent_id:
            commission = commission_repo.create(
                {
                    "savings_account_id": request.savings_account_id,
                    "agent_id": agent_id,
                    "amount": total_commission,
                    "created_by": current_user["user_id"],
                    "created_at": datetime.now(timezone.utc),
                    "commission_date": datetime.now(timezone.utc),
                }
            )
            session.commit()
            logger.info(
                "Created commission for payment request %s with agent %s",
                payment_request.id,
                agent_id,
            )
            
            # Notify agent about commission earned
            await notify_user(
                user_id=agent_id,
                notification_type=NotificationType.COMMISSION_EARNED,
                title="Commission Earned",
                message=f"You've earned {total_commission:.2f} commission from savings account {savings_account.tracking_number}",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=notification_repo,
                related_entity_id=commission.id if hasattr(commission, 'id') else None,
                related_entity_type="commission",
            )

        response_data = PaymentRequestResponse(
            id=payment_request.id,
            payment_account_id=payment_request.payment_account_id,
            account_details_id=payment_request.account_details_id,
            savings_account_id=payment_request.savings_account_id,
            amount=payment_request.amount,
            status=payment_request.status,
            request_date=payment_request.request_date,
            approval_date=payment_request.approval_date,
            customer_name=current_user_obj.full_name,
            tracking_number=savings_account.tracking_number,
        )

        logger.info(
            "Created payment request %s for user %s",
            payment_request.id,
            current_user["user_id"],
        )
        
        # Notify customer about payment request creation
        if payment_request.payment_account and payment_request.payment_account.customer_id:
            customer_id = payment_request.payment_account.customer_id
            await notify_user(
                user_id=customer_id,
                notification_type=NotificationType.PAYMENT_REQUEST_PENDING,
                title="Payment Request Submitted",
                message=f"Your payment request of {payout_amount:.2f} for savings account {savings_account.tracking_number} has been submitted and is pending approval.",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=notification_repo,
                related_entity_id=payment_request.id,
                related_entity_type="payment_request",
            )
        
        # Notify business admin about new payment request
        if savings_account.business_id:
            await notify_business_admin(
                business_id=savings_account.business_id,
                notification_type=NotificationType.PAYMENT_REQUEST_PENDING,
                title="New Payment Request",
                message=f"New payment request of {payout_amount:.2f} from {current_user_obj.full_name} for savings account {savings_account.tracking_number}",
                priority=NotificationPriority.HIGH,
                db=session,
                business_repo=business_repo,
                notification_repo=notification_repo,
                related_entity_id=payment_request.id,
                related_entity_type="payment_request",
            )
        
        return success_response(
            status_code=201,
            message="Payment request created successfully",
            data=response_data.model_dump(),
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create payment request: {str(e)}")

async def get_payment_requests(
    business_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: dict = None,
    db: Session = None,
    *,
    payments_repo: PaymentsRepository | None = None,
    user_repo: UserRepository | None = None,
    business_repo: BusinessRepository | None = None,
):
    """Retrieve payment requests based on user role and filters."""

    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    session = payments_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] in ["agent", "sub_agent"]:
        return error_response(
            status_code=403,
            message="Agents and sub-agents cannot view payment requests. Please use the Commissions tab instead.",
        )

    base_conditions: List = []
    customer_filter: Optional[int] = None
    business_filter: Optional[int] = None
    status_enum: Optional[PaymentRequestStatus] = None

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payment requests")
        base_conditions.append(PaymentAccount.customer_id == current_user["user_id"])
        base_conditions.append(
            PaymentRequest.status.in_([
                PaymentRequestStatus.PENDING.value,
                PaymentRequestStatus.APPROVED.value,
            ])
        )
    elif current_user["role"] == "admin":
        admin_business = business_repo.get_by_admin_id(current_user["user_id"])
        if not admin_business:
            return error_response(status_code=403, message="Admin is not assigned to any business")
        business_filter = admin_business.id
    elif current_user["role"] == "super_admin":
        business_filter = business_id
    else:
        return error_response(status_code=403, message="Unauthorized role")

    if customer_id:
        customer = user_repo.find_one_by(id=customer_id, role="customer")
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        customer_filter = customer_id

    if status:
        try:
            status_enum = PaymentRequestStatus(status.lower())
        except ValueError:
            return error_response(status_code=400, message=f"Invalid status: {status}")

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            return error_response(status_code=400, message=f"Invalid start_date format: {start_date}")

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00")) + timedelta(days=1)
        except ValueError:
            return error_response(status_code=400, message=f"Invalid end_date format: {end_date}")

    payment_requests, total_count = payments_repo.get_payment_requests_with_filters(
        base_conditions=base_conditions,
        status=status_enum,
        customer_id=customer_filter,
        business_id=business_filter,
        search=search,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=limit,
        offset=offset,
    )

    response_data = []
    for request_obj in payment_requests:
        payment_account = request_obj.payment_account
        savings_account = request_obj.savings_account
        customer = payment_account.customer if payment_account else None
        response_data.append(
            PaymentRequestResponse(
                id=request_obj.id,
                payment_account_id=request_obj.payment_account_id,
                account_details_id=request_obj.account_details_id,
                savings_account_id=request_obj.savings_account_id,
                amount=request_obj.amount,
                status=request_obj.status,
                request_date=request_obj.request_date,
                approval_date=request_obj.approval_date,
                rejection_reason=request_obj.rejection_reason,
                customer_name=customer.full_name if customer else "Unknown",
                tracking_number=savings_account.tracking_number if savings_account else None,
            ).model_dump()
        )

    logger.info(
        "Retrieved %s payment requests for user %s",
        len(payment_requests),
        current_user["user_id"],
    )
    return success_response(
        status_code=200,
        message="Payment requests retrieved successfully",
        data={
            "payment_requests": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        },
    )

async def approve_payment_request(
    request_id: int,
    current_user: dict,
    db: Session,
    *,
    payments_repo: PaymentsRepository | None = None,
    user_repo: UserRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Approve a payment request with business-scoped validation."""

    from utils.permissions import can_approve_payment

    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    session = payments_repo.db

    payment_request = payments_repo.get_by_id_with_relations(request_id)
    if not payment_request:
        return error_response(status_code=404, message="Payment request not found")

    if payment_request.status != PaymentRequestStatus.PENDING.value:
        return error_response(
            status_code=400,
            message=f"Payment request is in {payment_request.status} status",
        )

    savings_account = payment_request.savings_account
    savings_business_id = savings_account.business_id if savings_account else None

    if not can_approve_payment(current_user, savings_business_id, session):
        return error_response(
            status_code=403,
            message="You do not have permission to approve payments for this business",
        )

    try:
        payment_request.status = PaymentRequestStatus.APPROVED.value
        payment_request.approval_date = datetime.now(timezone.utc)
        payment_request.updated_by = current_user["user_id"]
        payment_request.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Approved payment request %s by user %s",
            request_id,
            current_user["user_id"],
        )
        
        # Notify customer about approval
        if payment_request.payment_account and payment_request.payment_account.customer_id:
            customer_id = payment_request.payment_account.customer_id
            await notify_user(
                user_id=customer_id,
                notification_type=NotificationType.PAYMENT_APPROVED,
                title="Payment Request Approved",
                message=f"Your payment request of {payment_request.amount:.2f} has been approved and will be processed shortly.",
                priority=NotificationPriority.MEDIUM,
                db=session,
                notification_repo=notification_repo,
                related_entity_id=payment_request.id,
                related_entity_type="payment_request",
            )
        
        # Notify agent about commission paid (if commission exists for this payment request)
        if payment_request.savings_account_id:
            savings_account = payment_request.savings_account
            if savings_account:
                # Get commission for this payment request
                commission = session.query(Commission).filter(
                    Commission.savings_account_id == payment_request.savings_account_id
                ).order_by(Commission.created_at.desc()).first()
                
                if commission and commission.agent_id:
                    await notify_user(
                        user_id=commission.agent_id,
                        notification_type=NotificationType.COMMISSION_PAID,
                        title="Commission Paid",
                        message=f"Commission of {commission.amount:.2f} has been paid to your account from savings account {savings_account.tracking_number}",
                        priority=NotificationPriority.HIGH,
                        db=session,
                        notification_repo=notification_repo,
                        related_entity_id=commission.id,
                        related_entity_type="commission",
            )
        
        return success_response(
            status_code=200,
            message="Payment request approved successfully",
            data={"payment_request_id": request_id},
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to approve payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to approve payment request: {str(e)}")

async def reject_payment_request(
    request_id: int,
    reject_data: PaymentRequestReject,
    current_user: dict,
    db: Session,
    *,
    payments_repo: PaymentsRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Reject a payment request with business-scoped validation."""

    from utils.permissions import can_reject_payment

    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    session = payments_repo.db

    payment_request = payments_repo.get_by_id_with_relations(request_id)
    if not payment_request:
        return error_response(status_code=404, message="Payment request not found")

    if payment_request.status != PaymentRequestStatus.PENDING.value:
        return error_response(
            status_code=400,
            message=f"Payment request is in {payment_request.status} status",
        )

    savings_account = payment_request.savings_account
    savings_business_id = savings_account.business_id if savings_account else None

    if not can_reject_payment(current_user, savings_business_id, session):
        return error_response(
            status_code=403,
            message="You do not have permission to reject payments for this business",
        )

    if not reject_data.rejection_reason or len(reject_data.rejection_reason.strip()) == 0:
        return error_response(status_code=400, message="Rejection reason is required")

    try:
        payment_request.status = PaymentRequestStatus.REJECTED.value
        payment_request.rejection_reason = reject_data.rejection_reason
        payment_request.updated_by = current_user["user_id"]
        payment_request.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Rejected payment request %s by user %s with reason: %s",
            request_id,
            current_user["user_id"],
            reject_data.rejection_reason,
        )
        
        # Notify customer about rejection
        if payment_request.payment_account and payment_request.payment_account.customer_id:
            customer_id = payment_request.payment_account.customer_id
            await notify_user(
                user_id=customer_id,
                notification_type=NotificationType.PAYMENT_REJECTED,
                title="Payment Request Rejected",
                message=f"Your payment request of {payment_request.amount:.2f} was rejected. Reason: {reject_data.rejection_reason}",
                priority=NotificationPriority.HIGH,
                db=session,
                notification_repo=notification_repo,
                related_entity_id=payment_request.id,
                related_entity_type="payment_request",
            )
        
        return success_response(
            status_code=200,
            message="Payment request rejected successfully",
            data={
                "payment_request_id": request_id,
                "rejection_reason": reject_data.rejection_reason,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to reject payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to reject payment request: {str(e)}")

async def cancel_payment_request(
    request_id: int,
    current_user: dict,
    db: Session,
    *,
    user_repo: UserRepository | None = None,
    payments_repo: PaymentsRepository | None = None,
    payment_account_repo: PaymentAccountRepository | None = None,
    business_repo: BusinessRepository | None = None,
    notification_repo: UserNotificationRepository | None = None,
):
    """Cancel a pending payment request. Only customers can cancel their own requests."""

    user_repo = _resolve_repo(user_repo, UserRepository, db)
    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    session = payments_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_request = payments_repo.get_by_id(request_id)
    if not payment_request:
        return error_response(status_code=404, message="Payment request not found")

    payment_account = payment_account_repo.get_by_id(payment_request.payment_account_id)
    if not payment_account or payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="You can only cancel your own payment requests")

    if payment_request.status != PaymentRequestStatus.PENDING.value:
        return error_response(
            status_code=400,
            message=f"Cannot cancel a {payment_request.status} payment request. Only pending requests can be cancelled.",
        )

    try:
        payment_request.status = PaymentRequestStatus.CANCELLED.value
        payment_request.updated_by = current_user["user_id"]
        payment_request.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Cancelled payment request %s by customer %s",
            request_id,
            current_user["user_id"],
        )
        
        # Notify business admin about cancellation
        payment_request_with_relations = payments_repo.get_by_id_with_relations(request_id)
        if payment_request_with_relations and payment_request_with_relations.savings_account:
            savings_account = payment_request_with_relations.savings_account
            if savings_account.business_id:
                await notify_business_admin(
                    business_id=savings_account.business_id,
                    notification_type=NotificationType.PAYMENT_CANCELLED,
                    title="Payment Request Cancelled",
                    message=f"Payment request {payment_request.reference} of {payment_request.amount:.2f} was cancelled by {current_user_obj.full_name}",
                    priority=NotificationPriority.MEDIUM,
                    db=session,
                    business_repo=business_repo,
                    notification_repo=notification_repo,
                    related_entity_id=payment_request.id,
                    related_entity_type="payment_request",
                )
        
        return success_response(
            status_code=200,
            message="Payment request cancelled successfully",
            data={"payment_request_id": request_id},
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to cancel payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to cancel payment request: {str(e)}")

async def get_agent_commissions(
    business_id: Optional[int],
    savings_account_id: Optional[int],
    search: Optional[str],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session,
    *,
    commission_repo: CommissionRepository | None = None,
    user_repo: UserRepository | None = None,
):
    """Retrieve commissions for agents with customer and savings details."""

    commission_repo = _resolve_repo(commission_repo, CommissionRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin"]:
        return error_response(
            status_code=403,
            message="Only agents, sub-agents, admins, or super-admins can view commissions",
        )

    business_ids: Optional[List[int]] = None
    if current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")

    commissions, total_count = commission_repo.get_commissions_with_filters(
        business_ids=business_ids,
        business_id=business_id,
        savings_account_id=savings_account_id,
        search=search,
        limit=limit,
        offset=offset,
    )

    response_data = []
    for commission in commissions:
        savings_account = commission.savings_account
        customer = savings_account.customer if savings_account else None
        response_data.append(
            CommissionResponse(
                id=commission.id,
                savings_account_id=commission.savings_account_id,
                agent_id=commission.agent_id,
                amount=commission.amount,
                commission_date=commission.commission_date,
                customer_id=customer.id if customer else None,
                customer_name=customer.full_name if customer else "Unknown",
                savings_type=savings_account.savings_type if savings_account else None,
                tracking_number=savings_account.tracking_number if savings_account else None,
            ).model_dump()
        )

    logger.info(
        "Retrieved %s commissions for user %s",
        len(commissions),
        current_user["user_id"],
    )
    return success_response(
        status_code=200,
        message="Commissions retrieved successfully",
        data={
            "commissions": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        },
    )

async def get_customer_payments(
    customer_id: Optional[int],
    savings_account_id: Optional[int],
    search: Optional[str],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session,
    *,
    payments_repo: PaymentsRepository | None = None,
    user_repo: UserRepository | None = None,
):
    """Retrieve customer payments for completed savings."""

    payments_repo = _resolve_repo(payments_repo, PaymentsRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)
    session = payments_repo.db

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    base_conditions: List = [SavingsAccount.marking_status == MarkingStatus.COMPLETED]
    customer_filter: Optional[int] = None
    business_filter: Optional[int] = None

    role = current_user["role"]
    if role == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payments")
        base_conditions.append(PaymentAccount.customer_id == current_user["user_id"])
    elif role in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        base_conditions.append(SavingsAccount.business_id.in_(business_ids))
    elif role not in ["admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    if customer_id:
        customer = user_repo.find_one_by(id=customer_id, role="customer")
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        customer_filter = customer_id

    if savings_account_id:
        savings = session.query(SavingsAccount).filter(SavingsAccount.id == savings_account_id).first()
        if not savings:
            return error_response(status_code=404, message="Savings account not found")
        base_conditions.append(PaymentRequest.savings_account_id == savings_account_id)

    payment_requests, total_count = payments_repo.get_payment_requests_with_filters(
        base_conditions=base_conditions,
        customer_id=customer_filter,
        business_id=business_filter,
        search=search,
        limit=limit,
        offset=offset,
    )

    response_data = []
    for request_obj in payment_requests:
        savings_account = request_obj.savings_account
        customer = request_obj.payment_account.customer if request_obj.payment_account else None
        paid_markings = (
            session.query(SavingsMarking)
            .filter(
                SavingsMarking.savings_account_id == savings_account.id,
                SavingsMarking.status == SavingsStatus.PAID,
            )
            .order_by(SavingsMarking.marking_date)
            .all()
        )
        total_amount = sum(marking.amount for marking in paid_markings)

        if not paid_markings:
            total_commission = Decimal(0)
            payout_amount = Decimal(0)
        else:
            earliest_date = paid_markings[0].marking_date
            latest_date = paid_markings[-1].marking_date
            total_savings_days = (latest_date - earliest_date).days + 1
            if savings_account.commission_days == 0:
                total_commission = Decimal(0)
            else:
                total_commission = savings_account.commission_amount * Decimal(
                    total_savings_days / savings_account.commission_days
                )
                total_commission = round(total_commission, 2)
            payout_amount = total_amount - total_commission

        response_data.append(
            CustomerPaymentResponse(
                payment_request_id=request_obj.id,
                savings_account_id=savings_account.id,
                customer_id=customer.id if customer else None,
                customer_name=customer.full_name if customer else "Unknown",
                savings_type=savings_account.savings_type,
                tracking_number=savings_account.tracking_number,
                total_amount=total_amount,
                total_commission=total_commission,
                payout_amount=payout_amount,
                status=request_obj.status,
                created_at=request_obj.created_at,
                updated_at=request_obj.updated_at,
            ).model_dump()
        )

    logger.info(
        "Retrieved %s customer payments for user %s",
        len(payment_requests),
        current_user["user_id"],
    )
    return success_response(
        status_code=200,
        message="Customer payments retrieved successfully",
        data={
            "payments": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        },
    )

async def get_payment_accounts(
    customer_id: Optional[int],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session,
    *,
    payment_account_repo: PaymentAccountRepository | None = None,
    user_repo: UserRepository | None = None,
):
    """Retrieve payment accounts with associated details."""

    payment_account_repo = _resolve_repo(payment_account_repo, PaymentAccountRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    current_user_obj = user_repo.get_by_id(current_user["user_id"])
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["customer", "agent"]:
        return error_response(
            status_code=403,
            message="Unauthorized role. Only customers and agents can view payment accounts",
        )

    effective_customer_id = current_user["user_id"]
    if customer_id and customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="You can only view your own payment accounts")

    accounts, total_count = payment_account_repo.get_accounts_with_filters(
        customer_id=effective_customer_id,
        limit=limit,
        offset=offset,
    )

    response_data = []
    for account in accounts:
        customer = account.customer or user_repo.get_by_id(account.customer_id)
        account_details_response = [
            AccountDetailsResponse(
                id=detail.id,
                payment_account_id=detail.payment_account_id,
                account_name=detail.account_name,
                account_number=detail.account_number,
                bank_name=detail.bank_name,
                bank_code=detail.bank_code,
                account_type=detail.account_type,
                created_at=detail.created_at,
                updated_at=detail.updated_at,
            )
            for detail in account.account_details
        ]

        response_data.append(
            PaymentAccountResponse(
                id=account.id,
                customer_id=account.customer_id,
                customer_name=customer.full_name if customer else "Unknown",
                account_details=account_details_response,
                created_at=account.created_at,
                updated_at=account.updated_at,
            ).model_dump()
        )

    logger.info(
        "Retrieved %s payment accounts for user %s",
        len(accounts),
        current_user["user_id"],
    )
    return success_response(
        status_code=200,
        message="Payment accounts retrieved successfully",
        data={
            "payment_accounts": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        },
    )