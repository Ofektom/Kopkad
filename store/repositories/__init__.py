"""
Repository package for database operations.
Following Repository Pattern for clean separation of data access logic.
"""
from .base import BaseRepository
from .user import UserRepository
from .business import (
    BusinessRepository,
    UnitRepository,
    BusinessPermissionRepository,
)
from .permissions import PermissionRepository
from .settings import SettingsRepository

# Specialized repositories
from .user_business import UserBusinessRepository
from .savings import SavingsRepository
from .payments import (
    PaymentsRepository,
    PaymentAccountRepository,
    AccountDetailsRepository,
    CommissionRepository,
)
from .expenses import ExpenseCardRepository, ExpenseRepository
from .pending_business_request import PendingBusinessRequestRepository
from .financial_advisor import (
    SavingsGoalRepository,
    FinancialHealthScoreRepository,
    SpendingPatternRepository,
    UserNotificationRepository,
)

__all__ = [
    "BaseRepository",
    "UserRepository",
    "BusinessRepository",
    "UnitRepository",
    "BusinessPermissionRepository",
    "PermissionRepository",
    "SettingsRepository",
    "UserBusinessRepository",
    "SavingsRepository",
    "PaymentsRepository",
    "PaymentAccountRepository",
    "AccountDetailsRepository",
    "CommissionRepository",
    "ExpenseCardRepository",
    "ExpenseRepository",
    "PendingBusinessRequestRepository",
    "SavingsGoalRepository",
    "FinancialHealthScoreRepository",
    "SpendingPatternRepository",
    "UserNotificationRepository",
]

