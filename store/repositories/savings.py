"""
Savings repository for savings-related database operations.
"""
from typing import List
from sqlalchemy.orm import Session

from models.savings import SavingsAccount, SavingsMarking


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
        return (
            self.db.query(SavingsMarking)
            .filter(SavingsMarking.savings_account_id == account_id)
            .all()
        )

