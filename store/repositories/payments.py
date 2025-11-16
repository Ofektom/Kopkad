"""
Payments repositories for payment requests, accounts, account details, and commissions.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from models.payments import (
    AccountDetails,
    Commission,
    PaymentAccount,
    PaymentRequest,
    PaymentRequestStatus,
)
from models.savings import SavingsAccount
from models.user import User
from store.repositories.base import BaseRepository


class PaymentAccountRepository(BaseRepository[PaymentAccount]):
    """Repository for payment accounts."""

    def __init__(self, db: Session):
        super().__init__(PaymentAccount, db)

    def get_by_customer_id(self, customer_id: int) -> Optional[PaymentAccount]:
        return (
            self.db.query(PaymentAccount)
            .options(selectinload(PaymentAccount.account_details))
            .filter(PaymentAccount.customer_id == customer_id)
            .first()
        )

    def get_accounts_with_filters(
        self,
        *,
        customer_id: Optional[int],
        limit: int,
        offset: int,
    ) -> Tuple[List[PaymentAccount], int]:
        load_options = [selectinload(PaymentAccount.account_details)]
        if hasattr(PaymentAccount, "customer"):
            load_options.append(joinedload(getattr(PaymentAccount, "customer")))

        query = (
            self.db.query(PaymentAccount)
            .options(*load_options)
            .order_by(PaymentAccount.created_at.desc())
        )

        if customer_id is not None:
            query = query.filter(PaymentAccount.customer_id == customer_id)

        total = query.count()
        accounts = query.offset(offset).limit(limit).all()
        return accounts, total

    def has_active_requests(self, payment_account_id: int) -> bool:
        return (
            self.db.query(PaymentRequest)
            .filter(PaymentRequest.payment_account_id == payment_account_id)
            .first()
            is not None
        )


class AccountDetailsRepository(BaseRepository[AccountDetails]):
    """Repository for payment account details."""

    def __init__(self, db: Session):
        super().__init__(AccountDetails, db)

    def get_for_account(self, payment_account_id: int) -> List[AccountDetails]:
        return (
            self.db.query(AccountDetails)
            .filter(AccountDetails.payment_account_id == payment_account_id)
            .all()
        )

    def count_for_account(self, payment_account_id: int) -> int:
        return (
            self.db.query(func.count(AccountDetails.id))
            .filter(AccountDetails.payment_account_id == payment_account_id)
            .scalar()
            or 0
        )

    def count_other_details(self, account_details_id: int) -> int:
        detail = (
            self.db.query(AccountDetails)
            .filter(AccountDetails.id == account_details_id)
            .first()
        )
        if not detail:
            return 0
        return (
            self.db.query(func.count(AccountDetails.id))
            .filter(
                AccountDetails.payment_account_id == detail.payment_account_id,
                AccountDetails.id != account_details_id,
            )
            .scalar()
            or 0
        )


class CommissionRepository(BaseRepository[Commission]):
    """Repository for commissions."""

    def __init__(self, db: Session):
        super().__init__(Commission, db)

    def get_commissions_with_filters(
        self,
        *,
        business_ids: Optional[Sequence[int]] = None,
        business_id: Optional[int] = None,
        savings_account_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int,
        offset: int,
    ) -> Tuple[List[Commission], int]:
        query = (
            self.db.query(Commission)
            .join(SavingsAccount, SavingsAccount.id == Commission.savings_account_id)
            .join(User, User.id == SavingsAccount.customer_id)
            .options(
                joinedload(Commission.savings_account).joinedload(
                    SavingsAccount.customer
                )
            )
        )

        if business_ids:
            query = query.filter(SavingsAccount.business_id.in_(business_ids))

        if business_id:
            query = query.filter(SavingsAccount.business_id == business_id)

        if savings_account_id:
            query = query.filter(Commission.savings_account_id == savings_account_id)

        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.phone_number).like(pattern),
                    func.lower(SavingsAccount.tracking_number).like(pattern),
                )
            )

        total = query.count()
        items = (
            query.order_by(Commission.commission_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total


class PaymentsRepository(BaseRepository[PaymentRequest]):
    """Repository dedicated to payment requests and analytics."""

    def __init__(self, db: Session):
        super().__init__(PaymentRequest, db)

    # ------------------------------------------------------------------
    # Analytics helpers
    # ------------------------------------------------------------------
    def get_status_summary(self) -> List[Dict[str, object]]:
        rows = (
            self.db.query(
                PaymentRequest.status,
                func.count(PaymentRequest.id),
                func.coalesce(func.sum(PaymentRequest.amount), 0),
            )
            .group_by(PaymentRequest.status)
            .all()
        )

        summary: List[Dict[str, object]] = []
        for status, count, amount in rows:
            status_value = (
                status.value if isinstance(status, PaymentRequestStatus) else status
            )
            summary.append(
                {
                    "status": status_value,
                    "count": int(count or 0),
                    "amount": float(Decimal(amount or 0)),
                }
            )
        return summary

    def count_total_requests(self) -> int:
        return self.db.query(func.count(PaymentRequest.id)).scalar() or 0

    def get_successful_payment_stats(self) -> Dict[str, float]:
        query = (
            self.db.query(
                func.count(PaymentRequest.id),
                func.coalesce(func.sum(PaymentRequest.amount), 0),
            )
            .filter(PaymentRequest.status == PaymentRequestStatus.APPROVED.value)
            .first()
        )
        count = int(query[0] or 0) if query else 0
        amount = float(Decimal(query[1] or 0)) if query else 0.0
        return {"count": count, "amount": amount}

    def get_monthly_payment_volume(self, months: int = 6) -> List[Dict[str, float]]:
        if months <= 0:
            return []

        month_alias = func.date_trunc("month", PaymentRequest.approval_date)
        rows = (
            self.db.query(
                month_alias.label("month"),
                func.coalesce(func.sum(PaymentRequest.amount), 0).label("amount"),
            )
            .filter(
                PaymentRequest.status == PaymentRequestStatus.APPROVED.value,
                PaymentRequest.approval_date.isnot(None),
            )
            .group_by("month")
            .order_by(month_alias.desc())
            .limit(months)
            .all()
        )

        formatted: List[Dict[str, float]] = []
        for month, amount in reversed(rows):
            label = month.strftime("%b %Y") if month else "Unknown"
            formatted.append({"label": label, "value": float(Decimal(amount or 0))})
        return formatted

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------
    def get_by_id_with_relations(self, request_id: int) -> Optional[PaymentRequest]:
        return (
            self.db.query(PaymentRequest)
            .options(
                joinedload(PaymentRequest.payment_account),
                joinedload(PaymentRequest.savings_account),
            )
            .filter(PaymentRequest.id == request_id)
            .first()
        )

    def get_existing_for_savings(
        self, savings_account_id: int, statuses: Iterable[PaymentRequestStatus]
    ) -> Optional[PaymentRequest]:
        status_values = [status.value if isinstance(status, PaymentRequestStatus) else status for status in statuses]
        return (
            self.db.query(PaymentRequest)
            .filter(
                PaymentRequest.savings_account_id == savings_account_id,
                PaymentRequest.status.in_(status_values),
            )
            .first()
        )

    def get_payment_requests_with_filters(
        self,
        *,
        base_conditions: Optional[Sequence] = None,
        status: Optional[PaymentRequestStatus] = None,
        customer_id: Optional[int] = None,
        business_id: Optional[int] = None,
        search: Optional[str] = None,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        limit: int,
        offset: int,
    ) -> Tuple[List[PaymentRequest], int]:
        payment_account_loader = joinedload(PaymentRequest.payment_account)
        if hasattr(PaymentAccount, "customer"):
            payment_account_loader = payment_account_loader.joinedload(
                getattr(PaymentAccount, "customer")
            )

        query = (
            self.db.query(PaymentRequest)
            .join(PaymentAccount, PaymentAccount.id == PaymentRequest.payment_account_id)
            .join(SavingsAccount, SavingsAccount.id == PaymentRequest.savings_account_id)
            .join(User, User.id == PaymentAccount.customer_id)
            .options(
                payment_account_loader,
                joinedload(PaymentRequest.savings_account),
            )
        )

        if base_conditions:
            query = query.filter(and_(*base_conditions))

        if status:
            status_value = (
                status.value if isinstance(status, PaymentRequestStatus) else status
            )
            query = query.filter(PaymentRequest.status == status_value)

        if customer_id is not None:
            query = query.filter(PaymentAccount.customer_id == customer_id)

        if business_id is not None:
            query = query.filter(SavingsAccount.business_id == business_id)

        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(PaymentRequest.reference).like(pattern),
                    func.lower(SavingsAccount.tracking_number).like(pattern),
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.phone_number).like(pattern),
                    func.lower(User.email).like(pattern),
                )
            )

        if start_dt:
            query = query.filter(PaymentRequest.request_date >= start_dt)
        if end_dt:
            query = query.filter(PaymentRequest.request_date < end_dt)

        total = query.count()
        requests = (
            query.order_by(PaymentRequest.request_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return requests, total
