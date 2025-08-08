
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
    PaymentAccountResponse,
    PaymentInitiateResponse,
    PaymentAccountUpdate,
)
from service.payments import (
    create_account_details,
    create_payment_account,
    initiate_payment,
    get_payment_accounts,
    update_payment_account,
    delete_account_details,
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
    
    # Read request body and verify signature
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

    # Check if payment is already processed
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

    # Verify payment amount
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


@payment_router.post("/account-details", response_model=dict)
async def add_account_details(
    request: AccountDetailsCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add bank account details for a customer."""
    return await create_account_details(request, current_user, db)

@payment_router.post("/account", response_model=PaymentAccountResponse)
async def create_payment_account_endpoint(
    request: PaymentAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a payment account for a customer's completed savings."""
    return await create_payment_account(request, current_user, db)

@payment_router.put("/account/{payment_account_id}", response_model=PaymentAccountResponse)
async def update_payment_account_endpoint(
    payment_account_id: int,
    request: PaymentAccountUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a payment account and its associated account details."""
    return await update_payment_account(payment_account_id, request, current_user, db)

@payment_router.delete("/account-details/{account_details_id}", response_model=dict)
async def delete_account_details_endpoint(
    account_details_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete specific account details for a payment account."""
    return await delete_account_details(account_details_id, current_user, db)

@payment_router.post("/initiate/{payment_account_id}", response_model=PaymentInitiateResponse)
async def initiate_payment_endpoint(
    payment_account_id: int,
    account_details_id: Optional[int] = Query(None, description="ID of the specific account details to use for payment"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initiate payment for a completed savings account."""
    return await initiate_payment(payment_account_id, current_user, db, account_details_id)

@payment_router.get("/accounts", response_model=dict)
async def list_payment_accounts(
    customer_id: Optional[int] = None,
    savings_account_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve payment accounts with optional filtering."""
    return await get_payment_accounts(customer_id, savings_account_id, status, limit, offset, current_user, db)