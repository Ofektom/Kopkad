import httpx
from fastapi import HTTPException
from utils.response import error_response
from config.settings import settings
from decimal import Decimal
import logging
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from models.payments import AccountDetails, PaymentAccount, PaymentStatus
from models.savings import SavingsAccount, SavingsMarking, MarkingStatus, SavingsStatus
from models.user import User, Permission
from schemas.payments import (
    AccountDetailsCreate,
    AccountDetailsResponse,
    PaymentAccountCreate,
    PaymentAccountResponse,
    PaymentInitiateResponse,
    PaymentAccountUpdate,
)
from utils.response import success_response, error_response
from datetime import datetime, timezone
import logging
from paystackapi.transaction import Transaction
import os
import requests
from decimal import Decimal
from typing import Optional

logging.basicConfig(
    filename="payments.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def has_permission(user: User, permission: str, db: Session) -> bool:
    return permission in user.permissions

async def create_account_details(request: AccountDetailsCreate, current_user: dict, db: Session):
    """Add bank account details for a payment account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == request.payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    if current_user["role"] not in ["customer", "agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    try:
        account_details = AccountDetails(
            payment_account_id=request.payment_account_id,
            account_name=request.account_name,
            account_number=request.account_number,
            bank_name=request.bank_name,
            bank_code=request.bank_code,
            account_type=request.account_type,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(account_details)
        db.commit()
        db.refresh(account_details)
        logger.info(f"Created account details for payment account {request.payment_account_id} by user {current_user['user_id']}")
        return success_response(
            status_code=201,
            message="Account details added successfully",
            data={"account_details_id": account_details.id}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create account details: {str(e)}")

async def create_payment_account(request: PaymentAccountCreate, current_user: dict, db: Session):
    """Create a payment account for a completed savings account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if not has_permission(current_user_obj, Permission.MARK_SAVINGS, db):
        return error_response(status_code=403, message="No permission to create payment account")

    savings_account = db.query(SavingsAccount).filter(SavingsAccount.id == request.savings_account_id).first()
    if not savings_account:
        return error_response(status_code=404, message="Savings account not found")

    if savings_account.marking_status != MarkingStatus.COMPLETED:
        return error_response(
            status_code=400,
            message=f"Savings account must be in COMPLETED status, current status: {savings_account.marking_status}"
        )

    if current_user["role"] == "customer" and savings_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")

    paid_markings = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings_account.id,
        SavingsMarking.status == SavingsStatus.PAID
    ).all()
    if not paid_markings:
        return error_response(status_code=400, message="No paid markings found for this savings account")

    total_amount = sum(marking.amount for marking in paid_markings)
    if total_amount <= 0:
        return error_response(status_code=400, message="Total paid amount must be positive")

    try:
        payment_account = PaymentAccount(
            customer_id=savings_account.customer_id,
            savings_account_id=savings_account.id,
            amount=total_amount,
            status=PaymentStatus.PENDING,
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(payment_account)
        db.flush()

        account_details_list = []
        for detail in request.account_details:
            account_details = AccountDetails(
                payment_account_id=payment_account.id,
                account_name=detail.account_name,
                account_number=detail.account_number,
                bank_name=detail.bank_name,
                bank_code=detail.bank_code,
                account_type=detail.account_type,
                created_by=current_user["user_id"],
                created_at=datetime.now(timezone.utc),
            )
            db.add(account_details)
            account_details_list.append(account_details)

        db.commit()
        db.refresh(payment_account)
        for detail in account_details_list:
            db.refresh(detail)

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
            savings_account_id=payment_account.savings_account_id,
            amount=payment_account.amount,
            status=payment_account.status,
            payment_reference=payment_account.payment_reference,
            account_details=account_details_response,
            created_at=payment_account.created_at,
            updated_at=payment_account.updated_at,
        )

        logger.info(f"Created payment account {payment_account.id} for savings account {savings_account.id} with amount {total_amount}")
        return success_response(
            status_code=201,
            message="Payment account created successfully",
            data=response_data.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create payment account: {str(e)}")

async def update_payment_account(payment_account_id: int, request: PaymentAccountUpdate, current_user: dict, db: Session):
    """Update a payment account and its associated account details."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if not has_permission(current_user_obj, Permission.MARK_SAVINGS, db):
        return error_response(status_code=403, message="No permission to update payment account")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    if payment_account.status != PaymentStatus.PENDING:
        return error_response(status_code=400, message=f"Cannot update payment account in {payment_account.status} status")

    try:
        if request.savings_account_id:
            savings_account = db.query(SavingsAccount).filter(SavingsAccount.id == request.savings_account_id).first()
            if not savings_account:
                return error_response(status_code=404, message="Savings account not found")
            if savings_account.marking_status != MarkingStatus.COMPLETED:
                return error_response(
                    status_code=400,
                    message=f"Savings account must be in COMPLETED status, current status: {savings_account.marking_status}"
                )
            if current_user["role"] == "customer" and savings_account.customer_id != current_user["user_id"]:
                return error_response(status_code=403, message="Not your savings account")
            
            paid_markings = db.query(SavingsMarking).filter(
                SavingsMarking.savings_account_id == savings_account.id,
                SavingsMarking.status == SavingsStatus.PAID
            ).all()
            if not paid_markings:
                return error_response(status_code=400, message="No paid markings found for this savings account")
            
            total_amount = sum(marking.amount for marking in paid_markings)
            if total_amount <= 0:
                return error_response(status_code=400, message="Total paid amount must be positive")
            
            payment_account.savings_account_id = savings_account.id
            payment_account.customer_id = savings_account.customer_id
            payment_account.amount = total_amount

        if request.account_details:
            # Optionally, delete existing account details if replacing
            db.query(AccountDetails).filter(AccountDetails.payment_account_id == payment_account_id).delete()
            account_details_list = []
            for detail in request.account_details:
                account_details = AccountDetails(
                    payment_account_id=payment_account_id,
                    account_name=detail.account_name,
                    account_number=detail.account_number,
                    bank_name=detail.bank_name,
                    bank_code=detail.bank_code,
                    account_type=detail.account_type,
                    created_by=current_user["user_id"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(account_details)
                account_details_list.append(account_details)

        payment_account.updated_by = current_user["user_id"]
        payment_account.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(payment_account)

        account_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == payment_account.id).all()
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
            ) for detail in account_details
        ]

        response_data = PaymentAccountResponse(
            id=payment_account.id,
            customer_id=payment_account.customer_id,
            savings_account_id=payment_account.savings_account_id,
            amount=payment_account.amount,
            status=payment_account.status,
            payment_reference=payment_account.payment_reference,
            account_details=account_details_response,
            created_at=payment_account.created_at,
            updated_at=payment_account.updated_at,
        )

        logger.info(f"Updated payment account {payment_account_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Payment account updated successfully",
            data=response_data.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to update payment account: {str(e)}")

async def delete_account_details(account_details_id: int, current_user: dict, db: Session):
    """Delete specific account details for a payment account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    account_details = db.query(AccountDetails).filter(AccountDetails.id == account_details_id).first()
    if not account_details:
        return error_response(status_code=404, message="Account details not found")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == account_details.payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    if current_user["role"] not in ["customer", "agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    if payment_account.status != PaymentStatus.PENDING:
        return error_response(status_code=400, message=f"Cannot delete account details for payment account in {payment_account.status} status")

    try:
        # Ensure at least one account detail remains
        remaining_details = db.query(AccountDetails).filter(
            AccountDetails.payment_account_id == account_details.payment_account_id,
            AccountDetails.id != account_details_id
        ).count()
        if remaining_details == 0:
            return error_response(status_code=400, message="Cannot delete the last account details for a payment account")

        db.delete(account_details)
        db.commit()
        logger.info(f"Deleted account details {account_details_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Account details deleted successfully",
            data={"account_details_id": account_details_id}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to delete account details: {str(e)}")

async def initiate_payment(payment_account_id: int, current_user: dict, db: Session, account_details_id: Optional[int] = None):
    """Initiate payment to a customer's bank account for a completed savings account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["admin", "super_admin"]:
        return error_response(status_code=403, message="Only ADMIN or SUPER_ADMIN can initiate payments")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if payment_account.status != PaymentStatus.PENDING:
        return error_response(status_code=400, message=f"Payment account is in {payment_account.status} status")

    savings_account = db.query(SavingsAccount).filter(SavingsAccount.id == payment_account.savings_account_id).first()
    if not savings_account:
        return error_response(status_code=404, message="Savings account not found")

    if account_details_id:
        account_details = db.query(AccountDetails).filter(
            AccountDetails.id == account_details_id,
            AccountDetails.payment_account_id == payment_account_id
        ).first()
        if not account_details:
            return error_response(status_code=400, message="Specified account details not found or not associated with this payment account")
    else:
        account_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == payment_account_id).first()
        if not account_details:
            return error_response(status_code=400, message="No bank account details provided")

    customer = db.query(User).filter(User.id == payment_account.customer_id).first()
    if not customer:
        return error_response(status_code=404, message="Customer not found")

    try:
        reference = f"payment_{payment_account_id}_{datetime.now(timezone.utc).timestamp()}"
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json",
        }
        payload = {
            "source": "balance",
            "reason": f"Payout for savings account {savings_account.tracking_number}",
            "amount": int(payment_account.amount * 100),
            "recipient": {
                "type": "nuban",
                "name": account_details.account_name,
                "account_number": account_details.account_number,
                "bank_code": account_details.bank_code or "044",  # Default to Access Bank if not provided
            },
            "reference": reference,
        }
        response = requests.post(
            "https://api.paystack.co/transfer",
            headers=headers,
            json=payload,
        )
        response_data = response.json()
        logger.info(f"Paystack transfer response: {response_data}")

        if response.status_code == 200 and response_data.get("status"):
            payment_account.payment_reference = reference
            payment_account.status = PaymentStatus.COMPLETED
            payment_account.updated_by = current_user["user_id"]
            payment_account.updated_at = datetime.now(timezone.utc)
            db.commit()

            bank_details = {
                "account_name": account_details.account_name,
                "account_number": account_details.account_number,
                "bank_name": account_details.bank_name,
                "bank_code": account_details.bank_code,
            }

            response_data = PaymentInitiateResponse(
                payment_account_id=payment_account.id,
                amount=payment_account.amount,
                payment_reference=reference,
                status=payment_account.status,
                bank_details=bank_details,
            )

            logger.info(f"Initiated payment {reference} for payment account {payment_account_id} with amount {payment_account.amount}")
            return success_response(
                status_code=200,
                message="Payment initiated successfully",
                data=response_data.model_dump()
            )
        else:
            payment_account.status = PaymentStatus.FAILED
            db.commit()
            logger.error(f"Failed to initiate payment: {response_data}")
            return error_response(
                status_code=response.status_code,
                message=f"Failed to initiate payment: {response_data.get('message', 'Unknown error')}"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"Error initiating payment: {str(e)}")
        return error_response(status_code=500, message=f"Error initiating payment: {str(e)}")

async def get_payment_accounts(
    customer_id: Optional[int],
    savings_account_id: Optional[int],
    status: Optional[str],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session
):
    """Retrieve payment accounts with optional filtering."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    query = db.query(PaymentAccount)

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payment accounts")
        query = query.filter(PaymentAccount.customer_id == current_user["user_id"])
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        query = query.join(SavingsAccount, SavingsAccount.id == PaymentAccount.savings_account_id).filter(SavingsAccount.business_id.in_(business_ids))
    elif current_user["role"] != "admin" and current_user["role"] != "super_admin":
        return error_response(status_code=403, message="Unauthorized role")

    if customer_id:
        customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        query = query.filter(PaymentAccount.customer_id == customer_id)

    if savings_account_id:
        savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_account_id).first()
        if not savings:
            return error_response(status_code=404, message="Savings account not found")
        query = query.filter(PaymentAccount.savings_account_id == savings_account_id)

    if status:
        try:
            payment_status = PaymentStatus(status.lower())
            query = query.filter(PaymentAccount.status == payment_status)
        except ValueError:
            return error_response(status_code=400, message=f"Invalid status: {status}")

    total_count = query.count()
    payment_accounts = query.order_by(PaymentAccount.created_at.desc()).offset(offset).limit(limit).all()

    response_data = []
    for account in payment_accounts:
        account_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == account.id).all()
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
            ) for detail in account_details
        ]
        response_data.append(
            PaymentAccountResponse(
                id=account.id,
                customer_id=account.customer_id,
                savings_account_id=account.savings_account_id,
                amount=account.amount,
                status=account.status,
                payment_reference=account.payment_reference,
                account_details=account_details_response,
                created_at=account.created_at,
                updated_at=account.updated_at,
            ).model_dump()
        )

    logger.info(f"Retrieved {len(payment_accounts)} payment accounts for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Payment accounts retrieved successfully",
        data={
            "payment_accounts": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )