from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.user import User
from models.business import Business
from models.savings import SavingsAccount
from models.payments import PaymentRequest
from models.user_business import user_business
from utils.response import error_response, success_response
from store.enums import Role


async def universal_search(
    *,
    term: str,
    limit: int,
    current_user: Dict,
    db: Session,
) -> Dict[str, object]:
    """
    Perform a role-aware search across core system entities.

    Returns grouped results for:
    - users
    - businesses
    - savings accounts
    - payment requests
    """
    if not term or not term.strip():
        return error_response(status_code=400, message="Search term is required.")

    limit = max(1, min(limit, 20))
    normalized_term = term.strip()
    search_pattern = f"%{normalized_term.lower()}%"

    role = current_user.get("role")
    user_id = current_user.get("user_id")

    accessible_business_ids: Optional[List[int]] = None

    if role == Role.SUPER_ADMIN.value:
        accessible_business_ids = None  # Super admin can see everything
    elif role == Role.ADMIN.value:
        admin_business = (
            db.query(Business)
            .filter(Business.admin_id == user_id)
            .first()
        )
        accessible_business_ids = [admin_business.id] if admin_business else []
    else:
        accessible_business_ids = [
            row[0]
            for row in db.query(user_business.c.business_id)
            .filter(user_business.c.user_id == user_id)
            .all()
        ]

    def business_scope_filter(query):
        if accessible_business_ids is None:
            return query
        if not accessible_business_ids:
            return query.filter(False)  # No access
        return query.filter(Business.id.in_(accessible_business_ids))

    # ------------------------------------------------------------------
    # Businesses
    # ------------------------------------------------------------------
    business_query = db.query(Business)
    business_query = business_scope_filter(business_query)
    business_query = business_query.filter(
        or_(
            func.lower(Business.name).like(search_pattern),
            func.lower(Business.unique_code).like(search_pattern),
            func.lower(Business.address).like(search_pattern),
        )
    )
    businesses = business_query.order_by(Business.created_at.desc()).limit(limit).all()
    business_results = [
        {
            "id": business.id,
            "name": business.name,
            "unique_code": business.unique_code,
            "address": business.address,
        }
        for business in businesses
    ]

    # ------------------------------------------------------------------
    # Users (respect business scope)
    # ------------------------------------------------------------------
    user_query = (
        db.query(User)
        .filter(
            or_(
                func.lower(User.full_name).like(search_pattern),
                func.lower(User.email).like(search_pattern),
                func.lower(User.phone_number).like(search_pattern),
                func.lower(User.username).like(search_pattern),
            )
        )
    )

    if accessible_business_ids is not None:
        user_query = (
            user_query.join(
                user_business, user_business.c.user_id == User.id, isouter=True
            )
            .filter(user_business.c.business_id.in_(accessible_business_ids))
            .distinct()
        )

    users = user_query.order_by(User.created_at.desc()).limit(limit).all()
    user_results = [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "role": user.role,
        }
        for user in users
    ]

    # ------------------------------------------------------------------
    # Savings Accounts
    # ------------------------------------------------------------------
    savings_query = (
        db.query(SavingsAccount)
        .filter(
            or_(
                func.lower(SavingsAccount.tracking_number).like(search_pattern),
            )
        )
    )

    if accessible_business_ids is not None:
        savings_query = savings_query.filter(
            SavingsAccount.business_id.in_(accessible_business_ids)
        )

    savings_accounts = (
        savings_query.order_by(SavingsAccount.created_at.desc()).limit(limit).all()
    )
    savings_results = [
        {
            "id": savings.id,
            "tracking_number": savings.tracking_number,
            "business_id": savings.business_id,
            "customer_id": savings.customer_id,
            "savings_type": savings.savings_type,
        }
        for savings in savings_accounts
    ]

    # ------------------------------------------------------------------
    # Payment Requests
    # ------------------------------------------------------------------
    payments_query = (
        db.query(PaymentRequest)
        .join(SavingsAccount, SavingsAccount.id == PaymentRequest.savings_account_id)
        .filter(
            or_(
                func.lower(PaymentRequest.reference).like(search_pattern),
                func.lower(SavingsAccount.tracking_number).like(search_pattern),
            )
        )
    )

    if accessible_business_ids is not None:
        payments_query = payments_query.filter(
            SavingsAccount.business_id.in_(accessible_business_ids)
        )

    payment_requests = (
        payments_query.order_by(PaymentRequest.request_date.desc()).limit(limit).all()
    )
    payment_results = [
        {
            "id": request.id,
            "reference": request.reference,
            "status": request.status,
            "amount": float(request.amount),
            "business_id": request.savings_account.business_id
            if request.savings_account
            else None,
            "tracking_number": request.savings_account.tracking_number
            if request.savings_account
            else None,
        }
        for request in payment_requests
    ]

    return success_response(
        status_code=200,
        message="Search results loaded successfully",
        data={
            "term": normalized_term,
            "results": {
                "businesses": business_results,
                "users": user_results,
                "savings": savings_results,
                "payments": payment_results,
            },
        },
    )

