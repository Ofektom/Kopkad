from fastapi import HTTPException
from utils.response import error_response, success_response
from config.settings import settings
from decimal import Decimal
import logging
from datetime import datetime, timezone
from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from models.payments import AccountDetails, PaymentAccount, Commission, PaymentRequest, PaymentRequestStatus
from models.savings import SavingsAccount, SavingsMarking, MarkingStatus, SavingsStatus
from models.user import User, Permission
from schemas.payments import (
    AccountDetailsCreate,
    AccountDetailsResponse,
    PaymentAccountCreate,
    PaymentAccountResponse,
    PaymentRequestCreate,
    PaymentRequestResponse,
    PaymentAccountUpdate,
    CommissionResponse,
    CustomerPaymentResponse,
)
from typing import Optional

logging.basicConfig(
    filename="payments.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def create_account_details(payment_account_id: int, request: AccountDetailsCreate, current_user: dict, db: Session):
    """Add bank account details for a payment account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    if current_user["role"] not in ["customer", "agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    try:
        account_details = AccountDetails(
            payment_account_id=payment_account_id,
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
        logger.info(f"Created account details for payment account {payment_account_id} by user {current_user['user_id']}")
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
    """Create a payment account for a customer to store payment details."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["customer", "admin", "super_admin"]:
        return error_response(status_code=403, message="Only customers, admins, or super-admins can create payment accounts")

    if current_user["role"] == "customer" and current_user["user_id"] != current_user_obj.id:
        return error_response(status_code=403, message="Customers can only create their own payment accounts")

    existing_payment_account = db.query(PaymentAccount).filter(PaymentAccount.customer_id == current_user["user_id"]).first()
    if existing_payment_account:
        return error_response(status_code=400, message="Payment account already exists for this customer")

    try:
        payment_account = PaymentAccount(
            customer_id=current_user["user_id"],
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
        db.rollback()
        logger.error(f"Failed to create payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create payment account: {str(e)}")

async def update_payment_account(payment_account_id: int, request: PaymentAccountUpdate, current_user: dict, db: Session):
    """Update a payment account by adding or updating account details."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if current_user["role"] == "customer" and payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    if current_user["role"] not in ["customer", "admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    try:
        if request.account_details:
            existing_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == payment_account_id).all()
            existing_ids = {detail.id for detail in existing_details}
            new_details = []
            for detail in request.account_details:
                if hasattr(detail, 'id') and detail.id in existing_ids:
                    existing_detail = db.query(AccountDetails).filter(AccountDetails.id == detail.id).first()
                    existing_detail.account_name = detail.account_name
                    existing_detail.account_number = detail.account_number
                    existing_detail.bank_name = detail.bank_name
                    existing_detail.bank_code = detail.bank_code
                    existing_detail.account_type = detail.account_type
                    existing_detail.updated_by = current_user["user_id"]
                    existing_detail.updated_at = datetime.now(timezone.utc)
                else:
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
                    new_details.append(account_details)

        payment_account.updated_by = current_user["user_id"]
        payment_account.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(payment_account)

        account_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == payment_account_id).all()
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

        customer = db.query(User).filter(User.id == payment_account.customer_id).first()
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
            data=response_data.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update payment account: {str(e)}")
        return error_response(status_code=500, message=f"Failed to update payment account: {str(e)}")

async def delete_account_details(account_details_id: int, current_user: dict, db: Session, force_delete: bool = False):
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

    if db.query(PaymentRequest).filter(PaymentRequest.account_details_id == account_details_id).first():
        return error_response(status_code=400, message="Cannot delete account details used in a payment request")

    try:
        remaining_details = db.query(AccountDetails).filter(
            AccountDetails.payment_account_id == account_details.payment_account_id,
            AccountDetails.id != account_details_id
        ).count()

        if remaining_details == 0 and not force_delete:
            return {
                "status": "warning",
                "message": "This is the last account detail. Deleting it will also delete the payment account. Proceed?",
                "data": {"account_details_id": account_details_id}
            }

        db.delete(account_details)
        if remaining_details == 0:
            db.delete(payment_account)  # Cascade deletion handled by SQLAlchemy
            logger.info(f"Deleted payment account {payment_account.id} with last account details {account_details_id} by user {current_user['user_id']}")

        db.commit()
        logger.info(f"Deleted account details {account_details_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Account details deleted successfully" + (", including payment account" if remaining_details == 0 else ""),
            data={"account_details_id": account_details_id}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete account details: {str(e)}")
        return error_response(status_code=500, message=f"Failed to delete account details: {str(e)}")

async def create_payment_request(request: PaymentRequestCreate, current_user: dict, db: Session):
    """Create a payment request for a completed savings account."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] != "customer":
        return error_response(status_code=403, message="Only customers can create payment requests")

    payment_account = db.query(PaymentAccount).filter(PaymentAccount.id == request.payment_account_id).first()
    if not payment_account:
        return error_response(status_code=404, message="Payment account not found")

    if payment_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your payment account")

    account_details = db.query(AccountDetails).filter(
        AccountDetails.id == request.account_details_id,
        AccountDetails.payment_account_id == request.payment_account_id
    ).first()
    if not account_details:
        return error_response(status_code=404, message="Account details not found")

    savings_account = db.query(SavingsAccount).filter(SavingsAccount.id == request.savings_account_id).first()
    if not savings_account or savings_account.marking_status != MarkingStatus.COMPLETED:
        return error_response(status_code=400, message="Savings account must be completed to request payment")

    if savings_account.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your savings account")

    paid_markings = db.query(SavingsMarking).filter(
        SavingsMarking.savings_account_id == savings_account.id,
        SavingsMarking.status == SavingsStatus.PAID
    ).order_by(SavingsMarking.marking_date).all()
    if not paid_markings:
        return error_response(status_code=400, message="No paid markings found for this savings account")

    total_amount = sum(marking.amount for marking in paid_markings)
    if total_amount <= 0:
        return error_response(status_code=400, message="Total paid amount must be positive")

    # Calculate total savings days from earliest to latest paid marking date
    earliest_date = paid_markings[0].marking_date
    latest_date = paid_markings[-1].marking_date
    total_savings_days = (latest_date - earliest_date).days + 1  # Include both start and end dates
    if savings_account.commission_days == 0:
        total_commission = Decimal(0)
    else:
        total_commission = savings_account.commission_amount * Decimal(total_savings_days / savings_account.commission_days)
        total_commission = round(total_commission, 2)
    payout_amount = total_amount - total_commission
    if payout_amount <= 0:
        return error_response(status_code=400, message="Payout amount must be positive")

    try:
        # Create commission record for the agent
        agent = db.query(User).filter(
            User.id == savings_account.created_by,
            User.role.in_(["agent", "sub_agent"])
        ).first()
        if agent and not db.query(Commission).filter(Commission.savings_account_id == savings_account.id).first():
            commission = Commission(
                savings_account_id=savings_account.id,
                agent_id=agent.id,
                amount=total_commission,
                commission_date=datetime.now(timezone.utc),
                created_by=current_user["user_id"],
                created_at=datetime.now(timezone.utc),
            )
            db.add(commission)

        payment_request = PaymentRequest(
            payment_account_id=request.payment_account_id,
            account_details_id=request.account_details_id,
            savings_account_id=request.savings_account_id,
            amount=payout_amount,
            status=PaymentRequestStatus.PENDING,
            request_date=datetime.now(timezone.utc),
            created_by=current_user["user_id"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(payment_request)
        db.commit()
        db.refresh(payment_request)

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

        logger.info(f"Created payment request {payment_request.id} for savings account {request.savings_account_id} by user {current_user['user_id']}")
        return success_response(
            status_code=201,
            message="Payment request created successfully",
            data=response_data.model_dump()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to create payment request: {str(e)}")

async def get_payment_requests(
    business_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: dict = None,
    db: Session = None
):
    """Retrieve payment requests based on user role and filters."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    query = db.query(PaymentRequest).join(PaymentAccount).join(SavingsAccount).join(User, User.id == PaymentAccount.customer_id)

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payment requests")
        query = query.filter(
            PaymentAccount.customer_id == current_user["user_id"],
            PaymentRequest.status.in_([PaymentRequestStatus.PENDING, PaymentRequestStatus.APPROVED])
        )
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        query = query.filter(SavingsAccount.business_id.in_(business_ids))
    elif current_user["role"] not in ["admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    if business_id:
        query = query.filter(SavingsAccount.business_id == business_id)

    if customer_id:
        customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        query = query.filter(PaymentAccount.customer_id == customer_id)

    if status:
        try:
            payment_request_status = PaymentRequestStatus(status.lower())
            query = query.filter(PaymentRequest.status == payment_request_status)
        except ValueError:
            return error_response(status_code=400, message=f"Invalid status: {status}")

    if current_user["role"] == "customer":
        limit = min(limit, 20)
        total_count = query.count()
        payment_requests = query.order_by(PaymentRequest.request_date.desc()).offset(offset).limit(limit).all()
    else:
        total_count = query.count()
        payment_requests = query.order_by(PaymentRequest.request_date.desc()).offset(offset).limit(limit).all()

    response_data = []
    for request in payment_requests:
        payment_account = request.payment_account
        savings_account = request.savings_account
        customer = db.query(User).filter(User.id == payment_account.customer_id).first()
        response_data.append(
            PaymentRequestResponse(
                id=request.id,
                payment_account_id=request.payment_account_id,
                account_details_id=request.account_details_id,
                savings_account_id=request.savings_account_id,
                amount=request.amount,
                status=request.status,
                request_date=request.request_date,
                approval_date=request.approval_date,
                customer_name=customer.full_name if customer else "Unknown",
                tracking_number=savings_account.tracking_number,
            ).model_dump()
        )

    logger.info(f"Retrieved {len(payment_requests)} payment requests for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Payment requests retrieved successfully",
        data={
            "payment_requests": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )

async def approve_payment_request(request_id: int, current_user: dict, db: Session):
    """Approve a payment request (manual transfer assumed)."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Only agents, sub-agents, admins, or super-admins can approve payment requests")

    payment_request = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not payment_request:
        return error_response(status_code=404, message="Payment request not found")

    if payment_request.status != PaymentRequestStatus.PENDING:
        return error_response(status_code=400, message=f"Payment request is in {payment_request.status} status")

    savings_account = payment_request.savings_account
    if current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if savings_account.business_id not in business_ids:
            return error_response(status_code=403, message="Not authorized for this business")

    try:
        payment_request.status = PaymentRequestStatus.APPROVED
        payment_request.approval_date = datetime.now(timezone.utc)
        payment_request.updated_by = current_user["user_id"]
        payment_request.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Approved payment request {request_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Payment request approved successfully",
            data={"payment_request_id": request_id}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to approve payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to approve payment request: {str(e)}")

async def reject_payment_request(request_id: int, current_user: dict, db: Session):
    """Reject a payment request."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Only agents, sub-agents, admins, or super-admins can reject payment requests")

    payment_request = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not payment_request:
        return error_response(status_code=404, message="Payment request not found")

    if payment_request.status != PaymentRequestStatus.PENDING:
        return error_response(status_code=400, message=f"Payment request is in {payment_request.status} status")

    savings_account = payment_request.savings_account
    if current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if savings_account.business_id not in business_ids:
            return error_response(status_code=403, message="Not authorized for this business")

    try:
        payment_request.status = PaymentRequestStatus.REJECTED
        payment_request.updated_by = current_user["user_id"]
        payment_request.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Rejected payment request {request_id} by user {current_user['user_id']}")
        return success_response(
            status_code=200,
            message="Payment request rejected successfully",
            data={"payment_request_id": request_id}
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reject payment request: {str(e)}")
        return error_response(status_code=500, message=f"Failed to reject payment request: {str(e)}")

async def get_agent_commissions(
    business_id: Optional[int],
    savings_account_id: Optional[int],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session
):
    """Retrieve commissions for agents with customer and savings details."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Only agents, sub-agents, admins, or super-admins can view commissions")

    query = db.query(Commission).join(SavingsAccount, SavingsAccount.id == Commission.savings_account_id).join(
        User, User.id == SavingsAccount.customer_id
    )

    if current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        query = query.filter(SavingsAccount.business_id.in_(business_ids), Commission.agent_id == current_user["user_id"])

    if business_id:
        query = query.filter(SavingsAccount.business_id == business_id)

    if savings_account_id:
        savings = db.query(SavingsAccount).filter(SavingsAccount.id == savings_account_id).first()
        if not savings:
            return error_response(status_code=404, message="Savings account not found")
        query = query.filter(Commission.savings_account_id == savings_account_id)

    total_count = query.count()
    commissions = query.order_by(Commission.commission_date.desc()).offset(offset).limit(limit).all()

    response_data = []
    for commission in commissions:
        savings_account = commission.savings_account
        customer = db.query(User).filter(User.id == savings_account.customer_id).first()
        response_data.append(
            CommissionResponse(
                id=commission.id,
                savings_account_id=commission.savings_account_id,
                agent_id=commission.agent_id,
                amount=commission.amount,
                commission_date=commission.commission_date,
                customer_id=customer.id if customer else None,
                customer_name=customer.full_name if customer else "Unknown",
                savings_type=savings_account.savings_type,
                tracking_number=savings_account.tracking_number,
            ).model_dump()
        )

    logger.info(f"Retrieved {len(commissions)} commissions for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Commissions retrieved successfully",
        data={
            "commissions": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )

async def get_customer_payments(
    customer_id: Optional[int],
    savings_account_id: Optional[int],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session
):
    """Retrieve customer payments for completed savings."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    query = db.query(PaymentRequest).join(PaymentAccount).join(SavingsAccount).join(
        User, User.id == PaymentAccount.customer_id
    ).filter(SavingsAccount.marking_status == MarkingStatus.COMPLETED)

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payments")
        query = query.filter(PaymentAccount.customer_id == current_user["user_id"])
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        query = query.filter(SavingsAccount.business_id.in_(business_ids))
    elif current_user["role"] not in ["admin", "super_admin"]:
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
        query = query.filter(PaymentRequest.savings_account_id == savings_account_id)

    total_count = query.count()
    payment_requests = query.order_by(PaymentRequest.request_date.desc()).offset(offset).limit(limit).all()

    response_data = []
    for request in payment_requests:
        savings_account = request.savings_account
        customer = db.query(User).filter(User.id == request.payment_account.customer_id).first()
        paid_markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings_account.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).order_by(SavingsMarking.marking_date).all()
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
                total_commission = savings_account.commission_amount * Decimal(total_savings_days / savings_account.commission_days)
                total_commission = round(total_commission, 2)
            payout_amount = total_amount - total_commission

        response_data.append(
            CustomerPaymentResponse(
                payment_request_id=request.id,
                savings_account_id=savings_account.id,
                customer_id=customer.id if customer else None,
                customer_name=customer.full_name if customer else "Unknown",
                savings_type=savings_account.savings_type,
                tracking_number=savings_account.tracking_number,
                total_amount=total_amount,
                total_commission=total_commission,
                payout_amount=payout_amount,
                status=request.status,
                created_at=request.created_at,
                updated_at=request.updated_at,
            ).model_dump()
        )

    logger.info(f"Retrieved {len(payment_requests)} customer payments for user {current_user['user_id']}")
    return success_response(
        status_code=200,
        message="Customer payments retrieved successfully",
        data={
            "payments": response_data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )

async def get_payment_accounts(
    customer_id: Optional[int],
    limit: int,
    offset: int,
    current_user: dict,
    db: Session
):
    """Retrieve payment accounts with associated details."""
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    if current_user["role"] not in ["customer", "agent", "sub_agent", "admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    query = db.query(PaymentAccount).join(User, User.id == PaymentAccount.customer_id)

    if current_user["role"] == "customer":
        if customer_id and customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Customers can only view their own payment accounts")
        query = query.filter(PaymentAccount.customer_id == current_user["user_id"])
    elif current_user["role"] in ["agent", "sub_agent"]:
        business_ids = [b.id for b in current_user_obj.businesses]
        if not business_ids:
            return error_response(status_code=400, message="No business associated with user")
        query = query.join(PaymentRequest).join(SavingsAccount).filter(SavingsAccount.business_id.in_(business_ids))
    elif current_user["role"] not in ["admin", "super_admin"]:
        return error_response(status_code=403, message="Unauthorized role")

    if customer_id:
        customer = db.query(User).filter(User.id == customer_id, User.role == "customer").first()
        if not customer:
            return error_response(status_code=400, message=f"User {customer_id} is not a customer")
        query = query.filter(PaymentAccount.customer_id == customer_id)

    total_count = query.count()
    payment_accounts = query.order_by(PaymentAccount.created_at.desc()).offset(offset).limit(limit).all()

    response_data = []
    for account in payment_accounts:
        customer = db.query(User).filter(User.id == account.customer_id).first()
        account_details = db.query(AccountDetails).filter(AccountDetails.payment_account_id == account.id).all()
        logger.info(f"Queried account_details for payment_account_id={account.id}, found {len(account_details)} records")
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
                customer_name=customer.full_name if customer else "Unknown",
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