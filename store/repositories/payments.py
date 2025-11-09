"""
Payments repository for analytics on payment requests.
"""
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.payments import PaymentRequest, PaymentRequestStatus
from store.repositories.base import BaseRepository


class PaymentsRepository(BaseRepository[PaymentRequest]):
    """Repository dedicated to payment request analytics."""

    def __init__(self, db: Session):
        super().__init__(PaymentRequest, db)

    def get_status_summary(self) -> List[Dict[str, object]]:
        """Return counts and amounts grouped by payment request status."""
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
        """Return total number of payment requests."""
        return self.db.query(func.count(PaymentRequest.id)).scalar() or 0

    def get_successful_payment_stats(self) -> Dict[str, float]:
        """Return count and amount of approved payment requests."""
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
        """Return the sum of approved payment amounts per month."""
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


