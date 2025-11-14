"""
Savings repository for savings-related database operations.
"""
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from models.business import Unit
from models.savings import SavingsAccount, SavingsMarking
from models.user import User
from models.user_business import user_business


class SavingsRepository:
    """Repository for savings models"""

    def __init__(self, db: Session):
        self.db = db

    def get_accounts_by_customer(self, customer_id: int) -> List[SavingsAccount]:
        """Get all savings accounts for a customer"""
        return (
            self.db.query(SavingsAccount)
            .filter(SavingsAccount.customer_id == customer_id)
            .all()
        )

    def customer_has_accounts(self, customer_id: int) -> bool:
        """Check if customer has any savings accounts"""
        return (
            self.db.query(SavingsAccount)
            .filter(SavingsAccount.customer_id == customer_id)
            .first()
            is not None
        )

    def get_markings_by_account(self, account_id: int) -> List[SavingsMarking]:
        """Get all markings for a savings account"""
    def get_savings_with_filters(
        self,
        *,
        customer_id: int | None = None,
        business_id: int | None = None,
        unit_id: int | None = None,
        savings_type: str | None = None,
        search: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[List[SavingsAccount], int]:
        """Query savings accounts with optional filters."""
        query = self.db.query(SavingsAccount)

        if customer_id is not None:
            query = query.filter(SavingsAccount.customer_id == customer_id)
        if business_id is not None:
            query = query.filter(SavingsAccount.business_id == business_id)
        if unit_id is not None:
            query = query.filter(SavingsAccount.unit_id == unit_id)
        if savings_type:
            query = query.filter(SavingsAccount.savings_type == savings_type)
        if search:
            search_pattern = f"%{search.lower()}%"
            query = query.join(User, User.id == SavingsAccount.customer_id, isouter=True)
            query = query.filter(
                or_(
                    func.lower(SavingsAccount.tracking_number).like(search_pattern),
                    func.lower(User.full_name).like(search_pattern),
                    func.lower(User.phone_number).like(search_pattern),
                    func.lower(User.email).like(search_pattern),
                )
            )

        total = query.count()
        savings = (
            query.options(joinedload(SavingsAccount.markings))
            .order_by(SavingsAccount.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return savings, total

    def get_customer_unit_association(
        self, *, user_id: int, unit_id: int, business_id: int
    ) -> bool:
        """Check if a customer is associated with a given unit/business."""
        from models.business import Business

        return (
            self.db.query(Unit.id)
            .join(Business, Unit.business_id == Business.id)
            .join(user_business, user_business.c.business_id == Business.id)
            .filter(
                Unit.id == unit_id,
                Business.id == business_id,
                user_business.c.user_id == user_id,
            )
            .limit(1)
            .first()
            is not None
        )

        return (
            self.db.query(SavingsMarking)
            .filter(SavingsMarking.savings_account_id == account_id)
            .all()
        )

    # -------------------------------------------------------------------------
    # Analytics helpers
    # -------------------------------------------------------------------------

    def get_system_savings_metrics(self) -> Dict[str, object]:
        """
        Compute aggregate savings metrics for system-wide analytics.

        Returns:
            Dict[str, object]: {
                "total_accounts": int,
                "accounts_by_type": Dict[str, int],
                "total_volume": Decimal,
                "volume_by_status": Dict[str, Decimal]
            }
        """
        total_accounts = self.db.query(func.count(SavingsAccount.id)).scalar() or 0

        accounts_by_type_rows = (
            self.db.query(SavingsAccount.savings_type, func.count(SavingsAccount.id))
            .group_by(SavingsAccount.savings_type)
            .all()
        )
        accounts_by_type = {
            getattr(savings_type, "value", savings_type): count
            for savings_type, count in accounts_by_type_rows
        }

        total_volume = (
            self.db.query(func.coalesce(func.sum(SavingsMarking.amount), 0))
            .scalar()
            or Decimal("0")
        )

        status_volume_rows = (
            self.db.query(
                SavingsMarking.status,
                func.coalesce(func.sum(SavingsMarking.amount), 0),
            )
            .group_by(SavingsMarking.status)
            .all()
        )
        volume_by_status = {
            getattr(status, "value", status): volume
            for status, volume in status_volume_rows
        }

        return {
            "total_accounts": total_accounts,
            "accounts_by_type": accounts_by_type,
            "total_volume": Decimal(total_volume)
            if not isinstance(total_volume, Decimal)
            else total_volume,
            "volume_by_status": {
                key: Decimal(value) if not isinstance(value, Decimal) else value
                for key, value in volume_by_status.items()
            },
        }

    def get_successful_transfer_metrics(self) -> Dict[str, float]:
        """Return count and amount of savings markings settled via transfers."""
        transfer_methods = {"transfer", "bank_transfer", "bank-transfer"}

        count_amount = (
            self.db.query(
                func.count(SavingsMarking.id),
                func.coalesce(func.sum(SavingsMarking.amount), 0),
            )
            .filter(
                SavingsMarking.status == "paid",
                SavingsMarking.payment_method.in_(transfer_methods),
            )
            .first()
        )

        if not count_amount:
            return {"count": 0, "amount": 0.0}

        count, amount = count_amount
        return {
            "count": int(count or 0),
            "amount": float(Decimal(amount or 0)),
        }

    def get_monthly_transfer_volume(self, months: int = 6) -> List[Dict[str, float]]:
        """Return monthly sums for successful transfer markings."""
        if months <= 0:
            return []

        transfer_methods = {"transfer", "bank_transfer", "bank-transfer"}
        month_alias = func.date_trunc("month", SavingsMarking.marked_date)

        rows = (
            self.db.query(
                month_alias.label("month"),
                func.coalesce(func.sum(SavingsMarking.amount), 0).label("amount"),
            )
            .filter(
                SavingsMarking.status == "paid",
                SavingsMarking.payment_method.in_(transfer_methods),
                SavingsMarking.marked_date.isnot(None),
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

