"""
Payments controller providing dependency-injected endpoints.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from config.settings import settings
from database.postgres_optimized import get_db
from schemas.payments import (
    AccountDetailsCreate,
    AccountDetailsUpdate,
    PaymentAccountCreate,
    PaymentAccountResponse,
    PaymentAccountUpdate,
    PaymentRequestCreate,
    PaymentRequestReject,
)
from service.payments import (
    approve_payment_request,
    cancel_payment_request,
    create_account_details,
    create_payment_account,
    create_payment_request,
    delete_account_details,
    delete_payment_account,
    get_agent_commissions,
    get_customer_payments,
    get_payment_accounts,
    get_payment_requests,
    reject_payment_request,
    update_account_details,
    update_payment_account,
)
from store.repositories import (
    AccountDetailsRepository,
    BusinessRepository,
    CommissionRepository,
    PaymentAccountRepository,
    PaymentsRepository,
    UserRepository,
)
from utils.auth import get_current_user
from utils.dependencies import get_repository


async def paystack_webhook_controller(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Handle Paystack webhook events to mark savings as paid.
    This logic remains controller-specific because it interacts directly with request payloads.
    """
    import hashlib
    import hmac
    from decimal import Decimal
    from datetime import datetime

    from models.savings import SavingsMarking, SavingsStatus

    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="No signature provided")

    secret_key = settings.PAYSTACK_SECRET_KEY.encode("utf-8")
    computed_hmac = hmac.new(secret_key, body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(computed_hmac, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference")

    if not reference:
        raise HTTPException(status_code=400, detail="No reference provided")

    if (
        db.query(SavingsMarking)
        .filter(
            SavingsMarking.payment_reference == reference,
            SavingsMarking.status == SavingsStatus.PAID.value,
        )
        .first()
    ):
        return {"status": "success"}

    markings = (
        db.query(SavingsMarking)
        .filter(SavingsMarking.payment_reference == reference)
        .all()
    )
    if not markings:
        return {"status": "success"}

    expected_amount = sum(m.amount for m in markings)
    amount_paid = Decimal(data.get("amount", 0)) / 100

    if event in ["charge.success", "transfer.success"]:
        if amount_paid < expected_amount:
            return {"status": "success"}

        paid_at = data.get("paid_at")
        paid_at_dt = (
            datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
            if paid_at
            else datetime.utcnow()
        )
        for marking in markings:
            marking.status = SavingsStatus.PAID.value
            marking.marked_by_id = markings[0].savings_account.customer_id
            marking.updated_by = marking.marked_by_id
            marking.updated_at = paid_at_dt
        db.commit()

    return {"status": "success"}


async def create_payment_account_controller(
    request: PaymentAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
):
    return await create_payment_account(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
    )


async def create_account_details_controller(
    request: AccountDetailsCreate,
    payment_account_id: int = Query(..., description="ID of the payment account"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
):
    return await create_account_details(
        payment_account_id=payment_account_id,
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
    )


async def update_account_details_controller(
    account_details_id: int,
    request: AccountDetailsUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
):
    return await update_account_details(
        account_details_id=account_details_id,
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
    )


async def delete_payment_account_controller(
    payment_account_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
):
    return await delete_payment_account(
        payment_account_id=payment_account_id,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
        payments_repo=payments_repo,
    )


async def get_payment_accounts_controller(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    return await get_payment_accounts(
        customer_id=customer_id,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        payment_account_repo=payment_account_repo,
        user_repo=user_repo,
    )


async def update_payment_account_controller(
    payment_account_id: int,
    request: PaymentAccountUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
):
    response = await update_payment_account(
        payment_account_id=payment_account_id,
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
    )
    if response.get("status") == "success":
        return response["data"]
    raise HTTPException(
        status_code=response.get("status_code", 500),
        detail=response.get("message", "Unable to update payment account"),
    )


async def delete_account_details_controller(
    account_details_id: int,
    force_delete: bool = Query(False, description="Force deletion of last account detail"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
):
    return await delete_account_details(
        account_details_id=account_details_id,
        current_user=current_user,
        db=db,
        force_delete=force_delete,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
    )


async def create_payment_request_controller(
    request: PaymentRequestCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
    account_details_repo: AccountDetailsRepository = Depends(
        get_repository(AccountDetailsRepository)
    ),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
    commission_repo: CommissionRepository = Depends(get_repository(CommissionRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await create_payment_request(
        request=request,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payment_account_repo=payment_account_repo,
        account_details_repo=account_details_repo,
        payments_repo=payments_repo,
        commission_repo=commission_repo,
        business_repo=business_repo,
    )


async def get_payment_requests_controller(
    business_id: Optional[int] = Query(None, description="Filter by business ID"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    search: Optional[str] = Query(None, description="Search reference, tracking number, or customer"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    business_repo: BusinessRepository = Depends(get_repository(BusinessRepository)),
):
    return await get_payment_requests(
        business_id=business_id,
        customer_id=customer_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        payments_repo=payments_repo,
        user_repo=user_repo,
        business_repo=business_repo,
    )


async def approve_payment_request_controller(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
):
    return await approve_payment_request(
        request_id=request_id,
        current_user=current_user,
        db=db,
        payments_repo=payments_repo,
    )


async def reject_payment_request_controller(
    request_id: int,
    reject_data: PaymentRequestReject,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
):
    return await reject_payment_request(
        request_id=request_id,
        reject_data=reject_data,
        current_user=current_user,
        db=db,
        payments_repo=payments_repo,
    )


async def cancel_payment_request_controller(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
    payment_account_repo: PaymentAccountRepository = Depends(
        get_repository(PaymentAccountRepository)
    ),
):
    return await cancel_payment_request(
        request_id=request_id,
        current_user=current_user,
        db=db,
        user_repo=user_repo,
        payments_repo=payments_repo,
        payment_account_repo=payment_account_repo,
    )


async def get_commissions_controller(
    business_id: Optional[int] = Query(None, description="Filter by business ID"),
    savings_account_id: Optional[int] = Query(None, description="Filter by savings account ID"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    commission_repo: CommissionRepository = Depends(get_repository(CommissionRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    return await get_agent_commissions(
        business_id=business_id,
        savings_account_id=savings_account_id,
        search=search,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        commission_repo=commission_repo,
        user_repo=user_repo,
    )


async def get_customer_payments_controller(
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    savings_account_id: Optional[int] = Query(None, description="Filter by savings account ID"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    payments_repo: PaymentsRepository = Depends(get_repository(PaymentsRepository)),
    user_repo: UserRepository = Depends(get_repository(UserRepository)),
):
    return await get_customer_payments(
        customer_id=customer_id,
        savings_account_id=savings_account_id,
        search=search,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
        payments_repo=payments_repo,
        user_repo=user_repo,
    )

