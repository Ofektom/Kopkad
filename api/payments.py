from config.settings import settings
import hmac
import hashlib
import logging
from decimal import Decimal
from models.savings import SavingsMarking, SavingsStatus
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from schemas.payments import (
    AccountDetailsCreate,
    PaymentAccountCreate,
    PaymentRequestCreate,
    PaymentAccountUpdate,
    PaymentAccountResponse,
)
from service.payments import (
    create_account_details,
    create_payment_account,
    update_payment_account,
    delete_account_details,
    create_payment_request,
    get_payment_requests,
    approve_payment_request,
    reject_payment_request,
    get_agent_commissions,
    get_customer_payments,
    get_payment_accounts,  # Added import
)
from database.postgres import get_db
from utils.auth import get_current_user
from typing import Optional

payment_router = APIRouter(tags=["payments"], prefix="/payments")

# Configure logging for production
logging.basicConfig(
    filename="payments.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@payment_router.post("/webhook/paystack")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    logger.info("Received Paystack webhook request")
    
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.error("No signature provided in webhook request")
        raise HTTPException(status_code=400, detail="No signature provided")

    secret_key = settings.PAYSTACK_SECRET_KEY.encode("utf-8")
    computed_hmac = hmac.new(secret_key, body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(computed_hmac, signature):
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data")
    reference = data.get("reference")

    if not reference:
        logger.error("No reference provided in webhook payload")
        raise HTTPException(status_code=400, detail="No reference provided")

    if db.query(SavingsMarking).filter(
        SavingsMarking.payment_reference == reference,
        SavingsMarking.status == SavingsStatus.PAID.value
    ).first():
        logger.info(f"Webhook event for reference {reference} already processed")
        return {"status": "success"}

    markings = db.query(SavingsMarking).filter(SavingsMarking.payment_reference == reference).all()
    if not markings:
        logger.warning(f"No markings found for reference {reference}")
        return {"status": "success"}

    expected_amount = sum(m.amount for m in markings)
    amount_paid = Decimal(data["amount"]) / 100  # Convert kobo to naira

    if event in ["charge.success", "transfer.success"]:
        if amount_paid < expected_amount:
            logger.error(f"Underpayment for {reference}: expected {expected_amount}, paid {amount_paid}")
            return {"status": "success"}  # Leave pending

        for marking in markings:
            marking.status = SavingsStatus.PAID.value
            marking.marked_by_id = markings[0].savings_account.customer_id
            marking.updated_by = marking.marked_by_id
            marking.updated_at = datetime.fromisoformat(data["paid_at"].replace("Z", "+00:00"))
        db.commit()
        logger.info(f"Confirmed {len(markings)} markings for {reference}. Paid: {amount_paid}, Expected: {expected_amount}")
    else:
        logger.warning(f"Ignored webhook event: {event} for reference {reference}")
    
    return {"status": "success"}

@payment_router.post("/account", response_model=dict)
async def create_payment_account_endpoint(
    request: PaymentAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a payment account for a customer to store payment details."""
    return await create_payment_account(request, current_user, db)

@payment_router.post("/account-details", response_model=dict)
async def add_account_details(
    request: AccountDetailsCreate,
    payment_account_id: int = Query(..., description="ID of the payment account"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add bank account details for a payment account."""
    return await create_account_details(payment_account_id, request, current_user, db)

@payment_router.get("/accounts", response_model=dict)
async def get_payment_accounts_endpoint(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve payment accounts with associated details."""
    return await get_payment_accounts(customer_id, limit, offset, current_user, db)

@payment_router.put("/account/{payment_account_id}", response_model=PaymentAccountResponse)
async def update_payment_account_endpoint(
    payment_account_id: int,
    request: PaymentAccountUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a payment account by adding or updating account details."""
    response = await update_payment_account(payment_account_id, request, current_user, db)
    if response["status"] == "success":
        return response["data"]
    raise HTTPException(status_code=response["status_code"], detail=response["message"])

@payment_router.delete("/account-details/{account_details_id}", response_model=dict)
async def delete_account_details_endpoint(
    account_details_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete specific account details for a payment account."""
    return await delete_account_details(account_details_id, current_user, db)

@payment_router.post("/request", response_model=dict)
async def create_payment_request_endpoint(
    request: PaymentRequestCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer requests payment for a completed savings account."""
    response = await create_payment_request(request, current_user, db)
    if response["status"] == "success":
        return {"status": "success", "message": response["message"], "data": response["data"]}
    raise HTTPException(status_code=response["status_code"], detail=response["message"])

@payment_router.get("/requests", response_model=dict)
async def get_payment_requests_endpoint(
    business_id: Optional[int] = Query(None, description="Filter by business ID"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[str] = Query(None, description="Filter by status (pending, completed, rejected)"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve payment requests for agents or admins."""
    return await get_payment_requests(business_id, customer_id, status, limit, offset, current_user, db)

@payment_router.post("/request/{request_id}/approve", response_model=dict)
async def approve_payment_request_endpoint(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a payment request (manual transfer assumed)."""
    return await approve_payment_request(request_id, current_user, db)

@payment_router.post("/request/{request_id}/reject", response_model=dict)
async def reject_payment_request_endpoint(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a payment request."""
    return await reject_payment_request(request_id, current_user, db)

@payment_router.get("/commissions", response_model=dict)
async def get_commissions_endpoint(
    business_id: Optional[int] = Query(None, description="Filter by business ID"),
    savings_account_id: Optional[int] = Query(None, description="Filter by savings account ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve commissions for agents with customer and savings details."""
    return await get_agent_commissions(business_id, savings_account_id, limit, offset, current_user, db)

@payment_router.get("/customer-payments", response_model=dict)
async def get_customer_payments_endpoint(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    savings_account_id: Optional[int] = Query(None, description="Filter by savings account ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve customer payments for completed savings, including total amount, commission, and payout."""
    return await get_customer_payments(customer_id, savings_account_id, limit, offset, current_user, db)