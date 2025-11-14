"""
Repositories for expense cards and expenses.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, cast, String
from sqlalchemy.orm import Session, joinedload

from models.expenses import Expense, ExpenseCard
from store.repositories.base import BaseRepository


class ExpenseCardRepository(BaseRepository[ExpenseCard]):
    """Repository for managing expense cards."""

    def __init__(self, db: Session):
        super().__init__(ExpenseCard, db)

    def get_by_id_for_user(self, card_id: int, user_id: int) -> Optional[ExpenseCard]:
        return (
            self.db.query(ExpenseCard)
            .options(joinedload(ExpenseCard.expenses))
            .filter(ExpenseCard.id == card_id, ExpenseCard.customer_id == user_id)
            .first()
        )

    def list_for_user(
        self,
        *,
        user_id: int,
        search: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[ExpenseCard], int]:
        query = self.db.query(ExpenseCard).filter(ExpenseCard.customer_id == user_id)

        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(ExpenseCard.name).like(pattern),
                    func.lower(func.coalesce(ExpenseCard.income_details, "")).like(
                        pattern
                    ),
                )
            )

        total = query.count()
        cards = (
            query.order_by(ExpenseCard.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return cards, total

    def get_all_for_user(self, user_id: int) -> List[ExpenseCard]:
        return (
            self.db.query(ExpenseCard)
            .filter(ExpenseCard.customer_id == user_id)
            .options(joinedload(ExpenseCard.expenses))
            .all()
        )


class ExpenseRepository(BaseRepository[Expense]):
    """Repository for managing expense entries."""

    def __init__(self, db: Session):
        super().__init__(Expense, db)

    def list_for_card(
        self,
        *,
        card_id: int,
        search: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[List[Expense], int]:
        query = self.db.query(Expense).filter(Expense.expense_card_id == card_id)

        if search:
            pattern = f"%{search.lower()}%"
            query = (
                query.join(ExpenseCard, Expense.expense_card_id == ExpenseCard.id)
                .filter(
                    or_(
                        func.lower(func.coalesce(Expense.description, "")).like(pattern),
                        func.lower(func.coalesce(ExpenseCard.name, "")).like(pattern),
                        func.lower(
                            func.coalesce(
                                cast(Expense.category, String),
                                "",
                            )
                        ).like(pattern),
                    )
                )
            )

        total = query.count()
        expenses = (
            query.order_by(Expense.date.desc()).offset(offset).limit(limit).all()
        )
        return expenses, total

    def sum_by_user(
        self,
        *,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Decimal:
        query = (
            self.db.query(func.coalesce(func.sum(Expense.amount), 0))
            .join(ExpenseCard)
            .filter(ExpenseCard.customer_id == user_id)
        )
        if from_date:
            query = query.filter(Expense.date >= from_date)
        if to_date:
            query = query.filter(Expense.date <= to_date)
        return Decimal(query.scalar() or 0)

    def count_by_user(
        self,
        *,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> int:
        """Count expenses for a customer within an optional date range."""
        query = (
            self.db.query(func.count(Expense.id))
            .join(ExpenseCard)
            .filter(ExpenseCard.customer_id == user_id)
        )
        if from_date:
            query = query.filter(Expense.date >= from_date)
        if to_date:
            query = query.filter(Expense.date <= to_date)
        return query.scalar() or 0

    def grouped_by_category(
        self,
        *,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Sequence[Tuple[str, Decimal]]:
        query = (
            self.db.query(Expense.category, func.sum(Expense.amount))
            .join(ExpenseCard)
            .filter(ExpenseCard.customer_id == user_id)
        )
        if from_date:
            query = query.filter(Expense.date >= from_date)
        if to_date:
            query = query.filter(Expense.date <= to_date)
        return query.group_by(Expense.category).all()

